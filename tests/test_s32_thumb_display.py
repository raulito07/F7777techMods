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

Regresión: miniaturas tras navegación prolongada (caché, PIL, CTk).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    ensure_game_data_dir,
    game_paths_for,
)
from app.core.inventory import ModEntry  # noqa: E402
from app.core.thumb_display import ThumbImageCache  # noqa: E402
from tests.test_s06_ui import _make_mod  # noqa: E402


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path, format="PNG")


class ThumbDisplayUnitTests(unittest.TestCase):
    def test_lru_bounds_and_reuse(self):
        cache = ThumbImageCache(max_entries=4)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        paths = []
        for i in range(6):
            p = base / f"t{i}.png"
            _write_png(p, (i * 30 % 255, 40, 80))
            paths.append(p)

        keys_seen = set()
        for p in paths:
            img = cache.get_ctk_image(str(p), 120, 80)
            keys_seen.add(id(img))
        self.assertLessEqual(len(cache._cache), 4)

        again = cache.get_ctk_image(str(paths[-1]), 120, 80)
        self.assertIs(again, cache.get_ctk_image(str(paths[-1]), 120, 80))

    def test_many_loads_without_open_leak(self):
        cache = ThumbImageCache(max_entries=32)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = Path(td.name) / "one.png"
        _write_png(p, (200, 100, 50))
        for _ in range(150):
            img = cache.get_ctk_image(str(p), 300, 160)
            self.assertIsNotNone(img.cget("size"))

    def test_missing_file_raises(self):
        cache = ThumbImageCache()
        with self.assertRaises(FileNotFoundError):
            cache.get_ctk_image(str(Path("/nonexistent/x.png")), 10, 10)


class ThumbNavigationUITests(unittest.TestCase):
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

    def _app(self, n_mods: int):
        from unittest import mock

        from app import gui as gui_mod

        rec = GameRecord(
            id="s32_tmp",
            name="S32 Temp",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s32_tmp",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s32_tmp", games={"s32_tmp": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)
        mods = [_make_mod(i) for i in range(n_mods)]
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

    def test_120_sequential_thumb_paints(self):
        app = self._app(120)
        self._app_inst = app
        thumbs = app.session.thumbs_dir
        thumbs.mkdir(parents=True, exist_ok=True)
        for i, m in enumerate(app.mods):
            p = thumbs / f"thumb_{i:04d}.png"
            _write_png(p, (i % 255, (i * 3) % 255, 100))
            m.thumb_path = str(p)

        app.show_view("library")
        label = app.view_library.detail_image
        for m in app.mods:
            app.show_thumb_for(m, label)
            app.update_idletasks()
            ref = getattr(label, "_sgm_thumb_ref", None)
            self.assertIsNotNone(ref, msg=f"sin imagen tras {m.folder}")

        for _ in range(30):
            m = app.mods[_ % len(app.mods)]
            app.show_thumb_for(m, label)
        self.assertIsNotNone(getattr(label, "_sgm_thumb_ref", None))

    def test_placeholder_and_retry_after_bad_path(self):
        app = self._app(3)
        self._app_inst = app
        m = app.mods[0]
        app.show_view("library")
        label = app.view_library.detail_image
        bad = Path(app.session.thumbs_dir) / "corrupt.png"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"not-a-png")
        m.thumb_path = str(bad)
        app._paint_thumb(str(bad), label, mod_folder=m.folder)
        self.assertIn("reintentar", str(label.cget("text")).lower())

        good = Path(app.session.thumbs_dir) / "ok.png"
        _write_png(good, (10, 20, 30))
        m.thumb_path = str(good)
        label._sgm_thumb_path = str(good)  # type: ignore[attr-defined]
        app.view_library.tree.selection_set(m.folder)
        app.retry_detail_image()
        app.update_idletasks()
        self.assertIsNotNone(getattr(label, "_sgm_thumb_ref", None))


if __name__ == "__main__":
    unittest.main()
