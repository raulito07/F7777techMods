# -*- coding: utf-8 -*-
"""S46 — Biblioteca universal (modelo, filtros, rendimiento)."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.inventory import ModEntry  # noqa: E402
from app.core.library_catalog_model import (  # noqa: E402
    build_catalog_item,
    collect_tags_from_mods,
    mod_matches_tag,
    tags_for_mod,
)
from app.core.library_status import compute_mod_status, filter_mods  # noqa: E402
from app.core.library_view_prefs import (  # noqa: E402
    LAYOUT_CATALOG,
    load_library_layout,
    save_library_layout,
)


def _generic_mod(i: int, *, ext: str = ".dat") -> ModEntry:
    return ModEntry(
        folder=f"mod_{i}",
        name=f"Universal Mod {i}",
        characters=["OTROS"],
        character_main="OTROS",
        paks=[f"content_{i}{ext}"] if ext else [],
        multi=False,
        on_disk=False,
        stage_path="",
        usar=i % 4 == 0,
        category="Gameplay" if i % 2 == 0 else "Audio",
        source_kind="WORK_LIBRARY" if i % 5 == 0 else "STAGING_VORTEX",
    )


class S46CatalogModelTests(unittest.TestCase):
    def test_non_ff7_mod_tags_and_filter(self):
        m = _generic_mod(5, ext=".zip")
        m.category = "UI"
        tags = tags_for_mod(m)
        self.assertIn("UI", tags)
        self.assertIn("WORK", tags)
        self.assertTrue(mod_matches_tag(m, "UI"))
        self.assertFalse(mod_matches_tag(m, "CLOUD"))

    def test_catalog_item_no_pak_assumption(self):
        m = _generic_mod(2, ext=".bundle")
        st = compute_mod_status(m)
        item = build_catalog_item(m, game_id="rpg_demo", status=st, state_tag="off", state_label="Off")
        self.assertEqual(item.game_id, "rpg_demo")
        self.assertEqual(item.preview_path, "")

    def test_layout_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ui.json"
            save_library_layout("demo_game", LAYOUT_CATALOG, settings_path=p)
            self.assertEqual(load_library_layout("demo_game", settings_path=p), LAYOUT_CATALOG)

    def test_filter_by_tag_not_character(self):
        mods = [_generic_mod(i) for i in range(20)]
        out = filter_mods(mods, tag="Gameplay")
        self.assertTrue(all("Gameplay" in tags_for_mod(m) for m in out))

    def test_plan_unchanged_when_building_catalog(self):
        mods = [_generic_mod(i) for i in range(50)]
        before = [(m.folder, m.usar) for m in mods]
        for m in mods:
            build_catalog_item(
                m,
                game_id="x",
                status=compute_mod_status(m),
                state_tag="off",
                state_label="x",
            )
        after = [(m.folder, m.usar) for m in mods]
        self.assertEqual(before, after)


class S46PerformanceTests(unittest.TestCase):
    def test_build_2000_catalog_items(self):
        mods = [_generic_mod(i, ext=f".f{i % 3}") for i in range(2000)]
        t0 = time.perf_counter()
        for m in mods:
            build_catalog_item(
                m,
                game_id="perf",
                status=compute_mod_status(m),
                state_tag="unchanged",
                state_label="OK",
            )
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 12.0, msg=f"lento: {elapsed:.2f}s")

    def test_collect_tags_2000(self):
        mods = [_generic_mod(i) for i in range(2000)]
        t0 = time.perf_counter()
        tags = collect_tags_from_mods(mods)
        elapsed = time.perf_counter() - t0
        self.assertGreater(len(tags), 2)
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
