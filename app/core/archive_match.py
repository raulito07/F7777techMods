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

S12 — grados de correspondencia Vortex (nunca PROBABLE → VERIFICADA sin prueba).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .archive_catalog import (
    ArchiveLinkStatus,
    GameArchiveCatalog,
    ModArchiveEntry,
    PackagedFile,
)
from .archive_extract import list_archive_members
from .archive_verify import content_overlap
from .inventory import ModEntry, nexus_id_from_folder


class MatchGrade(str, Enum):
    VERIFICADA = "VERIFICADA"
    PROBABLE = "PROBABLE"
    AMBIGUA = "AMBIGUA"
    NO_ENCONTRADA = "NO ENCONTRADA"


class PackageKind(str, Enum):
    ORIGINAL_VORTEX = "ORIGINAL_VORTEX"
    ARCHIVO_PROPIO = "ARCHIVO_PROPIO"


class LifecycleState(str, Enum):
    COMPRIMIDO = "COMPRIMIDO"
    VERIFICADO = "VERIFICADO"
    ARCHIVADO = "ARCHIVADO"
    EXTRAIDO = "EXTRAIDO"
    NO_DISPONIBLE = "NO DISPONIBLE"


@dataclass
class MatchDetail:
    grade: str
    reasons: list[str]
    package_path: str = ""
    overlap: int = 0
    staging_files: int = 0


def classify_vortex_match(
    entry: ModArchiveEntry,
    *,
    deep_list: bool = False,
    min_overlap_ratio: float = 0.85,
) -> MatchDetail:
    """
    Clasifica correspondencia con ORIGINAL_VORTEX.
    VERIFICADA solo con listado de contenido y solape suficiente.
    """
    if entry.special_installer or entry.status == ArchiveLinkStatus.SPECIAL_INSTALLER.value:
        return MatchDetail(
            grade=MatchGrade.NO_ENCONTRADA.value,
            reasons=["instalador especial / no usable como original recuperable"],
        )
    if entry.status == ArchiveLinkStatus.AMBIGUOUS.value:
        return MatchDetail(
            grade=MatchGrade.AMBIGUA.value,
            reasons=[entry.match_reason or "varios candidatos"],
        )
    if not entry.archive_path:
        return MatchDetail(
            grade=MatchGrade.NO_ENCONTRADA.value,
            reasons=[entry.match_reason or "sin paquete Vortex vinculado"],
        )

    arch = Path(entry.archive_path)
    reasons = [entry.match_reason] if entry.match_reason else []
    if not arch.is_file():
        return MatchDetail(
            grade=MatchGrade.NO_ENCONTRADA.value,
            reasons=reasons + ["ruta de paquete inexistente"],
            package_path=str(arch),
        )

    # Sin listado de contenido → como máximo PROBABLE
    if not deep_list:
        return MatchDetail(
            grade=MatchGrade.PROBABLE.value,
            reasons=reasons + ["candidato único; falta verificación de contenido"],
            package_path=str(arch),
            staging_files=len(entry.staging_files),
        )

    members, errs, tool = list_archive_members(arch)
    if errs and not members:
        return MatchDetail(
            grade=MatchGrade.PROBABLE.value,
            reasons=reasons + [f"no se pudo listar ({tool}): {'; '.join(errs)[:120]}"],
            package_path=str(arch),
        )

    overlap, missing, _extra = content_overlap(entry.staging_files, members)
    st_n = max(1, len({Path(p).name.lower() for p in entry.staging_files}))
    ratio = overlap / st_n
    critical_missing = [
        m
        for m in missing
        if m.lower().endswith((".pak", ".utoc", ".ucas", ".ba2", ".bsa"))
    ]
    if ratio >= min_overlap_ratio and not critical_missing:
        return MatchDetail(
            grade=MatchGrade.VERIFICADA.value,
            reasons=reasons
            + [f"solape basename {ratio:.0%} vía {tool}; contenido equivalente"],
            package_path=str(arch),
            overlap=overlap,
            staging_files=len(entry.staging_files),
        )
    return MatchDetail(
        grade=MatchGrade.PROBABLE.value,
        reasons=reasons
        + [
            f"candidato único pero contenido insuficiente "
            f"(solape {ratio:.0%}; críticos ausentes={critical_missing[:3]})"
        ],
        package_path=str(arch),
        overlap=overlap,
        staging_files=len(entry.staging_files),
    )


