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

Diagnóstico legible: mods activos vs archivos preparados para Apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .apply import ApplyContext, ApplyPlan
from .conflict_engine import ConflictSettings, collect_offers
from .content_classify import classify_mod
from .inventory import ModEntry


@dataclass
class ModPlanDiagnostic:
    folder: str
    name: str
    usar: bool
    planned_files: list[str] = field(default_factory=list)
    offer_count: int = 0
    reasons: list[str] = field(default_factory=list)
    file_lines: list[str] = field(default_factory=list)


def _mod_errors(plan: ApplyPlan, mod: ModEntry) -> list[str]:
    out: list[str] = []
    needle = mod.name
    for e in plan.errors or []:
        if mod.folder in e or needle in e:
            out.append(e)
    return out


def diagnose_mod(
    mod: ModEntry,
    plan: ApplyPlan | None,
    *,
    adapter_id: str,
    mods_dest: Path,
    settings: ConflictSettings | None = None,
) -> ModPlanDiagnostic:
    d = ModPlanDiagnostic(folder=mod.folder, name=mod.name, usar=bool(mod.usar))
    if not mod.usar:
        d.reasons.append("No está activo en el plan (usar=NO). Simular plan lo ignora.")
        return d

    stage = Path(mod.stage_path or "")
    if not stage.is_dir():
        d.reasons.append("Sin carpeta de staging local — no hay origen para copiar.")

    if mod.multi and not mod.pak_elegido:
        d.reasons.append("Mod multi-variante: falta elegir UNA variante .pak.")

    try:
        from .emov_plan import game_root_from_mods_dir, library_emov_hints

        gr = game_root_from_mods_dir(mods_dest)
        for line in library_emov_hints(
            mod, game_root=gr, adapter_id=adapter_id
        ):
            d.file_lines.append(line)
    except Exception:
        pass

    try:
        mc = classify_mod(mod, adapter_id)
        if not mc.installable:
            d.reasons.append(
                f"Clasificación sin instalables ({mc.summary_kind()}). "
                "Revisa contenido / adaptador."
            )
        elif mod.usar and mc.installable:
            for rel in mc.installable[:12]:
                dest = mods_dest / Path(rel.replace("\\", "/").split("/")[-1])
                if rel.lower().endswith(".pak"):
                    dest = mods_dest / Path(rel).name
                d.file_lines.append(f"  {rel}  ← staging  →  {dest}")
    except Exception as exc:
        d.reasons.append(f"No se pudo clasificar: {exc}")

    if plan is not None:
        d.planned_files = sorted(
            rel for rel, meta in plan.desired_meta.items() if meta.mod_folder == mod.folder
        )
        d.reasons.extend(_mod_errors(plan, mod))

    if settings is not None and mod.usar:
        by_key, _variants, offer_errors = collect_offers([mod], settings)
        d.offer_count = sum(
            1
            for offers in by_key.values()
            for o in offers
            if o.mod_folder == mod.folder
        )
        for e in offer_errors:
            if e not in d.reasons:
                d.reasons.append(e)

    if mod.usar and d.offer_count == 0 and not d.planned_files:
        if not d.reasons:
            d.reasons.append("Activo en plan pero ningún archivo instalable detectado.")
    elif mod.usar and d.planned_files and plan is not None:
        adds = set(plan.to_add)
        upd = set(plan.to_update)
        pending = [f for f in d.planned_files if f in adds or f in upd]
        if not pending and d.planned_files:
            d.reasons.append(
                "Archivos ya en destino gestionado sin cambios pendientes "
                "(AÑADIR/ACTUALIZAR vacíos)."
            )

    return d


def format_plan_mod_section(
    mods: list[ModEntry],
    plan: ApplyPlan,
    ctx: ApplyContext,
    settings: ConflictSettings | None = None,
    *,
    scope_label: str,
    only_folders: set[str] | None = None,
) -> str:
    adapter_id = settings.adapter_id if settings else "generic_folder"
    active = [m for m in mods if m.usar and (only_folders is None or m.folder in only_folders)]
    lines = [
        f"ALCANCE: {scope_label}",
        f"Mods activos en este alcance: {len(active)}",
        "",
    ]
    if not active:
        lines.append("⚠ No hay mods con «usar» activo en este alcance.")
        return "\n".join(lines)

    any_action = bool(plan.to_add or plan.to_update)
    for m in active:
        diag = diagnose_mod(
            m,
            plan,
            adapter_id=adapter_id,
            mods_dest=ctx.mods,
            settings=settings,
        )
        lines.append(f"▸ {diag.name}  [{diag.folder}]")
        lines.append(f"   Estado plan: {'ACTIVO' if diag.usar else 'inactivo'}")
        lines.append(f"   Ofertas motor: {diag.offer_count} · En plan deseado: {len(diag.planned_files)}")
        if diag.planned_files:
            for rel in diag.planned_files[:15]:
                meta = plan.desired_meta.get(rel)
                src = meta.source if meta else Path("?")
                lines.append(f"   • {rel}")
                lines.append(f"       origen: {src}")
                lines.append(f"       destino: {ctx.mods / rel}")
            if len(diag.planned_files) > 15:
                lines.append(f"   • … y {len(diag.planned_files) - 15} más")
        elif diag.file_lines:
            lines.append("   Clasificación (si se activara sin bloqueos):")
            lines.extend(diag.file_lines[:8])
        for r in diag.reasons[:6]:
            lines.append(f"   ⚠ {r}")
        lines.append("")

    if active and not any_action and not plan.desired_meta:
        lines.insert(
            2,
            "⚠ ADVERTENCIA: mods activos pero 0 archivos preparados — Apply NO está listo.\n",
        )
    elif active and not any_action:
        lines.insert(
            2,
            "⚠ ADVERTENCIA: no hay AÑADIR ni ACTUALIZAR; el destino ya coincide o hay bloqueos.\n",
        )
    return "\n".join(lines)


def single_mod_detail_block(
    mod: ModEntry,
    plan: ApplyPlan | None,
    *,
    adapter_id: str,
    mods_dest: Path,
    selected_folder: str,
) -> str:
    sel_note = (
        " (coincide con selección visual)"
        if mod.folder == selected_folder
        else " (NO es la fila seleccionada en Biblioteca)"
    )
    diag = diagnose_mod(mod, plan, adapter_id=adapter_id, mods_dest=mods_dest)
    lines = [
        f"Mod analizado{sel_note}: {mod.name} [{mod.folder}]",
        f"Activo en plan (usar): {'SÍ' if mod.usar else 'NO'}",
        "",
    ]
    if diag.planned_files and plan:
        lines.append("Archivos en plan deseado:")
        for rel in diag.planned_files[:20]:
            meta = plan.desired_meta.get(rel)
            lines.append(f"  • {rel} ← {meta.source if meta else '?'} → {mods_dest / rel}")
    for r in diag.reasons:
        lines.append(f"⚠ {r}")
    if not diag.reasons and mod.usar and diag.planned_files:
        lines.append("Sin bloqueos obvios en este mod.")
    lines.append("")
    lines.append("Acciones: elige variante · Actualizar inventario · «Simular plan» / «Simular selección».")
    return "\n".join(lines)
