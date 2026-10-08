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

S28 — inspección de rutas y ZIP sin escritura ni extracción.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

WIN_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_ZIP_ENTRIES = 50_000
MAX_ZIP_UNCOMPRESSED = 8 * 1024 * 1024 * 1024  # 8 GiB acumulado declarado
MAX_COMPRESSION_RATIO = 200.0
MAX_PATH_DEPTH = 40


@dataclass
class PathSafetyIssue:
    code: str
    message: str
    path: str = ""
    confirmed: bool = True  # False = advertencia heurística


@dataclass
class ZipSafetyReport:
    path: str
    ok: bool
    issues: list[PathSafetyIssue] = field(default_factory=list)
    entry_count: int = 0
    uncompressed_declared: int = 0


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").strip()


def check_relative_path(rel: str, *, base_hint: str = "") -> list[PathSafetyIssue]:
    """Valida una ruta relativa candidata a instalación (sin I/O)."""
    issues: list[PathSafetyIssue] = []
    raw = _norm_rel(rel)
    if not raw:
        issues.append(PathSafetyIssue("EMPTY", "Ruta vacía", raw))
        return issues
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        issues.append(
            PathSafetyIssue("ABSOLUTE", "Ruta absoluta no permitida", raw, True)
        )
    if ".." in PurePosixPath(raw).parts or ".." in PureWindowsPath(raw).parts:
        issues.append(
            PathSafetyIssue("TRAVERSAL", "Path traversal (..)", raw, True)
        )
    parts = PurePosixPath(raw).parts
    if len(parts) > MAX_PATH_DEPTH:
        issues.append(
            PathSafetyIssue(
                "DEPTH",
                f"Profundidad excesiva ({len(parts)} > {MAX_PATH_DEPTH})",
                raw,
                True,
            )
        )
    for part in parts:
        stem = Path(part).stem.upper()
        if stem in WIN_RESERVED:
            issues.append(
                PathSafetyIssue(
                    "RESERVED",
                    f"Nombre reservado Windows: {part}",
                    raw,
                    True,
                )
            )
        if part.endswith(" ") or part.endswith("."):
            issues.append(
                PathSafetyIssue(
                    "WIN_TRAIL",
                    "Nombre con espacio/punto final (problemático en Windows)",
                    raw,
                    False,
                )
            )
    # Colisión potencial por case-fold (advertencia)
    if base_hint and raw != raw.lower() and raw.lower() == base_hint.lower() and raw != base_hint:
        issues.append(
            PathSafetyIssue(
                "CASE_COLLISION",
                "Posible colisión por mayúsculas/minúsculas",
                raw,
                False,
            )
        )
    return issues


def check_fs_path(path: Path, *, root: Path | None = None) -> list[PathSafetyIssue]:
    """Inspección ligera de un path existente (symlink / reparse). No sigue enlaces."""
    issues: list[PathSafetyIssue] = []
    try:
        if path.is_symlink():
            issues.append(
                PathSafetyIssue(
                    "SYMLINK",
                    "Enlace simbólico / reparse detectado",
                    str(path),
                    True,
                )
            )
    except OSError as e:
        issues.append(
            PathSafetyIssue("STAT_ERROR", f"No se pudo inspeccionar: {e}", str(path), True)
        )
    if root is not None:
        try:
            path.resolve().relative_to(root.resolve())
        except Exception:
            issues.append(
                PathSafetyIssue(
                    "OUTSIDE_ROOT",
                    "Ruta fuera del directorio raíz del mod",
                    str(path),
                    True,
                )
            )
    return issues


def inspect_zip(path: Path) -> ZipSafetyReport:
    """Lee metadatos del ZIP sin extraer. No escribe en disco."""
    report = ZipSafetyReport(path=str(path), ok=True)
    if not path.is_file():
        report.ok = False
        report.issues.append(
            PathSafetyIssue("MISSING", "ZIP no encontrado", str(path), True)
        )
        return report
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            report.entry_count = len(infos)
            if report.entry_count > MAX_ZIP_ENTRIES:
                report.ok = False
                report.issues.append(
                    PathSafetyIssue(
                        "ZIP_ENTRIES",
                        f"Demasiadas entradas ({report.entry_count})",
                        str(path),
                        True,
                    )
                )
            seen_fold: dict[str, str] = {}
            total_uncomp = 0
            for info in infos:
                name = info.filename
                total_uncomp += max(0, int(info.file_size))
                for iss in check_relative_path(name):
                    report.issues.append(iss)
                    if iss.confirmed:
                        report.ok = False
                # Zip-slip clásico
                if name.replace("\\", "/").startswith("../") or "/../" in name.replace(
                    "\\", "/"
                ):
                    report.ok = False
                    report.issues.append(
                        PathSafetyIssue("ZIP_SLIP", "Entrada ZIP con traversal", name, True)
                    )
                fold = name.replace("\\", "/").lower()
                if fold in seen_fold and seen_fold[fold] != name:
                    report.issues.append(
                        PathSafetyIssue(
                            "ZIP_CASE_DUP",
                            f"Entradas duplicadas por case: {seen_fold[fold]} vs {name}",
                            name,
                            False,
                        )
                    )
                else:
                    seen_fold[fold] = name
                if info.file_size > 0 and info.compress_size > 0:
                    ratio = info.file_size / max(1, info.compress_size)
                    if ratio >= MAX_COMPRESSION_RATIO and info.file_size > 50 * 1024 * 1024:
                        report.issues.append(
                            PathSafetyIssue(
                                "ZIP_BOMB_HINT",
                                f"Ratio de compresión sospechoso ({ratio:.0f}:1)",
                                name,
                                False,
                            )
                        )
            report.uncompressed_declared = total_uncomp
            if total_uncomp > MAX_ZIP_UNCOMPRESSED:
                report.ok = False
                report.issues.append(
                    PathSafetyIssue(
                        "ZIP_SIZE",
                        "Tamaño descomprimido declarado excesivo",
                        str(path),
                        True,
                    )
                )
    except zipfile.BadZipFile:
        report.ok = False
        report.issues.append(
            PathSafetyIssue("ZIP_BAD", "ZIP corrupto o no válido", str(path), True)
        )
    except OSError as e:
        report.ok = False
        report.issues.append(
            PathSafetyIssue("ZIP_IO", f"Error leyendo ZIP: {e}", str(path), True)
        )
    return report
