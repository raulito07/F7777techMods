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

S11 — plan de archivado en SIMULACIÓN (no borra staging ni mueve downloads).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .archive_catalog import ArchiveLinkStatus, GameArchiveCatalog, ModArchiveEntry
from .install_modes import same_file
from .inventory import ModEntry


@dataclass
class ArchivePlanRow:
    folder: str
    name: str
    staging_logical: int
    has_package: bool
    integrity_ok: bool
    recoverable: bool
    hardlinks: int
    blocked: bool
    block_reason: str
    reclaimable_logical: int


@dataclass
class ArchiveSimulation:
    game_id: str
    rows: list[ArchivePlanRow] = field(default_factory=list)
    reclaimable_total: int = 0
    archivable_count: int = 0
    blocked_count: int = 0
    warnings: list[str] = field(default_factory=list)
    archive_dir: str = ""
    archive_dir_free: int | None = None
    note: str = (
        "SIMULACIÓN — no se ha borrado staging ni movido Downloads. "
        "Archivado real pendiente de autorización explícita."
    )


@dataclass
class TransferPlan:
    """Plan de traslado a carpeta de archivo (no ejecuta)."""

    sources: list[str] = field(default_factory=list)
    dest_dir: str = ""
    total_bytes: int = 0
    duplicates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    executable: bool = False  # siempre False en S11


def _count_hardlinks_to_mods(
    stage_path: Path, mods_dir: Path | None
) -> int:
    if mods_dir is None or not mods_dir.is_dir() or not stage_path.is_dir():
        return 0
    n = 0
    try:
        for f in stage_path.rglob("*"):
            if not f.is_file():
                continue
            # buscar samefile en destino por nombre (coste acotado)
            dest = mods_dir / f.name
            if dest.is_file() and same_file(f, dest):
                n += 1
    except OSError:
        return n
    return n


def simulate_archive_plan(
    cat: GameArchiveCatalog,
    mods: list[ModEntry],
    *,
    mods_dir: Path | None = None,
    pending_ops: bool = False,
) -> ArchiveSimulation:
    """Genera plan de liberación de staging. No modifica disco de juego/Vortex."""
    sim = ArchiveSimulation(game_id=cat.game_id)
    by_folder = {m.folder: m for m in mods}
    if pending_ops:
        sim.warnings.append("Hay operaciones pendientes — archivado bloqueado globalmente.")

    for entry in cat.mods:
        m = by_folder.get(entry.folder)
        stage = Path(m.stage_path) if m else None
        hl = _count_hardlinks_to_mods(stage, mods_dir) if stage else 0
        blocked = False
        reasons: list[str] = []

        if pending_ops:
            blocked = True
            reasons.append("operación pendiente")
        if entry.status == ArchiveLinkStatus.AMBIGUOUS.value:
            blocked = True
            reasons.append("correspondencia ambigua")
        has_own_ok = bool(
            entry.own_archive_path
            and entry.recoverable is True
            and (entry.package_kind == "ARCHIVO_PROPIO" or entry.lifecycle == "VERIFICADO")
        )
        if entry.status in (
            ArchiveLinkStatus.STAGING_ONLY.value,
            ArchiveLinkStatus.NOT_FOUND.value,
        ) and not has_own_ok:
            blocked = True
            reasons.append("sin paquete recuperable verificado")
        if entry.status == ArchiveLinkStatus.SPECIAL_INSTALLER.value:
            blocked = True
            reasons.append("instalador especial no soportado")
        if (
            entry.match_grade == "PROBABLE"
            and entry.recoverable is not True
            and not has_own_ok
        ):
            blocked = True
            reasons.append("correspondencia solo PROBABLE (no VERIFICADA)")
        if entry.recoverable is False:
            blocked = True
            reasons.append(entry.recoverable_note or "no recuperable")
        if (
            entry.recoverable is None
            and entry.status != ArchiveLinkStatus.VERIFIED.value
            and not has_own_ok
        ):
            blocked = True
            reasons.append("recuperabilidad no demostrada")
        if entry.recoverable is None and entry.status == ArchiveLinkStatus.VERIFIED.value:
            # verificado por listado pero sin deep — aún no seguro para borrar
            blocked = True
            reasons.append(
                "falta prueba de restauración sandbox (regla: no eliminar sin demostrar)"
            )
        if hl > 0:
            blocked = True
            reasons.append(f"{hl} hardlink(s) hacia destino sin estrategia segura")

        # Regla final: archivable solo si recoverable==True
        if entry.recoverable is not True:
            blocked = True
            if "recuperabilidad" not in ";".join(reasons).lower() and "sandbox" not in ";".join(reasons).lower():
                reasons.append("recuperabilidad no demostrada (regla final S12)")

        reclaim = 0 if blocked else int(entry.staging_logical_size)
        row = ArchivePlanRow(
            folder=entry.folder,
            name=entry.name,
            staging_logical=entry.staging_logical_size,
            has_package=bool(entry.archive_path),
            integrity_ok=entry.status == ArchiveLinkStatus.VERIFIED.value,
            recoverable=bool(entry.recoverable),
            hardlinks=hl,
            blocked=blocked,
            block_reason="; ".join(reasons) if reasons else "",
            reclaimable_logical=reclaim,
        )
        sim.rows.append(row)
        if blocked:
            sim.blocked_count += 1
        else:
            sim.archivable_count += 1
            sim.reclaimable_total += reclaim

    sim.warnings.append(
        "Ningún archivo extraído es seguro para eliminar hasta demostrar "
        "recuperación desde su paquete conservado."
    )
    sim.warnings.append(
        "Mover paquetes fuera de Downloads puede hacer que Vortex deje de "
        "reconocerlos para gestión/actualización."
    )
    return sim


