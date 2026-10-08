# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre: usted puede redistribuirlo y/o
modificarlo bajo los términos de la Licencia Pública General de GNU
publicada por la Free Software Foundation, ya sea la versión 3
de la Licencia, o (a su elección) cualquier versión posterior.

Este programa se distribuye con la esperanza de que sea útil, pero
SIN NINGUNA GARANTÍA; sin siquiera la garantía implícita de
COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Vea la
Licencia Pública General de GNU para más detalles.

Debería haber recibido una copia de la Licencia Pública General de GNU
junto con este programa. Si no, vea <https://www.gnu.org/licenses/>.

S11 — extracción segura SOLO en sandbox temporal.
ZIP vía stdlib; 7z/RAR solo listado/extracción si existe 7z fiable en PATH.
No ejecuta instaladores ni código del paquete.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Límites anti zip-bomb / DoS
MAX_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB lógico
MAX_SINGLE_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
MAX_RATIO = 200  # uncompressed/compressed aprox. por entrada zip


@dataclass
class ExtractResult:
    ok: bool
    sandbox: Path | None
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tool: str = ""
    bytes_written: int = 0


def find_7z_executable() -> Path | None:
    for name in ("7z.exe", "7z", "7za.exe", "7za"):
        p = shutil.which(name)
        if p:
            return Path(p)
    # rutas típicas Windows
    for cand in (
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ):
        if cand.is_file():
            return cand
    return None


def _safe_join(root: Path, member: str) -> Path:
    """Resuelve member bajo root; bloquea absolutos, .. y escapes."""
    if not member or member.endswith("/") or member.endswith("\\"):
        raise ValueError(f"entrada de directorio ignorada: {member}")
    # normalizar separadores
    norm = member.replace("\\", "/").lstrip("/")
    if norm.startswith("../") or "/../" in f"/{norm}/" or norm == "..":
        raise ValueError(f"path traversal bloqueado: {member}")
    p = Path(norm)
    if p.is_absolute() or getattr(p, "drive", ""):
        raise ValueError(f"ruta absoluta bloqueada: {member}")
    if any(part in ("..", "") for part in p.parts if part == ".."):
        raise ValueError(f"path traversal bloqueado: {member}")
    dest = (root / p).resolve()
    root_res = root.resolve()
    try:
        dest.relative_to(root_res)
    except ValueError as e:
        raise ValueError(f"escape de sandbox: {member}") from e
    return dest


def list_zip_members(archive: Path) -> tuple[list[str], list[str]]:
    """Devuelve (nombres_archivo, errores)."""
    errs: list[str] = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            if zf.testzip() is not None:
                errs.append("ZIP corrupto (testzip falló)")
            for info in zf.infolist():
                if info.is_dir():
                    continue
                names.append(info.filename.replace("\\", "/"))
    except zipfile.BadZipFile as e:
        errs.append(f"ZIP inválido: {e}")
    except Exception as e:
        errs.append(str(e))
    return names, errs


