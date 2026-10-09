# -*- coding: utf-8 -*-
"""S46.3 — lógica de fases/cierre del benchmark (sin juego real)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bench_presentations_phases import (  # noqa: E402
    apply_layout,
    drain_visual_paint_sync,
    wait_visual_incremental,
)


class _FakeVp:
    def __init__(self, total: int) -> None:
        self._items = [object()] * total
        self._idx = 0
        self._gen = 1

    def tick(self, n: int = 1) -> None:
        self._idx = min(len(self._items), self._idx + n)

    def _paint_batch(self, gen: int) -> None:
        self.tick(4)


class _FakeApp:
    def update(self) -> None:
        pass


class BenchPhaseLogicTests(unittest.TestCase):
    def test_drain_visual_completes(self):
        vp = _FakeVp(10)
        info = drain_visual_paint_sync(vp, vp._gen, max_batches=20)
        self.assertTrue(info["done"])
        self.assertEqual(info["visual_idx"], 10)
        self.assertEqual(info["reason"], "complete")

    def test_drain_max_batches_exits(self):
        vp = _FakeVp(10)
        vp._paint_batch = lambda gen: None  # type: ignore[method-assign]
        info = drain_visual_paint_sync(vp, vp._gen, max_batches=3)
        self.assertFalse(info["done"])
        self.assertEqual(info["reason"], "max_batches")

    def test_wait_visual_empty_exits_immediately(self):
        vp = _FakeVp(0)
        info = wait_visual_incremental(_FakeApp(), vp, timeout_sec=1.0)
        self.assertTrue(info["done"])
        self.assertEqual(info["reason"], "empty")

    def test_apply_layout_syncs_mode(self):
        from app.core.library_view_prefs import LAYOUT_CATALOG, LAYOUT_TABLE  # noqa: E402

        lib = mock.Mock()
        lib.layout_var = mock.Mock()
        lib._layout_mode = LAYOUT_TABLE
        apply_layout(lib, "CATÁLOGO")
        lib._switch_layout_display.assert_called_once()
        self.assertEqual(lib._layout_mode, LAYOUT_CATALOG)


if __name__ == "__main__":
    unittest.main()
