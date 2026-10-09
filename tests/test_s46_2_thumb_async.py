# -*- coding: utf-8 -*-
"""
F7777techMods — regresión S46.2 miniaturas async / hilo principal Tk.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import customtkinter as ctk  # noqa: E402

from app.core.library_catalog_model import CatalogModItem  # noqa: E402
from app.core.thumb_async import ThumbAsyncRuntime  # noqa: E402
from app.core.thumb_display import ThumbImageCache  # noqa: E402
from app.ui.views.library_visual_pane import LibraryVisualPane  # noqa: E402


def _png(path: Path, rgb: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (48, 48), rgb).save(path, format="PNG")


def _item(mod_id: str, preview: str) -> CatalogModItem:
    return CatalogModItem(
        game_id="g",
        mod_id=mod_id,
        display_name=mod_id,
        preview_path=preview,
        tags=[],
        category="",
        source="STAGING",
        state_label="Listo",
        state_tag="ready",
        plan_active=False,
        on_disk=True,
    )


class ThumbAsyncThreadTests(unittest.TestCase):
    def test_prefetch_on_done_runs_on_main_thread(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        seen: list[int] = []
        main_id = threading.get_ident()
        done = threading.Event()
        rt = ThumbAsyncRuntime(root, cache=ThumbImageCache(max_entries=4))
        rt.start_polling()
        self.addCleanup(rt.shutdown)

        def on_done():
            seen.append(threading.get_ident())
            done.set()

        rt.prefetch_missing({}, [], thumbs_dir=None, on_done=on_done)
        t0 = time.time()
        while not done.is_set() and time.time() - t0 < 5.0:
            root.update()
            time.sleep(0.02)
        self.assertTrue(done.is_set())
        self.assertEqual(seen, [main_id])

    def test_stale_paint_gen_does_not_apply(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name) / "a.png"
        _png(p, (200, 0, 0))
        cache = ThumbImageCache(max_entries=8)
        rt = ThumbAsyncRuntime(root, cache=cache)
        rt.start_polling()
        rt.set_session_gen(1)
        rt.set_paint_gen(1)
        applied: list[str] = []

        def ready(img):
            applied.append("old")

        rt.request_ctk_image(
            path=str(p),
            mod_id="m1",
            max_w=40,
            max_h=40,
            paint_gen=1,
            on_ready=ready,
        )
        rt.set_paint_gen(2)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            root.update()
            time.sleep(0.02)
        rt.shutdown()
        self.assertEqual(applied, [])

    def test_corrupt_file_leaves_placeholder(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        bad = Path(td.name) / "bad.png"
        bad.write_bytes(b"not-a-png")
        cache = ThumbImageCache(max_entries=8)
        rt = ThumbAsyncRuntime(root, cache=cache)
        rt.start_polling()
        rt.set_session_gen(1)
        rt.set_paint_gen(1)
        pane = LibraryVisualPane(root, on_click=lambda *_: None)
        pane.set_thumb_async(rt)
        pane.pack()
        items = [_item("mod_a", str(bad))]
        pane.start_paint(items, layout="visual_list", card_size="medium")
        t0 = time.time()
        while time.time() - t0 < 1.5:
            root.update()
            time.sleep(0.02)
        rt.shutdown()
        self.assertIn("mod_a", pane._widgets)


class VisualPaneStressTests(unittest.TestCase):
    def test_2000_synthetic_incremental_paint(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        shared = Path(td.name) / "one.png"
        _png(shared, (10, 120, 10))
        cache = ThumbImageCache(max_entries=64)
        rt = ThumbAsyncRuntime(root, cache=cache)
        rt.start_polling()
        rt.set_session_gen(1)
        pane = LibraryVisualPane(root, on_click=lambda *_: None)
        pane.set_thumb_async(rt)
        pane.pack(fill="both", expand=True)
        items = [_item(f"mod_{i:04d}", str(shared)) for i in range(2000)]
        t0 = time.perf_counter()
        pane.start_paint(items, layout="visual_list", card_size="medium")
        deadline = time.perf_counter() + 200.0
        while pane._idx < len(items) and time.perf_counter() < deadline:
            root.update()
            time.sleep(0.005)
        elapsed = time.perf_counter() - t0
        rt.shutdown()
        self.assertEqual(pane._idx, len(items))
        self.assertLess(elapsed, 195.0)

    def test_rapid_layout_switch_no_crash(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name) / "t.png"
        _png(p, (1, 2, 3))
        rt = ThumbAsyncRuntime(root, cache=ThumbImageCache(max_entries=32))
        rt.start_polling()
        rt.set_session_gen(1)
        pane = LibraryVisualPane(root, on_click=lambda *_: None)
        pane.set_thumb_async(rt)
        pane.pack()
        base = [_item(f"m{i}", str(p)) for i in range(80)]
        for layout in ("visual_list", "catalog", "visual_list"):
            pane.start_paint(base, layout=layout, card_size="medium")
            for _ in range(30):
                root.update()
                time.sleep(0.01)
        rt.shutdown()
        self.assertTrue(pane._widgets)


class LibraryReopenTests(unittest.TestCase):
    def test_destroy_during_load(self):
        from app.core.games import (  # noqa: E402
            GameRecord,
            GamesRegistry,
            ensure_game_data_dir,
            game_paths_for,
        )
        from app.core.inventory import ModEntry  # noqa: E402
        from tests.test_s06_ui import _make_mod  # noqa: E402

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        data = base / "data"
        data.mkdir()
        mods = base / "mods"
        stage = base / "stage"
        mods.mkdir()
        stage.mkdir()
        rec = GameRecord(
            id="s462",
            name="S462",
            mods_dir=str(mods),
            stage_dir=str(stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s462",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s462", games={"s462": rec})
        paths = game_paths_for(rec, app_data=data)
        ensure_game_data_dir(paths)
        mods_list = [_make_mod(i) for i in range(40)]

        from app import gui as gui_mod  # noqa: E402

        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.registry = reg
        app.session = paths
        app.mods = mods_list
        app.by_id = {m.folder: m for m in mods_list}
        app.show_view("library")
        app.view_library.layout_var.set("LISTA VISUAL")
        app.view_library.redraw()
        for _ in range(20):
            app.update()
            time.sleep(0.01)
        app._thumb_async.shutdown()
        app.destroy()
