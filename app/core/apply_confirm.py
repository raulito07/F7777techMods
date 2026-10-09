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

S36/S39 — resumen de Apply, huella de plan y estados pendientes.
Simular es opcional; la validación interna y la confirmación siguen obligatorias.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .apply import ApplyContext, ApplyPlan
from .inventory import ModEntry

PENDIENTE_INSTALAR = "PENDIENTE_INSTALAR"
PENDIENTE_RETIRAR = "PENDIENTE_RETIRAR"
SIN_CAMBIOS_APPLY = "SIN_CAMBIOS_APPLY"

# Tags visuales S39 (Biblioteca)
TAG_READY = "ready"  # VERDE — operaciones preparadas, sin bloqueos conocidos
TAG_WARN = "pending"  # AMARILLO — revisión / advertencia
TAG_BLOCK = "conflict"  # ROJO — bloqueo real
TAG_UNCHANGED = "unchanged"  # GRIS — sin cambios Apply

PAK_LIMITATION_NOTE = (
    "Nota: los conflictos de ruta/destino no equivalen a incompatibilidades "
    "internas desconocidas entre archivos .pak; esas solo se confirman con "
    "evidencia técnica o documentada."
)


def plan_fingerprint(plan: ApplyPlan) -> str:
    payload = {
        "add": sorted(plan.to_add),
        "upd": sorted(plan.to_update),
        "rem": sorted(plan.to_remove),
        "conf": int(plan.conflicts),
        "unres": int(plan.file_unresolved),
        "errors": sorted(str(e) for e in (plan.errors or [])),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_has_apply_work(plan: ApplyPlan) -> bool:
    return bool(plan.to_add or plan.to_update or plan.to_remove)


def _file_line(rel: str, plan: ApplyPlan, ctx: ApplyContext, verb: str) -> str:
    meta = (plan.desired_meta or {}).get(rel)
    mod = meta.mod_name if meta else "—"
    folder = meta.mod_folder if meta else "—"
    src = meta.source if meta else Path("—")
    dst = ctx.mods / rel
    return f"  • [{verb}] {rel}\n      mod: {mod} ({folder})\n      origen: {src}\n      destino: {dst}"


def format_apply_confirmation(plan: ApplyPlan, ctx: ApplyContext) -> str:
    lines = [
        "RESUMEN OBLIGATORIO — cambios en el destino del juego",
        f"Destino: {ctx.mods}",
        "",
    ]
    if not plan_has_apply_work(plan):
        lines.append("Sin cambios que aplicar (AÑADIR/ACTUALIZAR/RETIRAR vacíos).")
        return "\n".join(lines)

    if plan.to_add:
        lines.append(f"AÑADIR ({len(plan.to_add)}):")
        for rel in plan.to_add:
            lines.append(_file_line(rel, plan, ctx, "AÑADIR"))
        lines.append("")
    if plan.to_update:
        lines.append(f"ACTUALIZAR ({len(plan.to_update)}):")
        for rel in plan.to_update:
            lines.append(_file_line(rel, plan, ctx, "ACTUALIZAR"))
        lines.append("")
    if plan.to_remove:
        lines.append(f"RETIRAR ({len(plan.to_remove)}) — se borran del juego (solo GESTIONADOS):")
        for rel in plan.to_remove:
            lines.append(f"  • [RETIRAR] {rel}\n      destino: {ctx.mods / rel}")
        lines.append("")
    if plan.errors:
        lines.append("BLOQUEOS:")
        for e in plan.errors[:20]:
            lines.append(f"  • {e}")
        lines.append("")
    lines.append(PAK_LIMITATION_NOTE)
    return "\n".join(lines)


def plan_is_blocked(plan: ApplyPlan | None) -> bool:
    if plan is None:
        return True
    return bool(plan.conflicts or plan.file_unresolved or plan.errors)


def apply_row_visual(
    m: ModEntry,
    plan: ApplyPlan | None,
    *,
    structure_blocks: bool = False,
    structure_label: str = "",
    analysis_ready: bool = False,
) -> tuple[str, str]:
    """
    (tag, etiqueta) Apply-aware. Verde solo si hay operación preparada sin bloqueos.
    Activo en plan sin delta → gris, no verde.
    """
    pending = mod_apply_pending_flags(m, plan)
    blocked = plan_is_blocked(plan) or structure_blocks
    if m.usar and (m.conflicto or "").strip() and "ESTRUCTURA:" not in (m.conflicto or ""):
        # conflicto de rutas / motor reportado en etiqueta
        if "CONFLICTO" in (m.conflicto or "").upper() or "FILE_" in (m.conflicto or "").upper():
            return TAG_BLOCK, (m.conflicto or "Bloqueo")[:40]
    if structure_blocks and m.usar:
        return TAG_WARN, (structure_label or "Revisión estructura")[:40]
    if structure_label and m.usar and not pending and not structure_blocks:
        return TAG_WARN, structure_label[:40]
    if PENDIENTE_RETIRAR in pending:
        if blocked or not analysis_ready:
            return TAG_WARN, "Pendiente retirar — revisión"
        return TAG_READY, "Preparado: retirar"
    if PENDIENTE_INSTALAR in pending:
        if blocked or not analysis_ready:
            return TAG_WARN, "Pendiente instalar — revisión"
        return TAG_READY, "Preparado: instalar/actualizar"
    if m.usar and m.multi:
        from .component_selection import selection_pending

        if selection_pending(m):
            return TAG_WARN, "Variante/componente pendiente"
    if (m.conflicto or "").strip() and m.usar:
        return TAG_BLOCK, (m.conflicto or "Bloqueo")[:40]
    if not pending:
        if m.usar and m.on_disk:
            return TAG_UNCHANGED, "Sin cambios Apply"
        if m.usar:
            return TAG_UNCHANGED, "En plan (sin delta aún)"
        if m.on_disk:
            return TAG_UNCHANGED, "Destino ON (plan NO)"
        return TAG_UNCHANGED, "Sin cambios"
    return TAG_UNCHANGED, "Sin cambios"


def format_remove_confirmation(plan: ApplyPlan) -> str:
    rem = sorted(plan.to_remove)
    names = "\n".join(f"  • {r}" for r in rem[:40])
    extra = f"\n  • … y {len(rem) - 40} más" if len(rem) > 40 else ""
    return (
        f"CONFIRMACIÓN ADICIONAL — RETIRADA FÍSICA\n\n"
        f"Se retirarán {len(rem)} archivo(s) GESTIONADO(s) del juego:\n"
        f"{names}{extra}\n\n"
        "Desactivar en Biblioteca NO retira archivos; esta acción SÍ los elimina del destino."
    )


def mod_apply_pending_flags(m: ModEntry, plan: ApplyPlan | None) -> frozenset[str]:
    if plan is None:
        return frozenset()
    out: set[str] = set()
    folder = m.folder
    for rel in plan.to_add:
        meta = plan.desired_meta.get(rel)
        if meta and meta.mod_folder == folder:
            out.add(PENDIENTE_INSTALAR)
    for rel in plan.to_update:
        meta = plan.desired_meta.get(rel)
        if meta and meta.mod_folder == folder:
            out.add(PENDIENTE_INSTALAR)
    for rel in plan.to_remove:
        meta = plan.desired_meta.get(rel)
        if meta and meta.mod_folder == folder:
            out.add(PENDIENTE_RETIRAR)
            continue
        base = Path(rel).name.lower()
        if base in {p.lower() for p in m.paks} or (m.pak_elegido and base == m.pak_elegido.lower()):
            out.add(PENDIENTE_RETIRAR)
    if m.usar and not out and plan_has_apply_work(plan):
        # activo pero sin acción pendiente para este mod
        pass
    return frozenset(out)
