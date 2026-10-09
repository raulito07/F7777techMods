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

Simulación: mods activos sin archivos, alcance plan vs selección.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import ApplyContext, plan_apply  # noqa: E402
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.plan_diagnostics import diagnose_mod, format_plan_mod_section  # noqa: E402


class PlanSimulationTests(unittest.TestCase):
    def test_active_mod_no_staging_warns(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        mods_dir = base / "game_mods"
        mods_dir.mkdir()
        m = ModEntry(
            folder="LearnEnemySkill",
            name="Learn Enemy Skill",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["LearnEnemySkill.pak"],
            multi=False,
            on_disk=True,
            stage_path=str(base / "missing_stage"),
            usar=True,
            pak_elegido="LearnEnemySkill.pak",
        )
        ctx = ApplyContext(mods=mods_dir, stage=base / "stage", data_dir=base / "data")
        settings = ConflictSettings(adapter_id="ue4_paks_mods", stage_root=base / "stage")
        plan = plan_apply([m], ctx, settings)
        diag = diagnose_mod(m, plan, adapter_id="ue4_paks_mods", mods_dest=mods_dir, settings=settings)
        self.assertTrue(any("staging" in r.lower() for r in diag.reasons))
        section = format_plan_mod_section(
            [m],
            plan,
            ctx,
            settings,
            scope_label="test",
        )
        self.assertIn("ADVERTENCIA", section)
        self.assertIn("LearnEnemySkill", section)

    def test_active_no_install_actions_not_applyable(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        mods_dir = base / "game_mods"
        mods_dir.mkdir()
        m = ModEntry(
            folder="x",
            name="X",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["a.pak"],
            multi=False,
            on_disk=True,
            stage_path=str(base / "st"),
            usar=True,
        )
        ctx = ApplyContext(mods=mods_dir, stage=base / "stage", data_dir=base / "data")
        plan = plan_apply([m], ctx, ConflictSettings(adapter_id="ue4_paks_mods"))
        self.assertFalse(plan.to_add)
        self.assertFalse(plan.to_update)


if __name__ == "__main__":
    unittest.main()
