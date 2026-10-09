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

S27 — dimensiones de estado de biblioteca (independientes; solo lectura).
No implica Enabled histórico de Vortex ni escritura en disco.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing import TYPE_CHECKING

from .inventory import ModEntry

if TYPE_CHECKING:
    from .vortex_mod_context import ModIntelligence

# Dimensiones públicas (pueden coexistir)
INSTALADO_REAL = "INSTALADO_REAL"
ACTIVO_EN_PLAN = "ACTIVO_EN_PLAN"
ARCHIVADO_VERIFICADO = "ARCHIVADO_VERIFICADO"
DISPONIBLE_EN_WORK = "DISPONIBLE_EN_WORK"
STAGING_VORTEX = "STAGING_VORTEX"
PENDIENTE_VORTEX = "PENDIENTE_VORTEX"
CONFLICTO = "CONFLICTO"
VARIANTE_PENDIENTE = "VARIANTE_PENDIENTE"
NO_DISPONIBLE = "NO_DISPONIBLE"
# S28 — dimensiones de estructura (opcional; si hay informe)
ESTRUCTURA_INCOMPLETA = "ESTRUCTURA_INCOMPLETA"
ESTRUCTURA_REVISION = "ESTRUCTURA_REVISION"
ESTRUCTURA_NO_SOPORTADA = "ESTRUCTURA_NO_SOPORTADA"
ESTRUCTURA_BLOQUEO = "ESTRUCTURA_BLOQUEO"
FORMATO_UE4_PAK = "FORMATO_UE4_PAK"
FORMATO_UE5_IOSTORE = "FORMATO_UE5_IOSTORE"
FORMATO_GENERICO = "FORMATO_GENERICO"
# S44 — capas Vortex / F7777 (independientes)
VORTEX_ENABLED_HISTORICO = "VORTEX_ENABLED_HISTORICO"
VORTEX_ENABLED_VERIFICADO = "VORTEX_ENABLED_VERIFICADO"
GESTIONADO_F7777 = "GESTIONADO_F7777"
COMPAT_DESCONOCIDA = "COMPAT_DESCONOCIDA"
VORTEX_AUX_LOADORDER = "VORTEX_AUX_LOADORDER"

ALL_FLAGS = (
    INSTALADO_REAL,
    ACTIVO_EN_PLAN,
    ARCHIVADO_VERIFICADO,
    DISPONIBLE_EN_WORK,
    STAGING_VORTEX,
    PENDIENTE_VORTEX,
    CONFLICTO,
    VARIANTE_PENDIENTE,
    NO_DISPONIBLE,
    ESTRUCTURA_INCOMPLETA,
    ESTRUCTURA_REVISION,
    ESTRUCTURA_NO_SOPORTADA,
    ESTRUCTURA_BLOQUEO,
    FORMATO_UE4_PAK,
    FORMATO_UE5_IOSTORE,
    FORMATO_GENERICO,
    VORTEX_ENABLED_HISTORICO,
    VORTEX_ENABLED_VERIFICADO,
    GESTIONADO_F7777,
    COMPAT_DESCONOCIDA,
    VORTEX_AUX_LOADORDER,
)

# Filtros de UI (etiqueta → predicado sobre flags / mod)
FILTER_ALL = "TODOS"


@dataclass(frozen=True)
class ModStatusView:
    """Vista de estados independientes para un mod."""

    flags: frozenset[str]
    row_label: str
    row_tag: str

    def has(self, flag: str) -> bool:
        return flag in self.flags


def _conflict_serious(m: ModEntry) -> bool:
    c = (m.conflicto or "").strip()
    if not c:
        return False
    return any(
        x in c for x in ("Choque", "Falta", "CONFLICTO", "VARIANT", "AJENO", "BLOQUE")
    )


def _pendiente_vortex_hint(m: ModEntry) -> bool:
    """Heurística de UI: texto de conflicto/liberación; no lee Vortex en vivo."""
    c = (m.conflicto or "").upper()
    return "PENDIENTE_VORTEX" in c or "PENDIENTE VORTEX" in c


