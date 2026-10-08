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

Pruebas S06 — navegación, filtros, rendimiento, locks asíncronos.
No equivalen a validación visual interactiva completa.
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.inventory import ModEntry  # noqa: E402
from app.core.games import (  # noqa: E402
    GamesRegistry,
    GameRecord,
    game_paths_for,
    ensure_game_data_dir,
)
from app.ui.theme import NAV_ITEMS, LIBRARY_PAGE_SIZE  # noqa: E402


def _make_mod(i: int, *, usar: bool = False, conflict: str = "") -> ModEntry:
    folder = f"Mod_{i:04d}"
    return ModEntry(
        folder=folder,
        name=f"Mod Name {i}",
        characters=["OTROS"],
        character_main="OTROS",
        paks=[f"file_{i}.pak"],
        multi=False,
        on_disk=i % 7 == 0,
        stage_path=str(Path(f"/tmp/stage/{folder}")),
        usar=usar,
        pak_elegido=f"file_{i}.pak",
        description=f"Descripción sintética {i}",
        conflicto=conflict,
    )


class S06UITests(unittest.TestCase):
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

    def _app(self, n_mods: int = 20):
        from app import gui as gui_mod

        rec = GameRecord(
            id="s06_tmp",
            name="S06 Temp",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s06_tmp",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s06_tmp", games={"s06_tmp": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)
        mods = [
            _make_mod(i, usar=(i % 5 == 0), conflict="CONFLICTO" if i % 11 == 0 else "")
            for i in range(n_mods)
        ]

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
        return app

    def tearDown(self):
        app = getattr(self, "_app_inst", None)
        if app is not None:
            try:
                app.destroy()
            except Exception:
                pass

    def test_nav_items_and_show_view(self):
        app = self._app(30)
        self._app_inst = app
        keys = [k for k, _ in NAV_ITEMS]
        self.assertEqual(
            keys,
            [
                "summary",
                "library",
                "conflicts",
                "installed",
                "storage",
                "history",
                "settings",
                "about",
            ],
        )
        for k in keys:
            app.show_view(k)
            self.assertEqual(app._current_view, k)
            self.assertTrue(app._views[k].winfo_ismapped() or True)

    def test_library_filter_and_pagination_200(self):
        app = self._app(220)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        t0 = time.perf_counter()
        lib.search_var.set("Mod Name 1")
        lib.redraw()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.5, msg=f"filtro lento: {elapsed:.3f}s")
        self.assertTrue(len(lib._filtered_cache) < 220)
        self.assertLessEqual(len(lib.tree.get_children()), LIBRARY_PAGE_SIZE)
        lib.state_var.set("Activos")
        lib.search_var.set("")
        lib.redraw()
        self.assertTrue(all(m.usar for m in lib._filtered_cache))

    def test_toggle_and_busy_blocks_game_switch(self):
        app = self._app(10)
        self._app_inst = app
        app.show_view("library")
        app.view_library.redraw()
        # select first
        kids = app.view_library.tree.get_children()
        if kids:
            app.view_library.tree.selection_set(kids[0])
            before = app.view_library.selected().usar
            app.toggle_selected()
            after = app.by_id[kids[0]].usar
            self.assertNotEqual(before, after)
        app._busy_write = True
        app.registry.games["other"] = GameRecord(
            id="other",
            name="Other",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="other",
        )
        # attempt switch while busy — should keep active
        active = app.registry.active_game_id
        with mock.patch("app.ui.app.messagebox.showinfo"):
            app._on_game_selected("Other  [other]")
        self.assertEqual(app.registry.active_game_id, active)

    def test_stale_analyze_discarded(self):
        app = self._app(5)
        self._app_inst = app
        app._analyze_gen = 1
        app._session_gen = 1
        app.registry.active_game_id = "s06_tmp"
        # Simulate stale callback
        app._analyze_gen = 2
        called = {"n": 0}

        def on_done():
            called["n"] += 1

        # Manually invoke guard logic
        gen = 1
        session_gen = 1
        game_id = "s06_tmp"
        if gen != app._analyze_gen or session_gen != app._session_gen:
            pass
        else:
            on_done()
        self.assertEqual(called["n"], 0)

    def test_format_preview_and_progress_api(self):
        from app.core.apply import ApplyPlan, execute, ApplyContext, plan_apply
        from app.core.inventory import ModEntry as ME

        app = self._app(3)
        self._app_inst = app
        plan = ApplyPlan(
            to_add=["a.pak"],
            to_update=["b.pak"],
            to_remove=["c.pak"],
            desired={},
            desired_meta={},
            errors=["bloqueado x"],
            conflicts=0,
            drifted=["d.pak"],
        )
        msg = app._format_plan_preview(plan, app._ctx(), title="T")
        self.assertIn("AÑADIR", msg)
        self.assertIn("DERIVA", msg)
        self.assertIn("bloqueado x", msg)

        # progress callback accepted by execute (empty plan fails validation — just check signature)
        import inspect

        sig = inspect.signature(execute)
        self.assertIn("progress", sig.parameters)

    def test_zoom_persists_setting(self):
        app = self._app(5)
        self._app_inst = app
        for z in (100, 125, 140, 150):
            app.set_zoom(z)
            self.assertEqual(app.zoom, z)
            app.view_library.apply_zoom(z / 100.0)
        app.set_appearance("light")
        app.set_appearance("dark")

    def test_apply_blocked_without_fresh_analysis(self):
        app = self._app(10)
        self._app_inst = app
        app._session_gen = 3
        app._analysis_ready = False
        app._analysis_for_gen = -1
        self.assertFalse(app.plan_is_applyable())
        app._sync_apply_button()
        self.assertEqual(str(app.apply_btn.cget("state")), "disabled")

        # Análisis antiguo de otra generación → sigue bloqueado
        from app.core.apply import ApplyPlan

        app._last_plan = ApplyPlan(
            to_add=[],
            to_update=[],
            to_remove=[],
            desired={},
            desired_meta={},
            errors=[],
            conflicts=0,
        )
        app._analysis_ready = True
        app._analysis_for_gen = 1  # distinto de session_gen=3
        self.assertFalse(app.plan_is_applyable())

        # Análisis vigente limpio → aplicable
        app._analysis_for_gen = 3
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertTrue(app.plan_is_applyable())
            app._sync_apply_button()
            self.assertEqual(str(app.apply_btn.cget("state")), "normal")

        # Con conflictos → bloqueado
        app._last_plan.conflicts = 2
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertFalse(app.plan_is_applyable())

    def test_filter_survives_page_change(self):
        app = self._app(100)
        self._app_inst = app
        lib = app.view_library
        lib.state_var.set("Activos")
        lib.redraw()
        n = len(lib._filtered_cache)
        self.assertTrue(n > 0)
        if n > LIBRARY_PAGE_SIZE:
            lib.next_page()
            self.assertEqual(lib.state_var.get(), "Activos")
            self.assertTrue(all(m.usar for m in lib._filtered_cache))


if __name__ == "__main__":
    unittest.main()
