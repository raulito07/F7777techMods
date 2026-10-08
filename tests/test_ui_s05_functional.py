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

Pruebas funcionales de UI (código + instancia Tk oculta). No equivalen a
validación visual manual.
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


class UIFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.base = Path(cls._td.name)
        cls.data = cls.base / "data"
        cls.data.mkdir()
        (cls.data / "games").mkdir()

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_update_status_and_panels(self):
        from app.core.games import (
            GamesRegistry,
            GameRecord,
            game_paths_for,
            ensure_game_data_dir,
        )
        from app import gui as gui_mod

        mods = self.base / "mods"
        stage = self.base / "stage"
        mods.mkdir(exist_ok=True)
        stage.mkdir(exist_ok=True)
        rec = GameRecord(
            id="ui_tmp",
            name="UI Temp",
            mods_dir=str(mods),
            stage_dir=str(stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="ui_tmp",
        )
        reg = GamesRegistry(active_game_id="ui_tmp", games={"ui_tmp": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)

        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
            app.withdraw()
            try:
                app.session = paths
                app.registry = reg
                app.mods = []
                app.by_id = {}
                app._last_plan = None
                app._update_status_bar()
                for name in (
                    "simulate",
                    "apply_to_game",
                    "open_files_panel",
                    "open_history_panel",
                    "open_conflicts_panel",
                    "show_view",
                ):
                    self.assertTrue(hasattr(app, name), msg=name)
                app.show_view("library")
                app.show_view("summary")
            finally:
                app.destroy()

    def test_format_plan_preview_lists_files(self):
        from app.core.apply import ApplyPlan
        from app.core.games import GameRecord, game_paths_for, GamesRegistry, ensure_game_data_dir
        from app import gui as gui_mod

        mods = self.base / "mods2"
        stage = self.base / "stage2"
        mods.mkdir(exist_ok=True)
        stage.mkdir(exist_ok=True)
        rec = GameRecord(
            id="ui_tmp2",
            name="UI Temp 2",
            mods_dir=str(mods),
            stage_dir=str(stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="ui_tmp2",
        )
        reg = GamesRegistry(active_game_id="ui_tmp2", games={"ui_tmp2": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)

        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
            app.withdraw()
            try:
                app.session = paths
                app.mods = []
                plan = ApplyPlan(
                    to_add=["a.pak", "b.pak"],
                    to_update=["c.pak"],
                    to_remove=["d.pak"],
                    desired={},
                    desired_meta={},
                    errors=["aviso prueba"],
                    conflicts=0,
                )
                msg = app._format_plan_preview(
                    plan, paths.apply_context(), title="TEST"
                )
                self.assertIn("AÑADIR", msg)
                self.assertIn("a.pak", msg)
                self.assertIn("ACTUALIZAR", msg)
                self.assertIn("RETIRAR", msg)
                self.assertIn("aviso prueba", msg)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