def compute_mod_status(
    m: ModEntry,
    *,
    structure_report: object | None = None,
    intel: ModIntelligence | None = None,
) -> ModStatusView:
    flags: set[str] = set()
    src = (getattr(m, "source_kind", "") or "").upper()

    if m.on_disk:
        flags.add(INSTALADO_REAL)
    if m.usar:
        flags.add(ACTIVO_EN_PLAN)

    # S28 — informe de estructura (opcional)
    if structure_report is not None:
        cls = str(getattr(structure_report, "classification", "") or "")
        if cls == "INCOMPLETO":
            flags.add(ESTRUCTURA_INCOMPLETA)
        if cls == "NO_SOPORTADO":
            flags.add(ESTRUCTURA_NO_SOPORTADA)
        if bool(getattr(structure_report, "needs_manual_review", False)):
            flags.add(ESTRUCTURA_REVISION)
        if bool(getattr(structure_report, "blocks_prepare", False)):
            flags.add(ESTRUCTURA_BLOQUEO)
        fmt = str(getattr(structure_report, "format_label", "") or "").lower()
        if "ue4" in fmt or "pak (.pak)" in fmt:
            flags.add(FORMATO_UE4_PAK)
        elif "iostore" in fmt or "ue5" in fmt:
            flags.add(FORMATO_UE5_IOSTORE)
        elif "genéric" in fmt or "generic" in fmt or "carpeta" in fmt:
            flags.add(FORMATO_GENERICO)

    archived = bool(getattr(m, "archived", False))
    has_hash = bool(
        (getattr(m, "archive_content_sha256", "") or "").strip()
        or (getattr(m, "archive_zip_sha256", "") or "").strip()
    )
    arch_path = (getattr(m, "archive_path", "") or "").strip()
    if archived and (has_hash or arch_path):
        flags.add(ARCHIVADO_VERIFICADO)
    elif archived:
        # Marcado archivado sin hash aún: sigue siendo señal de archivo propio
        flags.add(ARCHIVADO_VERIFICADO)

    if getattr(m, "work_extracted", False) or src == "WORK_LIBRARY":
        flags.add(DISPONIBLE_EN_WORK)

    stage = (m.stage_path or "").strip()
    stage_ok = bool(stage and Path(stage).is_dir()) if stage else False
    if src == "STAGING_VORTEX" or (stage_ok and "WORK" not in src):
        flags.add(STAGING_VORTEX)

    if _pendiente_vortex_hint(m):
        flags.add(PENDIENTE_VORTEX)

    if m.usar and m.multi:
        from .component_selection import selection_pending

        if selection_pending(m):
            flags.add(VARIANTE_PENDIENTE)
    if m.usar and _conflict_serious(m):
        flags.add(CONFLICTO)

    if intel is not None:
        if intel.vortex_enabled_verified is True:
            flags.add(VORTEX_ENABLED_VERIFICADO)
        if intel.vortex_enabled_historical is True:
            flags.add(VORTEX_ENABLED_HISTORICO)
        if intel.managed_f7777:
            flags.add(GESTIONADO_F7777)
        if intel.compat_unknown and m.paks:
            flags.add(COMPAT_DESCONOCIDA)
        if intel.aux.load_order_index is not None:
            flags.add(VORTEX_AUX_LOADORDER)

    has_source = (
        INSTALADO_REAL in flags
        or DISPONIBLE_EN_WORK in flags
        or STAGING_VORTEX in flags
        or ARCHIVADO_VERIFICADO in flags
        or stage_ok
        or bool(m.paks)
    )
    if not has_source:
        flags.add(NO_DISPONIBLE)

    # Etiqueta de fila (prioridad visual; no colapsa dimensiones)
    if VARIANTE_PENDIENTE in flags:
        row_tag, row_label = "pending", "Variante pendiente"
    elif CONFLICTO in flags:
        row_tag, row_label = "conflict", (m.conflicto or "CONFLICTO")[:40]
    elif ACTIVO_EN_PLAN in flags and INSTALADO_REAL in flags:
        row_tag, row_label = "active_inst", "Plan SI + destino ON"
    elif ACTIVO_EN_PLAN in flags:
        row_tag, row_label = "active", "Activo en plan"
    elif INSTALADO_REAL in flags:
        row_tag, row_label = "installed", "Destino ON (plan NO)"
    elif ARCHIVADO_VERIFICADO in flags and DISPONIBLE_EN_WORK not in flags:
        row_tag, row_label = "off", "Archivado ZIP"
    elif DISPONIBLE_EN_WORK in flags:
        row_tag, row_label = "off", "En WORK"
    elif NO_DISPONIBLE in flags:
        row_tag, row_label = "off", "No disponible"
    else:
        row_tag, row_label = "off", "Desactivado"

    return ModStatusView(flags=frozenset(flags), row_label=row_label, row_tag=row_tag)


def status_badges_text(st: ModStatusView) -> str:
    order = [
        INSTALADO_REAL,
        ACTIVO_EN_PLAN,
        ARCHIVADO_VERIFICADO,
        DISPONIBLE_EN_WORK,
        STAGING_VORTEX,
        PENDIENTE_VORTEX,
        CONFLICTO,
        VARIANTE_PENDIENTE,
        NO_DISPONIBLE,
        VORTEX_ENABLED_HISTORICO,
        VORTEX_ENABLED_VERIFICADO,
        GESTIONADO_F7777,
        COMPAT_DESCONOCIDA,
        VORTEX_AUX_LOADORDER,
    ]
    present = [f for f in order if f in st.flags]
    if not present:
        return "(sin flags)"
    return " · ".join(present)