def apply_match_grades(
    cat: GameArchiveCatalog,
    *,
    verify_content: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """Actualiza match_grade / package_kind / lifecycle en el catálogo."""
    counts = {
        MatchGrade.VERIFICADA.value: 0,
        MatchGrade.PROBABLE.value: 0,
        MatchGrade.AMBIGUA.value: 0,
        MatchGrade.NO_ENCONTRADA.value: 0,
    }
    mods = cat.mods if limit is None else cat.mods[:limit]
    for entry in mods:
        if entry.own_archive_path and Path(entry.own_archive_path).is_file():
            entry.package_kind = PackageKind.ARCHIVO_PROPIO.value
        # No degradar un listado/sandbox ya VERIFICADO con un pase superficial
        if (
            not verify_content
            and entry.match_grade == MatchGrade.VERIFICADA.value
            and entry.status == ArchiveLinkStatus.VERIFIED.value
        ):
            counts[MatchGrade.VERIFICADA.value] = (
                counts.get(MatchGrade.VERIFICADA.value, 0) + 1
            )
            continue
        detail = classify_vortex_match(entry, deep_list=verify_content)
        entry.match_grade = detail.grade
        counts[detail.grade] = counts.get(detail.grade, 0) + 1
        if entry.archive_path and not entry.package_kind:
            entry.package_kind = PackageKind.ORIGINAL_VORTEX.value
        # Solo VERIFICADA cuenta como recuperable vía original (aún hace falta deep sandbox
        # para marcar recoverable=True; aquí no lo forzamos).
        if detail.grade == MatchGrade.VERIFICADA.value:
            entry.status = ArchiveLinkStatus.VERIFIED.value
            entry.lifecycle = LifecycleState.VERIFICADO.value
            if entry.recoverable is None:
                entry.recoverable_note = (
                    "correspondencia VERIFICADA con original; "
                    "falta demo sandbox para archivable"
                )
        elif detail.grade == MatchGrade.AMBIGUA.value:
            entry.status = ArchiveLinkStatus.AMBIGUOUS.value
            entry.lifecycle = LifecycleState.EXTRAIDO.value
            entry.recoverable = False
            entry.recoverable_note = "correspondencia AMBIGUA — no recuperable vía original"
        elif detail.grade == MatchGrade.PROBABLE.value:
            # Nunca elevar a VERIFICADA sin prueba de contenido
            if entry.status != ArchiveLinkStatus.VERIFIED.value:
                entry.lifecycle = LifecycleState.EXTRAIDO.value
            if entry.recoverable is not True:
                entry.recoverable_note = (
                    "PROBABLE: no archivable vía original hasta VERIFICADA + sandbox"
                )
        else:
            if not entry.own_archive_path:
                entry.lifecycle = LifecycleState.EXTRAIDO.value
            if entry.recoverable is not True and not entry.own_archive_path:
                entry.recoverable_note = entry.recoverable_note or "sin original VERIFICADO"
    # procesar resto sin verify si hubo limit
    if limit is not None:
        for entry in cat.mods[limit:]:
            if not entry.match_grade:
                detail = classify_vortex_match(entry, deep_list=False)
                entry.match_grade = detail.grade
                if entry.archive_path and not entry.package_kind:
                    entry.package_kind = PackageKind.ORIGINAL_VORTEX.value
    return counts


def enrich_from_vortex_meta(
    mods: list[ModEntry], meta: dict | None
) -> int:
    """Aplica metadatos Vortex/Nexus si el JSON local los tiene. No escribe Vortex."""
    if not meta or not isinstance(meta, dict):
        return 0
    # estructuras tolerantes: {folder: {...}} o {mods: [...]}
    by_folder: dict[str, dict] = {}
    if isinstance(meta.get("mods"), list):
        for row in meta["mods"]:
            if isinstance(row, dict) and row.get("folder"):
                by_folder[str(row["folder"])] = row
    else:
        for k, v in meta.items():
            if isinstance(v, dict):
                by_folder[str(k)] = v
    n = 0
    for m in mods:
        row = by_folder.get(m.folder)
        if not row:
            continue
        nid = row.get("nexus_id") or row.get("modId") or row.get("domain_mod_id")
        if nid and not m.nexus_id:
            m.nexus_id = str(nid)
            n += 1
        if row.get("modName") and not m.nexus_mod_name:
            m.nexus_mod_name = str(row["modName"])
        if row.get("author") and not m.author:
            m.author = str(row["author"])
    return n


def package_size_hint(packages: list[PackagedFile], nexus_id: str | None) -> int | None:
    if not nexus_id:
        return None
    sizes = [p.size for p in packages if p.nexus_id == nexus_id]
    if len(sizes) == 1:
        return sizes[0]
    return None
