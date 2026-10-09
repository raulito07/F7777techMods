# -*- coding: utf-8 -*-
"""S45 — vista Biblioteca paginada vs completa."""

from __future__ import annotations

import json
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
from app.core.library_view_prefs import (  # noqa: E402
    MODE_FULL,
    MODE_PAGINATED,
    UI_LABEL_FULL,
    UI_LABEL_PAGINATED,
    display_slice,
    list_summary_text,
    load_library_view_mode,
    save_library_view_mode,
)
from app.ui.theme import LIBRARY_PAGE_SIZE  # noqa: E402


def _mods(n: int) -> list[ModEntry]:
    return [
        ModEntry(
            folder=f"Mod-{i}",
            name=f"Mod Name {i}",
            characters=["OTROS"],
            character_main="OTROS",
            paks=[],
            multi=False,
            on_disk=False,
            stage_path="",
            usar=i % 3 == 0,
        )
        for i in range(n)
    ]


class LibraryViewPrefsTests(unittest.TestCase):
    def test_display_slice_paginated_and_full(self):
        data = list(range(250))
        page = display_slice(data, mode=MODE_PAGINATED, page=1, page_size=80)
        self.assertEqual(len(page), 80)
        self.assertEqual(page[0], 80)
        full = display_slice(data, mode=MODE_FULL, page=99, page_size=40)
        self.assertEqual(len(full), 250)

    def test_summary_text_modes(self):
        h, p, w = list_summary_text(
            mode=MODE_FULL,
            total_filtered=600,
            page=0,
            page_size=80,
            total_in_memory=600,
        )
        self.assertIn("vista completa", h.lower())
        self.assertTrue(w)
        h2, p2, w2 = list_summary_text(
            mode=MODE_PAGINATED,
            total_filtered=100,
            page=0,
            page_size=40,
            total_in_memory=100,
        )
        self.assertIn("Página 1", h2)
        self.assertIn("40", p2)
        self.assertFalse(w2)

    def test_persistence_per_game(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ui_settings.json"
            save_library_view_mode("game_a", MODE_FULL, settings_path=path)
            self.assertEqual(load_library_view_mode("game_a", settings_path=path), MODE_FULL)
            save_library_view_mode("game_b", MODE_PAGINATED, settings_path=path)
            self.assertEqual(load_library_view_mode("game_b", settings_path=path), MODE_PAGINATED)
            self.assertEqual(load_library_view_mode("game_a", settings_path=path), MODE_FULL)
            blob = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("library_view_by_game", blob)


class LibraryViewUITests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.mods = self.base / "mods"
        self.data = self.base / "data"
        self.stage.mkdir()
        self.mods.mkdir()
        self.data.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def tearDown(self):
        app = getattr(self, "_app_inst", None)
        if app is not None:
            try:
                app.destroy()
            except Exception:
                pass

    def _app(self, n: int):
        from app import gui as gui_mod
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for

        for i in range(n):
            d = self.stage / f"Mod-{i}"
            d.mkdir(exist_ok=True)
            (d / f"file_{i}.pak").write_bytes(b"PK")
        rec = GameRecord(
            id="g1",
            name="Test",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="g1",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="g1", games={"g1": rec})
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

    def test_full_view_shows_all_filtered(self):
        app = self._app(120)
        lib = app.view_library
        lib.view_mode_var.set(UI_LABEL_FULL)
        lib._on_view_mode_change()
        lib.redraw()
        self.assertEqual(len(lib.tree.get_children()), len(lib._filtered_cache))
        self.assertTrue(lib.is_full_view())

    def test_pagination_regression(self):
        app = self._app(220)
        lib = app.view_library
        lib.view_mode_var.set(UI_LABEL_PAGINATED)
        lib._on_view_mode_change()
        lib.redraw()
        self.assertLessEqual(len(lib.tree.get_children()), LIBRARY_PAGE_SIZE + 1)

    def test_full_view_filter_and_selection(self):
        app = self._app(50)
        lib = app.view_library
        lib.view_mode_var.set(UI_LABEL_FULL)
        lib._on_view_mode_change()
        lib.state_var.set("Activos")
        lib.redraw()
        self.assertTrue(all(m.usar for m in lib._filtered_cache))
        lib.select_filtered()
        self.assertEqual(len(lib.tree.selection()), len(lib._filtered_cache))

    def test_large_list_redraw_time(self):
        app = self._app(800)
        lib = app.view_library
        lib.view_mode_var.set(UI_LABEL_FULL)
        lib._on_view_mode_change()
        t0 = time.perf_counter()
        lib.redraw()
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(lib.tree.get_children()), 800)
        self.assertLess(elapsed, 8.0, msg=f"redraw lento: {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
