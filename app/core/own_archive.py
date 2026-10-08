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

S12 — ARCHIVO_PROPIO (ZIP generado por el gestor, no es descarga Nexus).
Creación con verificación sandbox antes de publicar. Restauración solo a sandbox.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..version import __version__
from .archive_extract import (
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    _safe_join,
    cleanup_sandbox,
)
from .hash_cache import sha256_file
from .inventory import ModEntry, nexus_id_from_folder

# Manifiesto bajo ruta reservada (no es contenido del mod)
MANIFEST_DIR = "__sgm_archive__/v1"
MANIFEST_NAME = "manifest.json"
MANIFEST_ZIP_PATH = f"{MANIFEST_DIR}/{MANIFEST_NAME}"
FORMAT_ID = "sgm_own_archive"
FORMAT_VERSION = 1
PACKAGE_KIND = "ARCHIVO_PROPIO"

SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}

ProgressCb = Callable[[str, int, int], None]
CancelCb = Callable[[], bool]


@dataclass
class OwnArchiveFile:
    path: str
    sha256: str
    size: int


@dataclass
class OwnArchiveManifest:
    format: str
    format_version: int
    package_kind: str
    game_id: str
    mod_id: str
    folder: str
    display_name: str
    nexus_id: str | None
    created_at: str
    product_version: str
    variants: list[str]
    pak_elegido: str
    files: list[OwnArchiveFile]
    total_files: int
    total_bytes: int
    content_sha256: str
    compression: str = "ZIP_DEFLATED"

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "format_version": self.format_version,
            "package_kind": self.package_kind,
            "game_id": self.game_id,
            "mod_id": self.mod_id,
            "folder": self.folder,
            "display_name": self.display_name,
            "nexus_id": self.nexus_id,
            "created_at": self.created_at,
            "product_version": self.product_version,
            "variants": list(self.variants),
            "pak_elegido": self.pak_elegido,
            "files": [
                {"path": f.path, "sha256": f.sha256, "size": f.size} for f in self.files
            ],
            "total_files": self.total_files,
            "total_bytes": self.total_bytes,
            "content_sha256": self.content_sha256,
            "compression": self.compression,
            "note": (
                "Paquete generado por F7777techMods. "
                "No es descarga original de Vortex/Nexus ni actualización oficial."
            ),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OwnArchiveManifest":
        files = [
            OwnArchiveFile(
                path=str(x["path"]),
                sha256=str(x["sha256"]),
                size=int(x["size"]),
            )
            for x in (d.get("files") or [])
        ]
        return cls(
            format=str(d.get("format") or ""),
            format_version=int(d.get("format_version") or 0),
            package_kind=str(d.get("package_kind") or ""),
            game_id=str(d.get("game_id") or ""),
            mod_id=str(d.get("mod_id") or ""),
            folder=str(d.get("folder") or ""),
            display_name=str(d.get("display_name") or ""),
            nexus_id=d.get("nexus_id"),
            created_at=str(d.get("created_at") or ""),
            product_version=str(d.get("product_version") or ""),
            variants=list(d.get("variants") or []),
            pak_elegido=str(d.get("pak_elegido") or ""),
            files=files,
            total_files=int(d.get("total_files") or len(files)),
            total_bytes=int(d.get("total_bytes") or 0),
            content_sha256=str(d.get("content_sha256") or ""),
            compression=str(d.get("compression") or "ZIP_DEFLATED"),
        )


@dataclass
class CreateOwnArchiveResult:
    ok: bool
    published_path: str = ""
    mod_id: str = ""
    zip_sha256: str = ""
    zip_size: int = 0
    file_count: int = 0
    logical_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    verified_restore: bool = False
    elapsed_s: float = 0.0
    status: str = "PENDIENTE"  # S13: PENDIENTE|COMPRIMIENDO|VERIFICANDO|ARCHIVADO VERIFICADO|ERROR|BLOQUEADO
    content_sha256: str = ""
    origin_unchanged: bool = False


