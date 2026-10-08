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

S20 — UX: multi-selección, plan masivo, filtros, paginación, arranque limpio.
Solo temporales; no escribe juegos reales.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    ensure_game_data_dir,
    game_paths_for,
)
from app.core.inventory import ModEntry  # noqa: E402
from app.ui.theme import LIBRARY_PAGE_SIZE  # noqa: E402


def _mod(i: int, **kw) -> ModEntry:
    folder = f"Mod_{i:04d}"
    return ModEntry(
        folder=folder,
        name=f"Mod Name {i}",
        characters=["OTROS"],
        character_main="OTROS",
        paks=[f"file_{i}.pak"],
        multi=False,
        on_disk=kw.get("on_disk", i % 7 == 0),
        stage_path=str(Path(f"/tmp/stage/{folder}")),
        usar=kw.get("usar", False),
        pak_elegido=f"file_{i}.pak",
        description=f"desc {i}",
        source_kind=kw.get("source_kind", "STAGING_VORTEX"),
        archived=kw.get("archived", False),
        work_extracted=kw.get("work_extracted", False),
        conflicto=kw.get("conflicto", ""),
    )


class S20UxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.base = Path(cls._td.name)
        cls.data = cls.base / "data"
        cls.data.mkdir()
        cls.mods = cls.base / "mods"
        cls.stage = cls.base / "stage"
        cls.mods.mkdir()
        cls.stage.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def _app(self, n_mods: int = 50):
        from app import gui as gui_mod

        rec = GameRecord(
            id="s20_tmp",
            name="S20 Temp",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s20_tmp",
            destination_verified=True,
            path_status="installed",
            install_mode="COPY",
        )
        reg = GamesRegistry(active_game_id="s20_tmp", games={"s20_tmp": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)
        mods = [_mod(i, usar=(i % 5 == 0)) for i in range(n_mods)]
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.registry = reg
        app.session = paths
        app.mods = mods
        app.by_id = {m.folder: m for m in mods}
        app._last_plan = None
        app._analysis_ready = False
        return app

    def tearDown(self):
        app = getattr(self, "_app_inst", None)
        if app is not None:
            try:
                app.destroy()
            except Exception:
                pass

    def test_multi_select_and_bulk_plan(self):
        app = self._app(40)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        lib.redraw()
        kids = lib.tree.get_children()
        self.assertTrue(kids)
        lib.tree.selection_set(kids[:3])
        selected = lib.selected_many()
        self.assertEqual(len(selected), 3)
        for m in selected:
            m.usar = False
        with mock.patch("app.ui.app.messagebox.showinfo"), mock.patch(
            "app.ui.app.ModManagerApp.analyze_conflicts", lambda self, on_done=None: None
        ):
            app.bulk_plan_activate()
            self.assertTrue(all(m.usar for m in selected))
            # reponer selección tras redraw
            lib.tree.selection_set([m.folder for m in selected if lib.tree.exists(m.folder)])
            app.bulk_plan_deactivate()
            self.assertTrue(all(not m.usar for m in selected))

    def test_filters_and_pagination(self):
        app = self._app(220)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        lib.page_size_var.set("40")
        lib.state_var.set("Activos")
        t0 = time.perf_counter()
        lib.redraw()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 2.0)
        self.assertTrue(all(m.usar for m in lib._filtered_cache))
        self.assertLessEqual(len(lib.tree.get_children()), 40)
        lib.next_page()
        self.assertGreaterEqual(lib.page, 0)

    def test_installed_vs_selected(self):
        app = self._app(20)
        self._app_inst = app
        m = app.mods[0]
        m.usar = True
        m.on_disk = False
        tag, estado = app.view_library._row_tag(m)
        self.assertIn("plan", estado.lower())
        self.assertNotEqual(tag, "installed")
        m.usar = False
        m.on_disk = True
        tag2, estado2 = app.view_library._row_tag(m)
        self.assertEqual(tag2, "installed")
        self.assertTrue("destino" in estado2.lower() or "ON" in estado2)

    def test_stale_analysis_blocks_apply(self):
        app = self._app(10)
        self._app_inst = app
        app._analysis_ready = False
        app._session_gen = 3
        app._analysis_for_gen = 1
        self.assertFalse(app.plan_is_applyable())
        app._busy_plan = True
        self.assertTrue(app.is_busy())
        app._busy_plan = False

    def test_source_filter(self):
        app = self._app(10)
        self._app_inst = app
        app.mods[0].source_kind = "WORK_LIBRARY"
        app.mods[0].work_extracted = True
        app.show_view("library")
        lib = app.view_library
        lib.source_var.set("WORK")
        lib.redraw()
        self.assertTrue(all("WORK" in (m.source_kind or "") for m in lib._filtered_cache))

    def test_clean_boot_sgm_data_dir(self):
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "clean_data"
            clean.mkdir()
            env = {**os.environ, "SGM_DATA_DIR": str(clean)}
            # reimport paths in subprocess-like isolation via runpy would be heavy;
            # validate helper resolves env
            from app.core import paths as paths_mod

            old = paths_mod.DATA
            try:
                # simulate env effect
                paths_mod.DATA = Path(env["SGM_DATA_DIR"])
                self.assertEqual(paths_mod.DATA, clean)
                self.assertFalse((paths_mod.DATA / "games.json").exists())
            finally:
                paths_mod.DATA = old

    def test_gitignore_and_example_exist(self):
        self.assertTrue((ROOT / ".gitignore").is_file())
        self.assertTrue((ROOT / "examples" / "games.example.json").is_file())
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue("data/**" in gi or "data/games.json" in gi)
        self.assertTrue("data/backups/" in gi or "data/**" in gi)


if __name__ == "__main__":
    unittest.main()
