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

S14 — preparar instalación desde biblioteca de trabajo (simulación).
No ejecuta Apply real sobre juegos en este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .apply import ApplyContext, plan_apply
from .conflict_engine import ConflictSettings
from .work_library import WorkLibraryIndex, mark_in_use, work_record_to_mod_entry


@dataclass
class WorkInstallPrep:
    ok: bool
    mod_count: int = 0
    plan_errors: list[str] = field(default_factory=list)
    to_add: int = 0
    to_update: int = 0
    to_remove: int = 0
    blockers: int = 0
    note: str = ""
    preview: str = ""


def prepare_install_from_work(
    idx: WorkLibraryIndex,
    *,
    mod_ids: list[str] | None,
    ctx: ApplyContext,
    settings: ConflictSettings,
    mark_use: bool = True,
) -> WorkInstallPrep:
    """
    Construye plan_apply desde extraídos en biblioteca propia.
    Solo simulación (plan_apply no escribe).
    """
    ids = mod_ids if mod_ids is not None else list(idx.mods.keys())
    mods = []
    used_ids = []
    for mid in ids:
        rec = idx.mods.get(mid)
        if not rec:
            continue
        if not Path(rec.work_path).is_dir():
            continue
        mods.append(work_record_to_mod_entry(rec, usar=True))
        used_ids.append(mid)
    if not mods:
        return WorkInstallPrep(
            ok=False,
            note="No hay mods extraídos en biblioteca de trabajo para preparar.",
        )
    if mark_use:
        mark_in_use(idx, used_ids, in_use=True)

    plan = plan_apply(mods, ctx=ctx, settings=settings)
    preview_lines = [
        f"Mods desde biblioteca propia: {len(mods)}",
        f"Añadir: {len(plan.to_add)} · Actualizar: {len(plan.to_update)} · "
        f"Quitar: {len(plan.to_remove)}",
        f"Bloqueos: {plan.conflicts}",
        f"Modo instalación policy: {plan.install_mode_policy}",
        "",
        "S14: solo preparación/simulación. Apply real requiere autorización aparte.",
        "Fuente: biblioteca de trabajo (no staging Vortex).",
        "",
    ]
    for e in plan.errors[:25]:
        preview_lines.append(f"  ! {e}")
    return WorkInstallPrep(
        ok=plan.conflicts == 0,
        mod_count=len(mods),
        plan_errors=list(plan.errors),
        to_add=len(plan.to_add),
        to_update=len(plan.to_update),
        to_remove=len(plan.to_remove),
        blockers=plan.conflicts,
        note="plan_apply simulado desde work_library",
        preview="\n".join(preview_lines),
    )
