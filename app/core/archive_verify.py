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

S11 — verificación de recuperabilidad (listado + solape con staging).
No declara recuperable sin prueba verificable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .archive_catalog import (
    ArchiveLinkStatus,
    GameArchiveCatalog,
    ModArchiveEntry,
)
from .archive_extract import (
    cleanup_sandbox,
    extract_to_sandbox,
    list_archive_members,
)
from .hash_cache import sha256_file


@dataclass
class RecoverabilityReport:
    folder: str
    status: str
    recoverable: bool
    note: str
    archive_members: int = 0
    staging_files: int = 0
    overlap: int = 0
    missing_in_archive: list[str] = field(default_factory=list)
    extra_in_archive_sample: list[str] = field(default_factory=list)
    sandbox_ok: bool | None = None
    sandbox_match: bool | None = None


def _basenames(paths: list[str]) -> set[str]:
    return {Path(p).name.lower() for p in paths if p}


def _relset(paths: list[str]) -> set[str]:
    return {p.replace("\\", "/").lower().lstrip("/") for p in paths}


def content_overlap(
    staging_files: list[str], archive_members: list[str]
) -> tuple[int, list[str], list[str]]:
    """Solape por nombre de archivo (basename). Conservador."""
    st = _basenames(staging_files)
    ar = _basenames(archive_members)
    if not st:
        return 0, [], sorted(ar)[:20]
    overlap = st & ar
    missing = sorted(st - ar)
    extra = sorted(ar - st)[:20]
    return len(overlap), missing, extra


def verify_mod_package(
    entry: ModArchiveEntry,
    *,
    deep_extract: bool = False,
    sandbox_parent: Path | None = None,
    min_overlap_ratio: float = 0.85,
) -> RecoverabilityReport:
    """Verifica paquete candidato. deep_extract=True prueba sandbox (ZIP/7z)."""
    rep = RecoverabilityReport(
        folder=entry.folder,
        status=entry.status,
        recoverable=False,
        note="",
        staging_files=len(entry.staging_files),
    )

    if entry.status == ArchiveLinkStatus.SPECIAL_INSTALLER.value or entry.special_installer:
        rep.note = "instalador/herramienta especial no soportada para archivado automático"
        rep.status = ArchiveLinkStatus.SPECIAL_INSTALLER.value
        return rep

    if entry.status == ArchiveLinkStatus.AMBIGUOUS.value:
        rep.note = "correspondencia ambigua; no archivable hasta desambiguar"
        return rep

    if not entry.archive_path:
        rep.status = ArchiveLinkStatus.STAGING_ONLY.value
        rep.note = "sin paquete original vinculado"
        return rep

    arch = Path(entry.archive_path)
    if not arch.is_file():
        rep.status = ArchiveLinkStatus.NOT_FOUND.value
        rep.note = "ruta de paquete inexistente"
        return rep

    # hash del comprimido
    try:
        entry.archive_sha256 = sha256_file(arch)
        entry.archive_size = arch.stat().st_size
    except OSError as e:
        rep.note = f"no se pudo hashear paquete: {e}"
        return rep

    members, errs, tool = list_archive_members(arch)
    if errs and tool == "unsupported":
        rep.note = "; ".join(errs)
        return rep
    if errs and not members:
        rep.note = "; ".join(errs)
        return rep

    rep.archive_members = len(members)
    overlap, missing, extra = content_overlap(entry.staging_files, members)
    rep.overlap = overlap
    rep.missing_in_archive = missing[:40]
    rep.extra_in_archive_sample = extra

    st_n = max(1, len(_basenames(entry.staging_files)))
    ratio = overlap / st_n

    # Transformaciones Vortex: si faltan pocos metadatos ok; si faltan paks no
    critical_missing = [
        m
        for m in missing
        if m.lower().endswith((".pak", ".utoc", ".ucas", ".ba2", ".bsa"))
    ]

    if ratio < min_overlap_ratio or critical_missing:
        rep.status = ArchiveLinkStatus.NOT_FOUND.value
        rep.note = (
            f"contenido no equivalente (solape basename {ratio:.0%}; "
            f"críticos ausentes: {critical_missing[:5]})"
        )
        entry.status = rep.status
        entry.recoverable = False
        entry.recoverable_note = rep.note
        return rep

    # Listado OK → ARCHIVO VERIFICADO (nombres); recuperación aún no demostrada
    rep.status = ArchiveLinkStatus.VERIFIED.value
    entry.status = rep.status
    entry.match_grade = "VERIFICADA"
    entry.package_kind = entry.package_kind or "ORIGINAL_VORTEX"
    entry.lifecycle = "VERIFICADO"
    rep.note = (
        f"paquete vinculado ({tool}): solape basename {ratio:.0%}; "
        f"{arch.name}. Recuperación sandbox pendiente."
    )
    entry.recoverable = None
    entry.recoverable_note = rep.note

    if not deep_extract:
        return rep

    result = extract_to_sandbox(arch, parent=sandbox_parent)
    rep.sandbox_ok = result.ok
    if not result.ok:
        rep.recoverable = False
        rep.note = "listado OK pero extracción sandbox falló: " + "; ".join(
            result.errors[:3]
        )
        entry.recoverable = False
        entry.recoverable_note = rep.note
        cleanup_sandbox(result.sandbox)
        return rep
    sb_names = _basenames(result.files)
    st_names = _basenames(entry.staging_files)
    crit_st = {n for n in st_names if n.endswith((".pak", ".utoc", ".ucas"))}
    if crit_st and not crit_st.issubset(sb_names):
        rep.sandbox_match = False
        rep.recoverable = False
        rep.note = "sandbox no contiene todos los contenedores de staging"
        entry.recoverable = False
        entry.recoverable_note = rep.note
        cleanup_sandbox(result.sandbox)
        return rep
    rep.sandbox_match = True
    cleanup_sandbox(result.sandbox)
    rep.recoverable = True
    rep.note = f"recuperable demostrado en sandbox ({tool}): {arch.name}"
    entry.recoverable = True
    entry.recoverable_note = rep.note
    entry.match_grade = "VERIFICADA"
    return rep


def verify_catalog(
    cat: GameArchiveCatalog,
    *,
    deep_extract: bool = False,
    sandbox_parent: Path | None = None,
    limit: int | None = None,
) -> list[RecoverabilityReport]:
    reports: list[RecoverabilityReport] = []
    mods = cat.mods if limit is None else cat.mods[:limit]
    for entry in mods:
        if entry.status in (
            ArchiveLinkStatus.STAGING_ONLY.value,
            ArchiveLinkStatus.AMBIGUOUS.value,
            ArchiveLinkStatus.SPECIAL_INSTALLER.value,
        ) and not entry.archive_path:
            reports.append(
                RecoverabilityReport(
                    folder=entry.folder,
                    status=entry.status,
                    recoverable=False,
                    note=entry.match_reason or entry.status,
                    staging_files=len(entry.staging_files),
                )
            )
            entry.recoverable = False
            entry.recoverable_note = reports[-1].note
            continue
        reports.append(
            verify_mod_package(
                entry,
                deep_extract=deep_extract,
                sandbox_parent=sandbox_parent,
            )
        )
    return reports
