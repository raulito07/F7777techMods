# -*- coding: utf-8 -*-
"""S46.1 — selección compartida y cambio de presentación."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.library_selection import LibrarySelection  # noqa: E402
from app.core.library_view_prefs import (  # noqa: E402
    LAYOUT_CATALOG,
    LAYOUT_TABLE,
    LAYOUT_VISUAL_LIST,
    UI_LABEL_FULL,
    UI_LAYOUT_CATALOG,
    UI_LAYOUT_TABLE,
    UI_LAYOUT_VISUAL,
)


class LibrarySelectionUnitTests(unittest.TestCase):
    def test_shift_range(self):
        sel = LibrarySelection()
        order = ["a", "b", "c", "d", "e"]
        sel.click("a", visible_order=order, ctrl=False, shift=False)
        sel.click("d", visible_order=order, ctrl=False, shift=True)
        self.assertEqual(sel.selected, {"a", "b", "c", "d"})

    def test_ctrl_toggle(self):
        sel = LibrarySelection()
        order = ["a", "b"]
        sel.click("a", visible_order=order, ctrl=False, shift=False)
        sel.click("b", visible_order=order, ctrl=True, shift=False)
        self.assertEqual(sel.selected, {"a", "b"})
        sel.click("a", visible_order=order, ctrl=True, shift=False)
        self.assertEqual(sel.selected, {"b"})


class LibrarySelectionUiTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.data = self.base / "data"
        self.mods = self.base / "mods"
        self.stage = self.base / "stage"
        for p in (self.data, self.mods, self.stage):
            p.mkdir()

    def tearDown(self):
        app = getattr(self, "_app_inst", None)
        if app:
            try:
                app.destroy()
            except Exception:
                pass
        self._td.cleanup()

    def _app(self, n: int = 30):
        from app import gui as gui_mod
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for

        for i in range(n):
            d = self.stage / f"Mod-{i}"
            d.mkdir(exist_ok=True)
            (d / f"f{i}.dat").write_bytes(b"x")
        rec = GameRecord(
            id="generic_rpg",
            name="Generic RPG",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="generic_rpg",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="generic_rpg", games={"generic_rpg": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)
        with mock.patch.dict("os.environ", {"SGM_DATA_DIR": str(self.data)}), mock.patch(
            "app.ui.app.ensure_registry", return_value=reg
        ), mock.patch("app.ui.app.game_paths_for", return_value=paths):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        self._app_inst = app
        app.registry = reg
        app.session = paths
        app.refresh()
        return app

    def test_layout_switch_keeps_selection_and_plan(self):
        app = self._app(25)
        lib = app.view_library
        lib.redraw()
        m0 = app.mods[0]
        m1 = app.mods[1]
        before_plan = [(x.folder, x.usar) for x in app.mods]
        lib._library_sel.set_folders([m0.folder, m1.folder])
        lib.layout_var.set(UI_LAYOUT_CATALOG)
        lib._on_layout_change()
        self.assertIn(m0.folder, lib._library_sel.selected)
        lib.layout_var.set(UI_LAYOUT_TABLE)
        lib._on_layout_change()
        self.assertEqual(lib._library_sel.selected, {m0.folder, m1.folder})
        after_plan = [(x.folder, x.usar) for x in app.mods]
        self.assertEqual(before_plan, after_plan)

    def _pump(self, app, lib, n: int) -> None:
        for _ in range(80):
            app.update_idletasks()
            app.update()
            if lib._layout_mode == LAYOUT_TABLE:
                break
            if lib.visual_pane._idx >= n and len(lib.visual_pane._widgets) >= n:
                break

    def test_full_view_all_layouts(self):
        app = self._app(40)
        lib = app.view_library
        lib.view_mode_var.set(UI_LABEL_FULL)
        lib._on_view_mode_change()
        for layout in (UI_LAYOUT_TABLE, UI_LAYOUT_VISUAL, UI_LAYOUT_CATALOG):
            lib.layout_var.set(layout)
            lib._on_layout_change()
            lib.redraw()
            self._pump(app, lib, 40)
            if layout == UI_LAYOUT_TABLE:
                self.assertEqual(len(lib.tree.get_children()), 40)
            else:
                self.assertEqual(len(lib.visual_pane._widgets), 40)


if __name__ == "__main__":
    unittest.main()