def mod_matches_query(m: ModEntry, query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    blob = (
        f"{m.name} {m.description} {m.category} {' '.join(m.paks)} "
        f"{m.folder} {m.author} {m.nexus_mod_name}"
    ).lower()
    # Búsqueda parcial: todas las palabras deben aparecer
    return all(part in blob for part in q.split())


def mod_matches_dimension_filter(m: ModEntry, st: ModStatusView, filt: str) -> bool:
    """Filtro por dimensión / legado S20. ``filt`` es etiqueta de menú."""
    if not filt or filt == FILTER_ALL:
        return True
    # Dimensiones S27
    mapping = {
        "INSTALADO_REAL": INSTALADO_REAL,
        "ACTIVO_EN_PLAN": ACTIVO_EN_PLAN,
        "ARCHIVADO_VERIFICADO": ARCHIVADO_VERIFICADO,
        "DISPONIBLE_EN_WORK": DISPONIBLE_EN_WORK,
        "STAGING_VORTEX": STAGING_VORTEX,
        "PENDIENTE_VORTEX": PENDIENTE_VORTEX,
        "CONFLICTO": CONFLICTO,
        "VARIANTE_PENDIENTE": VARIANTE_PENDIENTE,
        "NO_DISPONIBLE": NO_DISPONIBLE,
        # Etiquetas legibles
        "Instalado real": INSTALADO_REAL,
        "Activo en plan": ACTIVO_EN_PLAN,
        "Archivado ZIP": ARCHIVADO_VERIFICADO,
        "En WORK": DISPONIBLE_EN_WORK,
        "Staging Vortex": STAGING_VORTEX,
        "Pendiente Vortex": PENDIENTE_VORTEX,
        "Con conflictos": CONFLICTO,
        "Variante pendiente": VARIANTE_PENDIENTE,
        "No disponible": NO_DISPONIBLE,
        "Paquete incompleto": ESTRUCTURA_INCOMPLETA,
        "Revisión manual": ESTRUCTURA_REVISION,
        "No soportado": ESTRUCTURA_NO_SOPORTADA,
        "Bloqueo estructura": ESTRUCTURA_BLOQUEO,
        "Con variantes": VARIANTE_PENDIENTE,
        "Formato UE4 PAK": FORMATO_UE4_PAK,
        "Formato UE5 IoStore": FORMATO_UE5_IOSTORE,
        "Formato genérico": FORMATO_GENERICO,
        "Enabled Vortex (hist.)": VORTEX_ENABLED_HISTORICO,
        "Enabled Vortex (verif.)": VORTEX_ENABLED_VERIFICADO,
        "Gestionado F7777": GESTIONADO_F7777,
        "Compat. desconocida": COMPAT_DESCONOCIDA,
        "Load order Vortex (aux)": VORTEX_AUX_LOADORDER,
    }
    if filt in mapping:
        return st.has(mapping[filt])
    # Compatibilidad filtros S20
    if filt == "Activos":
        return bool(m.usar)
    if filt == "Desactivados":
        return not m.usar
    if filt == "Conflictos":
        return st.has(CONFLICTO)
    if filt == "En destino":
        return st.has(INSTALADO_REAL)
    if filt == "No instalados":
        return not st.has(INSTALADO_REAL)
    if filt == "Archivados ZIP":
        return st.has(ARCHIVADO_VERIFICADO)
    if filt == "Pendiente Apply":
        return st.has(ACTIVO_EN_PLAN) and not st.has(INSTALADO_REAL)
    return True


def filter_mods(
    mods: list[ModEntry],
    *,
    query: str = "",
    dimension: str = FILTER_ALL,
    source: str = "TODAS",
    character: str = "TODOS",
    tag: str = "TODAS",
    structure_by_folder: dict[str, object] | None = None,
    intel_by_folder: dict[str, object] | None = None,
) -> list[ModEntry]:
    """Filtrado puro (sin I/O). Apto para inventarios grandes en tests."""
    out: list[ModEntry] = []
    for m in mods:
        if character not in ("", "TODOS") and m.character_main != character:
            continue
        if tag and tag not in ("", "TODAS"):
            from .library_catalog_model import mod_matches_tag

            if not mod_matches_tag(m, tag):
                continue
        src = (getattr(m, "source_kind", "") or "STAGING_VORTEX").upper()
        if source == "VORTEX" and "WORK" in src:
            continue
        if source == "WORK" and "WORK" not in src:
            continue
        rep = None
        if structure_by_folder is not None:
            rep = structure_by_folder.get(m.folder)
        intel = None
        if intel_by_folder is not None:
            intel = intel_by_folder.get(m.folder)
        st = compute_mod_status(m, structure_report=rep, intel=intel)
        if not mod_matches_dimension_filter(m, st, dimension):
            continue
        if not mod_matches_query(m, query):
            continue
        out.append(m)
    return out


def archive_candidates(mods: list[ModEntry]) -> list[ModEntry]:
    """Candidatos a archivar: en staging, sin ZIP verificado (solo selección)."""
    out = []
    for m in mods:
        st = compute_mod_status(m)
        if st.has(STAGING_VORTEX) and not st.has(ARCHIVADO_VERIFICADO):
            out.append(m)
    return out


def work_restore_candidates(mods: list[ModEntry]) -> list[ModEntry]:
    """Candidatos a restaurar a WORK: archivados sin copia WORK."""
    out = []
    for m in mods:
        st = compute_mod_status(m)
        if st.has(ARCHIVADO_VERIFICADO) and not st.has(DISPONIBLE_EN_WORK):
            out.append(m)
    return out
