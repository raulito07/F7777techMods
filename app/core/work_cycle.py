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

S15 — ciclo sandbox: ZIP → WORK → plan → Apply → desactivar → restaurar → cleanup.
Solo para pruebas / sandbox; no escribe Vortex.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .apply import ApplyContext, ApplyError, execute, load_manifest, plan_apply
from .conflict_engine import ConflictSettings
from .inventory import ModEntry
from .mod_source import SOURCE_WORK_LIBRARY, validate_mods_for_apply
from .own_archive import create_own_archive
from .work_library import (
    cleanup_work_library,
    load_index,
    mark_in_use,
    restore_archive_to_work,
    work_record_to_mod_entry,
)


@dataclass
class CycleStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class SandboxCycleResult:
    ok: bool
    steps: list[CycleStep] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(CycleStep(name=name, ok=ok, detail=detail))
        if not ok:
            self.ok = False
            if detail:
                self.errors.append(f"{name}: {detail}")


def run_sandbox_install_cycle(
    *,
    game_id: str,
    stage_mod: ModEntry,
    stage_root: Path,
    archive_dir: Path,
    work_root: Path,
    ctx: ApplyContext,
    settings: ConflictSettings,
    pak_elegido: str = "",
) -> SandboxCycleResult:
    """
    Ciclo completo en sandbox:
    ZIP propio → WORK_LIBRARY → plan → execute → verify manifest →
    desactivar → execute → cleanup work → re-restore → re-install.
    """
    res = SandboxCycleResult(ok=True)
    settings.game_id = game_id
    settings.work_root = work_root
    settings.destination_verified = True
    if pak_elegido:
        stage_mod.pak_elegido = pak_elegido

    # 1) crear ZIP
    cr = create_own_archive(
        game_id=game_id,
        mod=stage_mod,
        stage_root=stage_root,
        dest_dir=archive_dir,
    )
    res.add("zip_propio", cr.ok, cr.published_path or "; ".join(cr.errors[:2]))
    if not cr.ok:
        return res

    # 2) restore work
    idx = load_index(work_root, game_id=game_id)
    rr = restore_archive_to_work(
        game_id=game_id,
        archive_path=Path(cr.published_path),
        work_root=work_root,
        idx=idx,
    )
    res.add("restore_work", rr.ok, rr.work_path or "; ".join(rr.errors[:2]))
    if not rr.ok:
        return res
    idx = load_index(work_root, game_id=game_id)
    wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
    if pak_elegido:
        wm.pak_elegido = pak_elegido

    # 3) validar procedencia
    v = validate_mods_for_apply(
        [wm],
        game_id=game_id,
        stage_root=stage_root,
        work_root=work_root,
    )
    res.add("validate_source", v.ok, "; ".join(v.errors[:3]))
    if not v.ok:
        return res

    # 4) plan + apply
    plan = plan_apply([wm], ctx=ctx, settings=settings)
    res.add(
        "plan",
        plan.conflicts == 0 and not plan.errors,
        f"add={len(plan.to_add)} conf={plan.conflicts}",
    )
    if plan.conflicts or plan.errors:
        res.errors.extend(plan.errors[:5])
        return res
    try:
        execute(plan, ctx, mods=[wm])
        res.add("apply", True, f"installed={len(plan.to_add)}")
    except ApplyError as e:
        res.add("apply", False, str(e)[:200])
        return res

    man = load_manifest(ctx)
    res.add("manifest", bool(man), f"entries={len(man)}")

    # 5) desactivar
    wm.usar = False
    mark_in_use(idx, [rr.mod_id], in_use=False)
    plan2 = plan_apply([wm], ctx=ctx, settings=settings)
    try:
        execute(plan2, ctx, mods=[wm])
        res.add("deactivate", True, f"removed={len(plan2.to_remove)}")
    except ApplyError as e:
        res.add("deactivate", False, str(e)[:200])
        return res

    # 6) cleanup work (sin hardlinks tras desactivar COPY)
    mods_dir = ctx.mods
    removed, notes = cleanup_work_library(
        idx, only_unused=True, mods_dir=mods_dir
    )
    res.add("cleanup_work", True, f"removed={removed}; {notes[:1]}")

    # 7) re-restore + reinstall
    idx = load_index(work_root, game_id=game_id)
    rr2 = restore_archive_to_work(
        game_id=game_id,
        archive_path=Path(cr.published_path),
        work_root=work_root,
        idx=idx,
    )
    res.add("re_restore", rr2.ok, rr2.work_path or "; ".join(rr2.errors[:2]))
    if not rr2.ok:
        return res
    idx = load_index(work_root, game_id=game_id)
    wm2 = work_record_to_mod_entry(idx.mods[rr2.mod_id], usar=True)
    if pak_elegido:
        wm2.pak_elegido = pak_elegido
    plan3 = plan_apply([wm2], ctx=ctx, settings=settings)
    try:
        execute(plan3, ctx, mods=[wm2])
        res.add("reinstall", True, f"add={len(plan3.to_add)}")
    except ApplyError as e:
        res.add("reinstall", False, str(e)[:200])
        return res

    res.add(
        "source_kind",
        wm2.source_kind == SOURCE_WORK_LIBRARY,
        wm2.source_kind,
    )
    return res