def plan_transfer_to_archive_dir(
    packages: list[str],
    dest_dir: Path,
) -> TransferPlan:
    """Planifica traslado (no ejecuta). Detecta duplicados por nombre."""
    plan = TransferPlan(dest_dir=str(dest_dir), executable=False)
    plan.warnings.append(
        "S11 no mueve Downloads reales. Este plan es solo informativo."
    )
    plan.warnings.append(
        "Advertencia Vortex: sacar paquetes de Downloads puede romper actualizaciones."
    )
    seen_names: dict[str, str] = {}
    if dest_dir.is_dir():
        for f in dest_dir.iterdir():
            if f.is_file():
                seen_names[f.name.lower()] = str(f)
    for src in packages:
        p = Path(src)
        if not p.is_file():
            continue
        plan.sources.append(str(p))
        plan.total_bytes += p.stat().st_size
        key = p.name.lower()
        if key in seen_names:
            plan.duplicates.append(p.name)
    try:
        usage = shutil.disk_usage(str(dest_dir if dest_dir.exists() else dest_dir.parent))
        if plan.total_bytes > usage.free:
            plan.warnings.append(
                f"espacio insuficiente en destino (libre={usage.free}, "
                f"necesario≈{plan.total_bytes})"
            )
    except OSError:
        plan.warnings.append("no se pudo consultar espacio libre del destino")
    return plan


def format_archive_simulation(sim: ArchiveSimulation) -> str:
    def fmt(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        for u, d in (("KiB", 1024), ("MiB", 1024**2), ("GiB", 1024**3)):
            if n < d * 1024 or u == "GiB":
                return f"{n / d:.2f} {u}"
        return str(n)

    lines = [
        f"=== Plan de archivado (SIMULACIÓN) — {sim.game_id} ===",
        sim.note,
        f"Archivables (tras demo sandbox): {sim.archivable_count}",
        f"Bloqueados: {sim.blocked_count}",
        f"Espacio lógico potencialmente recuperable: {fmt(sim.reclaimable_total)}",
        "",
    ]
    for w in sim.warnings:
        lines.append(f"! {w}")
    lines.append("")
    lines.append("Bloqueados (muestra):")
    for r in [x for x in sim.rows if x.blocked][:40]:
        lines.append(
            f"  ✗ {r.name} — {fmt(r.staging_logical)} — {r.block_reason}"
        )
    lines.append("")
    lines.append("Archivables (muestra):")
    for r in [x for x in sim.rows if not x.blocked][:40]:
        lines.append(f"  ✓ {r.name} — recuperar {fmt(r.reclaimable_logical)}")
    if sim.archivable_count == 0:
        lines.append("  (ninguno — falta demostrar restauración sandbox)")
    return "\n".join(lines)