def list_archive_members(archive: Path) -> tuple[list[str], list[str], str]:
    """Lista miembros. tool = zip|7z|unsupported."""
    suf = archive.suffix.lower()
    if suf == ".zip":
        names, errs = list_zip_members(archive)
        return names, errs, "zip"
    if suf in {".7z", ".rar"}:
        exe = find_7z_executable()
        if not exe:
            return [], [f"Sin herramienta 7z fiable para {suf}"], "unsupported"
        try:
            from .win_compat import subprocess_creationflags

            proc = subprocess.run(
                [str(exe), "l", "-slt", "-ba", str(archive)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                creationflags=subprocess_creationflags(),
            )
            if proc.returncode != 0:
                return [], [f"7z list falló ({proc.returncode}): {proc.stderr[:200]}"], "7z"
            names: list[str] = []
            cur_path = ""
            is_dir = False
            for line in (proc.stdout or "").splitlines():
                if line.startswith("Path = "):
                    cur_path = line[7:].strip().replace("\\", "/")
                    is_dir = False
                elif line.startswith("Attributes = "):
                    is_dir = "D" in line[13:]
                elif line.strip() == "" and cur_path:
                    if not is_dir and cur_path not in (".", archive.name):
                        names.append(cur_path)
                    cur_path = ""
            if cur_path and not is_dir:
                names.append(cur_path)
            return names, [], "7z"
        except Exception as e:
            return [], [str(e)], "7z"
    return [], [f"formato no soportado: {suf}"], "unsupported"


def extract_zip_safe(archive: Path, sandbox: Path) -> ExtractResult:
    res = ExtractResult(ok=False, sandbox=sandbox, tool="zip")
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                res.errors.append(f"ZIP corrupto en entrada: {bad}")
                return res
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if len(infos) > MAX_FILES:
                res.errors.append(f"demasiados archivos ({len(infos)} > {MAX_FILES})")
                return res
            total_uncomp = sum(max(0, i.file_size) for i in infos)
            if total_uncomp > MAX_UNCOMPRESSED_BYTES:
                res.errors.append("tamaño descomprimido supera el límite")
                return res
            comp = max(1, archive.stat().st_size)
            if total_uncomp / comp > MAX_RATIO and total_uncomp > 64 * 1024 * 1024:
                res.errors.append("ratio de compresión sospechoso (posible zip bomb)")
                return res

            written = 0
            for info in infos:
                if info.file_size > MAX_SINGLE_FILE_BYTES:
                    res.errors.append(f"archivo demasiado grande: {info.filename}")
                    return res
                # Zip Slip
                try:
                    dest = _safe_join(sandbox, info.filename)
                except ValueError as e:
                    res.errors.append(str(e))
                    return res
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                # rechazar symlinks creados
                if dest.is_symlink():
                    res.errors.append(f"symlink bloqueado: {info.filename}")
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                    return res
                written += dest.stat().st_size
                res.files.append(dest.relative_to(sandbox).as_posix())
            res.bytes_written = written
            res.ok = True
    except zipfile.BadZipFile as e:
        res.errors.append(f"ZIP inválido: {e}")
    except Exception as e:
        res.errors.append(str(e))
    return res


def extract_with_7z(archive: Path, sandbox: Path) -> ExtractResult:
    res = ExtractResult(ok=False, sandbox=sandbox, tool="7z")
    exe = find_7z_executable()
    if not exe:
        res.errors.append("7z no disponible")
        return res
    # list first for limits
    names, errs, _ = list_archive_members(archive)
    if errs:
        res.errors.extend(errs)
        return res
    if len(names) > MAX_FILES:
        res.errors.append(f"demasiados archivos ({len(names)})")
        return res
    # validar paths antes
    for n in names:
        try:
            _safe_join(sandbox, n)
        except ValueError as e:
            res.errors.append(str(e))
            return res
    try:
        from .win_compat import subprocess_creationflags

        proc = subprocess.run(
            [str(exe), "x", f"-o{sandbox}", "-y", "-ba", str(archive)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            creationflags=subprocess_creationflags(),
        )
        if proc.returncode != 0:
            res.errors.append(f"7z extract falló: {proc.stderr[:300]}")
            return res
        for f in sandbox.rglob("*"):
            if f.is_symlink():
                res.errors.append(f"symlink bloqueado tras extracción: {f}")
                return res
            if f.is_file():
                res.files.append(f.relative_to(sandbox).as_posix())
                res.bytes_written += f.stat().st_size
        if res.bytes_written > MAX_UNCOMPRESSED_BYTES:
            res.errors.append("extracción supera límite de tamaño")
            return res
        res.ok = True
    except Exception as e:
        res.errors.append(str(e))
    return res


def extract_to_sandbox(
    archive: Path,
    *,
    parent: Path | None = None,
) -> ExtractResult:
    """Extrae a directorio temporal bajo parent (o tempfile). No toca staging/downloads."""
    if not archive.is_file():
        return ExtractResult(ok=False, sandbox=None, errors=["archivo inexistente"])
    root = Path(parent) if parent else Path(tempfile.mkdtemp(prefix="sgm_s11_"))
    if parent:
        root.mkdir(parents=True, exist_ok=True)
        sandbox = Path(tempfile.mkdtemp(prefix="extract_", dir=str(root)))
    else:
        sandbox = root
    suf = archive.suffix.lower()
    if suf == ".zip":
        return extract_zip_safe(archive, sandbox)
    if suf in {".7z", ".rar"}:
        return extract_with_7z(archive, sandbox)
    return ExtractResult(
        ok=False,
        sandbox=sandbox,
        errors=[f"formato no soportado para extracción: {suf}"],
        tool="unsupported",
    )


def cleanup_sandbox(sandbox: Path | None) -> None:
    if sandbox is None:
        return
    try:
        if sandbox.is_dir():
            shutil.rmtree(sandbox, ignore_errors=True)
    except OSError:
        pass
