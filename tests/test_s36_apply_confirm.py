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
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import ApplyContext, ApplyPlan, DesiredFile  # noqa: E402
from app.core.apply_confirm import (  # noqa: E402
    PENDIENTE_INSTALAR,
    PENDIENTE_RETIRAR,
    format_apply_confirmation,
    format_remove_confirmation,
    mod_apply_pending_flags,
    plan_fingerprint,
    plan_has_apply_work,
)
from app.core.inventory import ModEntry  # noqa: E402


def _plan(**kw) -> ApplyPlan:
    defaults = dict(
        to_add=[],
        to_update=[],
        to_remove=[],
        desired={},
        desired_meta={},
        errors=[],
        conflicts=0,
    )
    defaults.update(kw)
    return ApplyPlan(**defaults)


class ApplyConfirmTests(unittest.TestCase):
    def test_fingerprint_changes_when_remove_added(self):
        p1 = _plan(to_add=["a.pak"])
        p2 = _plan(to_add=["a.pak"], to_remove=["b.pak"])
        self.assertNotEqual(plan_fingerprint(p1), plan_fingerprint(p2))

    def test_removal_only_has_work(self):
        p = _plan(to_remove=["FOV70.pak"])
        self.assertTrue(plan_has_apply_work(p))

    def test_format_lists_remove(self):
        ctx = ApplyContext(mods=Path("C:/game/~mods"))
        p = _plan(to_remove=["FOV70.pak"])
        txt = format_apply_confirmation(p, ctx)
        self.assertIn("RETIRAR", txt)
        self.assertIn("FOV70.pak", txt)

    def test_remove_extra_confirm_lists_count(self):
        p = _plan(to_remove=["a.pak", "b.pak"])
        self.assertIn("2 archivo", format_remove_confirmation(p))

    def test_mod_pending_install_and_remove(self):
        m = ModEntry(
            folder="f1",
            name="M",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["x.pak"],
            multi=False,
            on_disk=False,
            stage_path="s",
            usar=True,
        )
        meta = DesiredFile(source=Path("s/x.pak"), mod_folder="f1", mod_name="M")
        p = _plan(
            to_add=["x.pak"],
            desired={"x.pak": Path("s/x.pak")},
            desired_meta={"x.pak": meta},
        )
        self.assertIn(PENDIENTE_INSTALAR, mod_apply_pending_flags(m, p))
        p2 = _plan(to_remove=["x.pak"])
        self.assertIn(PENDIENTE_RETIRAR, mod_apply_pending_flags(m, p2))

    def test_plan_is_applyable_requires_fresh_analysis_fingerprint(self):
        """S39: no exige Simular manual; sí huella del último recálculo automático."""
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
        from tests.test_s06_ui import _make_mod

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        rec = GameRecord(
            id="s36",
            name="S36",
            mods_dir=str(base / "mods"),
            stage_dir=str(base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s36",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s36", games={"s36": rec})
        paths = game_paths_for(rec, app_data=base / "data")
        ensure_game_data_dir(paths)
        from app import gui as gui_mod

        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.mods = [_make_mod(0)]
        app.session = paths
        app.registry = reg
        app._session_gen = 1
        app._analysis_ready = True
        app._analysis_for_gen = 1
        app._last_plan = _plan(to_remove=["demo.pak"])
        self.assertFalse(app.plan_is_applyable())
        app._capture_apply_simulation(app._last_plan)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertTrue(app.plan_is_applyable())
        app._invalidate_apply_simulation()
        self.assertFalse(app.plan_is_applyable())


if __name__ == "__main__":
    unittest.main()
