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

S16 — comprobar independencia del gestor respecto al staging Vortex
(solo sandbox / plan; no Apply real a juegos).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .apply import ApplyContext, plan_apply
from .conflict_engine import ConflictSettings
from .own_archive import read_own_manifest
from .work_library import (
    load_index,
    restore_archive_to_work,
    work_record_to_mod_entry,
)


@dataclass
class IndependenceCheck:
    ok: bool
    archive_ok: bool = False
    restore_ok: bool = False
    plan_ok: bool = False
    uses_vortex_staging: bool = False
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    work_path: str = ""


def verify_independence_from_archive(
    *,
    game_id: str,
    archive_path: Path,
    work_root: Path,
    ctx: ApplyContext | None = None,
    settings: ConflictSettings | None = None,
    stage_root: Path | None = None,
    pak_elegido: str = "",
) -> IndependenceCheck:
    """
    Verifica que el mod puede restaurarse a WORK y planificarse sin
    usar staging Vortex. No escribe en destino de juego real si ctx es None
    (solo restore + plan en work).
    """
    res = IndependenceCheck(ok=False)
    ap = Path(archive_path)
    if not ap.is_file():
        res.errors.append("ZIP ausente")
        return res
    man, errs = read_own_manifest(ap)
    if not man or errs:
        res.errors.append("ARCHIVO_PROPIO inválido o corrupto")
        res.errors.extend(errs[:3])
        return res
    res.archive_ok = True

    idx = load_index(work_root, game_id=game_id)
    rr = restore_archive_to_work(
        game_id=game_id,
        archive_path=ap,
        work_root=work_root,
        idx=idx,
    )
    if not rr.ok:
        res.errors.extend(rr.errors[:5] or ["restore falló"])
        return res
    res.restore_ok = True
    res.work_path = rr.work_path or ""

    idx = load_index(work_root, game_id=game_id)
    rec = idx.mods.get(rr.mod_id)
    if not rec:
        res.errors.append("registro work ausente tras restore")
        return res
    wm = work_record_to_mod_entry(rec, usar=True)
    if pak_elegido:
        wm.pak_elegido = pak_elegido

    # ¿la ruta de origen cae bajo staging Vortex?
    if stage_root and stage_root.is_dir():
        try:
            Path(wm.stage_path).resolve().relative_to(stage_root.resolve())
            res.uses_vortex_staging = True
            res.errors.append("origen apunta a staging Vortex tras restore")
            return res
        except ValueError:
            pass

    if ctx is None or settings is None:
        res.plan_ok = True
        res.ok = True
        res.notes.append("Restore OK; plan omitido (sin ctx).")
        return res

    settings.game_id = game_id
    settings.work_root = work_root
    settings.destination_verified = True
    plan = plan_apply([wm], ctx=ctx, settings=settings)
    if plan.conflicts or plan.errors:
        res.errors.extend(plan.errors[:5])
        if plan.conflicts:
            res.errors.append(f"conflictos={plan.conflicts}")
        return res
    res.plan_ok = True
    res.ok = True
    res.notes.append(
        f"Independiente de Vortex: work={res.work_path}; "
        f"plan add={len(plan.to_add)}"
    )
    return res