def validate_archive_destination(
    dest_dir: Path,
    *,
    stage_root: Path | None = None,
    game_root: Path | None = None,
    mods_dir: Path | None = None,
) -> list[str]:
    """Rechaza destinos dentro de staging / juego / ~mods."""
    errs: list[str] = []
    try:
        dest = dest_dir.resolve()
    except OSError as e:
        return [f"destino inválido: {e}"]
    forbidden: list[tuple[str, Path]] = []
    if stage_root and stage_root.exists():
        forbidden.append(("staging", stage_root.resolve()))
    if game_root and str(game_root).strip() and Path(game_root).exists():
        forbidden.append(("juego", Path(game_root).resolve()))
    if mods_dir and str(mods_dir).strip() and Path(mods_dir).exists():
        forbidden.append(("mods_dir", Path(mods_dir).resolve()))
    for label, root in forbidden:
        try:
            dest.relative_to(root)
            errs.append(f"destino no puede estar dentro de {label}: {root}")
        except ValueError:
            pass
        try:
            root.relative_to(dest)
            # dest es ancestro del root — también peligroso (escribir encima del árbol)
            if root != dest:
                pass  # OK: archive parent of game is unusual but not inside
        except ValueError:
            pass
    return errs


def _origin_fingerprint(files: list[tuple[Path, str]]) -> dict[str, tuple[int, int]]:
    """rel -> (size, mtime_ns)."""
    out: dict[str, tuple[int, int]] = {}
    for abs_p, rel in files:
        st = abs_p.stat()
        out[rel] = (st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    return out


def _origin_changed(
    files: list[tuple[Path, str]],
    before: dict[str, tuple[int, int]],
    hashed: list[OwnArchiveFile],
) -> list[str]:
    """Detecta cambio de origen (stat y re-hash)."""
    errs: list[str] = []
    by_rel = {h.path: h for h in hashed}
    for abs_p, rel in files:
        try:
            st = abs_p.stat()
        except OSError as e:
            errs.append(f"origen desapareció ({rel}): {e}")
            continue
        prev = before.get(rel)
        cur = (st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
        if prev is None or prev != cur:
            errs.append(f"origen cambió durante el archivo: {rel}")
            continue
        ent = by_rel.get(rel)
        if ent is None:
            continue
        if sha256_file(abs_p) != ent.sha256:
            errs.append(f"SHA origen cambió durante el archivo: {rel}")
    return errs


@dataclass
class RestoreOwnArchiveResult:
    ok: bool
    sandbox: Path | None = None
    manifest: OwnArchiveManifest | None = None
    errors: list[str] = field(default_factory=list)
    files_matched: int = 0


def make_mod_id(game_id: str, folder: str) -> str:
    """Identificador estable; no usa el nombre visible como único."""
    h = hashlib.sha256(f"{game_id}\0{folder}".encode("utf-8")).hexdigest()
    return f"sgm_{h[:20]}"


def content_digest(files: list[OwnArchiveFile]) -> str:
    lines = [f"{f.path}:{f.sha256}:{f.size}" for f in sorted(files, key=lambda x: x.path)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _scan_stage_files(stage_mod: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Devuelve [(abs_path, rel_posix), ...] y errores."""
    errors: list[str] = []
    rows: list[tuple[Path, str]] = []
    if not stage_mod.is_dir():
        return [], ["carpeta de staging inexistente"]
    for f in sorted(stage_mod.rglob("*"), key=lambda p: str(p).lower()):
        if f.is_symlink():
            errors.append(f"symlink rechazado: {f.relative_to(stage_mod).as_posix()}")
            continue
        if not f.is_file():
            # junctions / dirs: skip dirs; if reparse point file-like, skip
            continue
        if f.name.lower() in SKIP_NAMES:
            continue
        # Windows: detectar junction vía FILE_ATTRIBUTE_REPARSE_POINT aproximado
        try:
            if os.path.islink(f) or (hasattr(f, "is_junction") and f.is_junction()):
                errors.append(f"enlace/junction rechazado: {f}")
                continue
        except OSError:
            pass
        try:
            rel = f.relative_to(stage_mod).as_posix()
        except ValueError:
            errors.append(f"ruta fuera del mod: {f}")
            continue
        if rel.startswith("__sgm_archive__/"):
            errors.append(f"colisión con ruta de manifiesto: {rel}")
            continue
        rows.append((f, rel))
    if len(rows) > MAX_FILES:
        errors.append(f"demasiados archivos ({len(rows)} > {MAX_FILES})")
    return rows, errors


def create_own_archive(
    *,
    game_id: str,
    mod: ModEntry,
    stage_root: Path,
    dest_dir: Path,
    compression: int = zipfile.ZIP_DEFLATED,
    compresslevel: int = 6,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
    pause: CancelCb | None = None,
    min_free_bytes: int | None = None,
    game_root: Path | None = None,
    mods_dir: Path | None = None,
    ensure_dest_available: bool = True,
) -> CreateOwnArchiveResult:
    """
    Empaqueta staging → ZIP propio en dest_dir.
    Solo publica tras verificación sandbox completa + origen intacto.
    No modifica staging.
    """
    import time

    t0 = time.perf_counter()
    res = CreateOwnArchiveResult(ok=False, status="PENDIENTE")
    stage_mod = Path(mod.stage_path)
    stage_root = Path(stage_root)
    dest_dir = Path(dest_dir)

    def _wait_pause() -> bool:
        """True si cancelado mientras pausado."""
        while pause and pause():
            if cancel and cancel():
                return True
            time.sleep(0.05)
        return bool(cancel and cancel())

    if not stage_mod.is_dir():
        res.errors.append("origen staging inexistente")
        res.status = "ERROR"
        return res
    if not _is_under(stage_mod, stage_root):
        res.errors.append("la carpeta no pertenece al staging seleccionado")
        res.status = "BLOQUEADO"
        return res

    dest_errs = validate_archive_destination(
        dest_dir, stage_root=stage_root, game_root=game_root, mods_dir=mods_dir
    )
    if dest_errs:
        res.errors.extend(dest_errs)
        res.status = "BLOQUEADO"
        return res

    if ensure_dest_available:
        ok_d, note_d = is_archive_root_available(dest_dir)
        if not ok_d:
            res.errors.append(f"disco/carpeta de archivo no disponible: {note_d}")
            res.status = "ERROR"
            return res

    files, scan_errs = _scan_stage_files(stage_mod)
    if scan_errs and not files:
        res.errors.extend(scan_errs)
        res.status = "ERROR"
        return res
    if any("symlink" in e.lower() or "junction" in e.lower() or "enlace" in e.lower() for e in scan_errs):
        res.errors.extend(scan_errs)
        res.status = "BLOQUEADO"
        return res
    if any("demasiados" in e for e in scan_errs):
        res.errors.extend(scan_errs)
        res.status = "BLOQUEADO"
        return res

    logical = 0
    hashed: list[OwnArchiveFile] = []
    total = len(files)
    try:
        origin_fp = _origin_fingerprint(files)
    except OSError as e:
        res.errors.append(f"no se pudo inventariar origen: {e}")
        res.status = "ERROR"
        return res

    for i, (abs_p, rel) in enumerate(files):
        if _wait_pause():
            res.errors.append("operación cancelada")
            res.status = "ERROR"
            return res
        if progress:
            progress("hasheando", i + 1, total)
        try:
            st = abs_p.stat()
            digest = sha256_file(abs_p)
            logical += st.st_size
            hashed.append(OwnArchiveFile(path=rel, sha256=digest, size=st.st_size))
        except OSError as e:
            res.errors.append(f"no se pudo leer {rel}: {e}")
            res.status = "ERROR"
            return res

    if logical > MAX_UNCOMPRESSED_BYTES:
        res.errors.append("tamaño lógico supera el límite de seguridad")
        res.status = "BLOQUEADO"
        return res

    dest_dir.mkdir(parents=True, exist_ok=True)
    need = max(logical // 2, logical // 4 + 64 * 1024 * 1024)  # estimación conservadora
    if min_free_bytes is not None:
        need = max(need, min_free_bytes)
    try:
        free = shutil.disk_usage(str(dest_dir)).free
        if free < need:
            res.errors.append(
                f"espacio insuficiente (libre={free}, estimado mínimo≈{need})"
            )
            res.status = "BLOQUEADO"
            return res
    except OSError as e:
        res.errors.append(f"no se pudo consultar espacio: {e}")
        res.status = "ERROR"
        return res

    mod_id = make_mod_id(game_id, mod.folder)
    cdig = content_digest(hashed)
    manifest = OwnArchiveManifest(
        format=FORMAT_ID,
        format_version=FORMAT_VERSION,
        package_kind=PACKAGE_KIND,
        game_id=game_id,
        mod_id=mod_id,
        folder=mod.folder,
        display_name=mod.name,
        nexus_id=mod.nexus_id or nexus_id_from_folder(mod.folder),
        created_at=datetime.now().isoformat(timespec="seconds"),
        product_version=__version__,
        variants=list(mod.paks),
        pak_elegido=mod.pak_elegido or "",
        files=hashed,
        total_files=len(hashed),
        total_bytes=logical,
        content_sha256=cdig,
        compression="ZIP_DEFLATED" if compression == zipfile.ZIP_DEFLATED else "ZIP_STORED",
    )

    # nombre de archivo: mod_id (no display name)
    final_name = f"{mod_id}.zip"
    final_path = dest_dir / final_name
    if final_path.exists():
        res.errors.append(f"destino ya existe (no sobrescrito): {final_path.name}")
        res.status = "BLOQUEADO"
        return res

    tmp_fd, tmp_name = tempfile.mkstemp(prefix="sgm_own_", suffix=".zip.partial", dir=str(dest_dir))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    sandbox: Path | None = None
    res.status = "COMPRIMIENDO"

    try:
        if _wait_pause():
            res.errors.append("operación cancelada")
            raise RuntimeError("cancel")

        # disco sigue disponible
        ok_d, note_d = is_archive_root_available(dest_dir)
        if not ok_d:
            res.errors.append(f"disco desconectado durante archivo: {note_d}")
            raise RuntimeError("disk")

        zf_kwargs: dict = {"compression": compression}
        if compression == zipfile.ZIP_DEFLATED:
            zf_kwargs["compresslevel"] = compresslevel
        with zipfile.ZipFile(tmp_path, "w", **zf_kwargs) as zf:
            for i, (abs_p, rel) in enumerate(files):
                if _wait_pause():
                    res.errors.append("operación cancelada")
                    raise RuntimeError("cancel")
                if progress:
                    progress("comprimiendo", i + 1, total)
                if _wait_pause():
                    res.errors.append("operación cancelada")
                    raise RuntimeError("cancel")
                # streaming vía ZipFile.write (no carga entero en RAM)
                zf.write(abs_p, arcname=rel)
            if _wait_pause():
                res.errors.append("operación cancelada")
                raise RuntimeError("cancel")
            man_bytes = json.dumps(
                manifest.to_dict(), ensure_ascii=False, indent=2
            ).encode("utf-8")
            zf.writestr(MANIFEST_ZIP_PATH, man_bytes)

        # origen intacto tras comprimido
        chg = _origin_changed(files, origin_fp, hashed)
        if chg:
            res.errors.extend(chg)
            raise RuntimeError("origin_changed")
        res.origin_unchanged = True

        # integridad ZIP
        res.status = "VERIFICANDO"
        if progress:
            progress("verificando ZIP", 0, 1)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                res.errors.append(f"ZIP corrupto tras escritura: {bad}")
                raise RuntimeError("corrupt")

        # restaurar sandbox y comparar hashes
        if progress:
            progress("verificando sandbox", 0, 1)
        sandbox = Path(tempfile.mkdtemp(prefix="sgm_own_sb_", dir=str(dest_dir)))
        restore = restore_own_archive_to_sandbox(
            tmp_path,
            sandbox_parent=sandbox,
            expect_game_id=game_id,
            expect_mod_id=mod_id,
        )
        if not restore.ok:
            res.errors.extend(restore.errors or ["restauración sandbox falló"])
            raise RuntimeError("restore_fail")

        # comparar SHA con inventario (estructura + hashes)
        for ent in hashed:
            got = sandbox / "content" / ent.path
            if not got.is_file():
                res.errors.append(f"falta en sandbox: {ent.path}")
                raise RuntimeError("mismatch")
            if sha256_file(got) != ent.sha256:
                res.errors.append(f"hash distinto tras restaurar: {ent.path}")
                raise RuntimeError("mismatch")

        # origen intacto otra vez antes de publicar
        chg2 = _origin_changed(files, origin_fp, hashed)
        if chg2:
            res.errors.extend(chg2)
            raise RuntimeError("origin_changed")

        res.verified_restore = True
        # publicar atómico
        if final_path.exists():
            res.errors.append(f"destino ya existe (no sobrescrito): {final_path.name}")
            raise RuntimeError("exists")
        ok_d, note_d = is_archive_root_available(dest_dir)
        if not ok_d:
            res.errors.append(f"disco desconectado antes de publicar: {note_d}")
            raise RuntimeError("disk")
        tmp_path.replace(final_path)
        # confirmar accesible
        if not final_path.is_file():
            res.errors.append("publicación no accesible tras rename")
            raise RuntimeError("publish")
        res.ok = True
        res.status = "ARCHIVADO VERIFICADO"
        res.published_path = str(final_path)
        res.mod_id = mod_id
        res.zip_sha256 = sha256_file(final_path)
        res.zip_size = final_path.stat().st_size
        res.file_count = len(hashed)
        res.logical_bytes = logical
        res.content_sha256 = cdig
        if progress:
            progress("publicado", 1, 1)
    except RuntimeError:
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if res.status not in ("BLOQUEADO",):
            res.status = "ERROR"
    except Exception as e:
        res.errors.append(str(e))
        res.status = "ERROR"
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    finally:
        if sandbox is not None:
            cleanup_sandbox(sandbox)
        if tmp_path.is_file() and not res.ok:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        res.elapsed_s = time.perf_counter() - t0

    return res


def verify_published_own_archive(
    archive: Path,
    *,
    expect_game_id: str | None = None,
    sandbox_parent: Path | None = None,
) -> CreateOwnArchiveResult:
    """Re-verifica un ZIP ya publicado (sandbox). No toca staging."""
    res = CreateOwnArchiveResult(ok=False, status="VERIFICANDO")
    archive = Path(archive)
    if not archive.is_file():
        res.errors.append("archivo no accesible (¿disco desconectado?)")
        res.status = "ERROR"
        return res
    man, errs = read_own_manifest(archive)
    if man is None:
        res.errors.extend(errs)
        res.status = "ERROR"
        return res
    if expect_game_id and man.game_id != expect_game_id:
        res.errors.append("juego incorrecto")
        res.status = "BLOQUEADO"
        return res
    own_tmp = sandbox_parent is None
    parent = Path(sandbox_parent) if sandbox_parent else Path(
        tempfile.mkdtemp(prefix="sgm_reverify_")
    )
    try:
        rs = restore_own_archive_to_sandbox(
            archive,
            sandbox_parent=parent,
            expect_game_id=expect_game_id or man.game_id,
            expect_mod_id=man.mod_id,
        )
        if not rs.ok:
            res.errors.extend(rs.errors)
            res.status = "ERROR"
            return res
        res.ok = True
        res.status = "ARCHIVADO VERIFICADO"
        res.published_path = str(archive)
        res.mod_id = man.mod_id
        res.zip_sha256 = sha256_file(archive)
        res.zip_size = archive.stat().st_size
        res.file_count = man.total_files
        res.logical_bytes = man.total_bytes
        res.content_sha256 = man.content_sha256
        res.verified_restore = True
    finally:
        if own_tmp:
            cleanup_sandbox(parent)
    return res


def read_own_manifest(archive: Path) -> tuple[OwnArchiveManifest | None, list[str]]:
    errs: list[str] = []
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            if MANIFEST_ZIP_PATH not in zf.namelist():
                return None, ["manifiesto SGM ausente (no es ARCHIVO_PROPIO)"]
            raw = zf.read(MANIFEST_ZIP_PATH)
            data = json.loads(raw.decode("utf-8"))
            man = OwnArchiveManifest.from_dict(data)
            if man.format != FORMAT_ID or man.format_version != FORMAT_VERSION:
                return None, ["formato de manifiesto no soportado"]
            if man.package_kind != PACKAGE_KIND:
                return None, ["package_kind inválido"]
            if man.content_sha256 != content_digest(man.files):
                return None, ["content_sha256 del manifiesto no coincide"]
            return man, []
    except zipfile.BadZipFile as e:
        return None, [f"ZIP inválido: {e}"]
    except Exception as e:
        return None, [str(e)]


def restore_own_archive_to_sandbox(
    archive: Path,
    *,
    sandbox_parent: Path | None = None,
    expect_game_id: str | None = None,
    expect_mod_id: str | None = None,
) -> RestoreOwnArchiveResult:
    """Restaura ARCHIVO_PROPIO a sandbox. No toca staging real."""
    res = RestoreOwnArchiveResult(ok=False)
    archive = Path(archive)
    if not archive.is_file():
        res.errors.append("archivo inexistente")
        return res

    man, errs = read_own_manifest(archive)
    if man is None:
        res.errors.extend(errs)
        return res
    res.manifest = man
    if expect_game_id and man.game_id != expect_game_id:
        res.errors.append(
            f"juego incorrecto en manifiesto ({man.game_id} ≠ {expect_game_id})"
        )
        return res
    if expect_mod_id and man.mod_id != expect_mod_id:
        res.errors.append("mod_id incorrecto en manifiesto")
        return res
    if man.total_files > MAX_FILES or len(man.files) > MAX_FILES:
        res.errors.append("manifiesto excede límite de archivos")
        return res
    if man.total_bytes > MAX_UNCOMPRESSED_BYTES:
        res.errors.append("manifiesto excede límite de tamaño")
        return res

    root = Path(sandbox_parent) if sandbox_parent else Path(tempfile.mkdtemp(prefix="sgm_own_rs_"))
    root.mkdir(parents=True, exist_ok=True)
    content = root / "content"
    content.mkdir(parents=True, exist_ok=True)
    res.sandbox = root

    try:
        with zipfile.ZipFile(archive, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                res.errors.append(f"ZIP corrupto: {bad}")
                return res
            by_name = {i.filename.replace("\\", "/"): i for i in zf.infolist() if not i.is_dir()}
            for ent in man.files:
                info = by_name.get(ent.path)
                if info is None:
                    res.errors.append(f"falta miembro: {ent.path}")
                    return res
                try:
                    dest = _safe_join(content, ent.path)
                except ValueError as e:
                    res.errors.append(str(e))
                    return res
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                if dest.is_symlink():
                    res.errors.append(f"symlink bloqueado: {ent.path}")
                    return res
                if dest.stat().st_size != ent.size:
                    res.errors.append(f"tamaño distinto: {ent.path}")
                    return res
                if sha256_file(dest) != ent.sha256:
                    res.errors.append(f"SHA-256 distinto: {ent.path}")
                    return res
                res.files_matched += 1
        res.ok = True
    except Exception as e:
        res.errors.append(str(e))
    return res


def is_archive_root_available(archive_dir: str | Path | None) -> tuple[bool, str]:
    """Disco de archivo conectado / ruta usable."""
    if not archive_dir:
        return False, "carpeta de archivo no configurada"
    p = Path(archive_dir)
    try:
        if not p.exists():
            return False, "disco/ruta de archivo no conectado o inexistente"
        if not p.is_dir():
            return False, "la ruta de archivo no es un directorio"
        # probe escritura
        probe = p / ".sgm_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, "disponible"
    except OSError as e:
        return False, f"no disponible: {e}"
