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

S27 — estados independientes, filtros combinados, inventarios grandes (sandbox).
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

from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
from app.core.inventory import ModEntry
from app.core.library_status import (
    ACTIVO_EN_PLAN,
    ARCHIVADO_VERIFICADO,
    CONFLICTO,
    DISPONIBLE_EN_WORK,
    INSTALADO_REAL,
    STAGING_VORTEX,
    archive_candidates,
    compute_mod_status,
    filter_mods,
    work_restore_candidates,
)


def _mod(i: int, **kw) -> ModEntry:
    folder = f"Mod_{i:04d}"
    return ModEntry(
        folder=folder,
        name=f"Mod Name {i}",
        characters=["OTROS"],
        character_main="OTROS",
        paks=[f"file_{i}.pak"],
        multi=kw.get("multi", False),
        on_disk=kw.get("on_disk", False),
        stage_path=str(Path(f"/tmp/stage/{folder}")),
        usar=kw.get("usar", False),
        pak_elegido=kw.get("pak_elegido", f"file_{i}.pak"),
        description=f"desc {i}",
        source_kind=kw.get("source_kind", "STAGING_VORTEX"),
        archived=kw.get("archived", False),
        work_extracted=kw.get("work_extracted", False),
        archive_path=kw.get("archive_path", ""),
        archive_zip_sha256=kw.get("archive_zip_sha256", ""),
        conflicto=kw.get("conflicto", ""),
        author=kw.get("author", ""),
    )


class S27LibraryStatusTests(unittest.TestCase):
    def test_independent_flags_coexist(self):
        m = _mod(
            1,
            usar=True,
            on_disk=True,
            archived=True,
            archive_zip_sha256="abc",
            work_extracted=True,
            source_kind="WORK_LIBRARY",
            conflicto="Choque con X",
        )
        st = compute_mod_status(m)
        self.assertTrue(st.has(ACTIVO_EN_PLAN))
        self.assertTrue(st.has(INSTALADO_REAL))
        self.assertTrue(st.has(ARCHIVADO_VERIFICADO))
        self.assertTrue(st.has(DISPONIBLE_EN_WORK))
        self.assertTrue(st.has(CONFLICTO))

    def test_vortex_enabled_not_implied_by_staging(self):
        m = _mod(2, usar=False, on_disk=False, source_kind="STAGING_VORTEX")
        st = compute_mod_status(m)
        self.assertTrue(st.has(STAGING_VORTEX))
        self.assertFalse(st.has(INSTALADO_REAL))
        self.assertFalse(st.has(ACTIVO_EN_PLAN))

    def test_filter_query_case_insensitive_partial(self):
        mods = [_mod(i) for i in range(20)]
        mods[5].name = "Cool Cloud Outfit"
        got = filter_mods(mods, query="cloud OUT")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].folder, "Mod_0005")

    def test_combined_filters(self):
        mods = [
            _mod(0, usar=True, on_disk=False),
            _mod(1, usar=True, on_disk=True),
            _mod(2, usar=False, archived=True, archive_path="x.zip"),
            _mod(3, source_kind="WORK_LIBRARY", work_extracted=True),
        ]
        plan = filter_mods(mods, dimension="Activo en plan")
        self.assertEqual({m.folder for m in plan}, {"Mod_0000", "Mod_0001"})
        inst = filter_mods(mods, dimension="Instalado real")
        self.assertEqual([m.folder for m in inst], ["Mod_0001"])
        zipf = filter_mods(mods, dimension="Archivado ZIP")
        self.assertEqual([m.folder for m in zipf], ["Mod_0002"])
        work = filter_mods(mods, dimension="En WORK", source="WORK")
        self.assertEqual([m.folder for m in work], ["Mod_0003"])

    def test_candidates_do_not_mutate(self):
        mods = [
            _mod(0, source_kind="STAGING_VORTEX"),
            _mod(1, archived=True, archive_zip_sha256="h"),
            _mod(2, archived=True, archive_path="a.zip", work_extracted=True),
        ]
        ac = archive_candidates(mods)
        wc = work_restore_candidates(mods)
        self.assertEqual([m.folder for m in ac], ["Mod_0000"])
        self.assertEqual([m.folder for m in wc], ["Mod_0001"])
        self.assertFalse(mods[0].archived)

    def test_large_inventory_filter_performance(self):
        mods = []
        for i in range(1200):
            mods.append(
                _mod(
                    i,
                    usar=(i % 5 == 0),
                    on_disk=(i % 11 == 0),
                    archived=(i % 17 == 0),
                    archive_path=("z.zip" if i % 17 == 0 else ""),
                    work_extracted=(i % 13 == 0),
                    source_kind="WORK_LIBRARY" if i % 13 == 0 else "STAGING_VORTEX",
                    conflicto="Choque" if i % 23 == 0 and i % 5 == 0 else "",
                )
            )
        t0 = time.perf_counter()
        out = filter_mods(mods, query="name", dimension="Activo en plan", source="VORTEX")
        elapsed = time.perf_counter() - t0
        self.assertGreater(len(out), 0)
        self.assertLess(elapsed, 0.75, f"filtro 1200 mods demasiado lento: {elapsed:.3f}s")
        t1 = time.perf_counter()
        for m in mods:
            compute_mod_status(m)
        elapsed2 = time.perf_counter() - t1
        self.assertLess(elapsed2, 0.75, f"status 1200 mods: {elapsed2:.3f}s")


class S27LibraryUiTests(unittest.TestCase):
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

    def _app(self, n_mods: int = 80):
        from app import gui as gui_mod

        rec = GameRecord(
            id="s27_tmp",
            name="S27 Temp",
            mods_dir=str(self.mods),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s27_tmp",
            destination_verified=True,
            path_status="installed",
            install_mode="COPY",
        )
        reg = GamesRegistry(active_game_id="s27_tmp", games={"s27_tmp": rec})
        paths = game_paths_for(rec, app_data=self.data)
        ensure_game_data_dir(paths)
        mods = [_mod(i, usar=(i % 4 == 0), on_disk=(i % 9 == 0)) for i in range(n_mods)]
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

    def test_clear_filters_and_result_count(self):
        app = self._app(100)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        lib.search_var.set("Name 1")
        lib.state_var.set("Activo en plan")
        lib.redraw()
        n_filt = len(lib._filtered_cache)
        self.assertLess(n_filt, 100)
        self.assertIn(str(n_filt), lib.count_label.cget("text"))
        lib.clear_filters()
        self.assertEqual(lib.state_var.get(), "TODOS")
        self.assertEqual(lib.search_var.get(), "")
        self.assertEqual(len(lib._filtered_cache), 100)

    def test_multi_select_and_candidates(self):
        app = self._app(60)
        self._app_inst = app
        app.mods[0].archived = False
        app.mods[0].source_kind = "STAGING_VORTEX"
        app.mods[1].archived = True
        app.mods[1].archive_zip_sha256 = "deadbeef"
        app.mods[1].work_extracted = False
        app.show_view("library")
        lib = app.view_library
        lib.redraw()
        lib.select_archive_candidates()
        self.assertTrue(app._bulk_filter_folders)
        lib.select_work_candidates()
        self.assertIn(app.mods[1].folder, app._bulk_filter_folders or [])

    def test_pagination_stable_filter_cache(self):
        app = self._app(120)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        lib.page_size_var.set("40")
        lib.redraw()
        total = len(lib._filtered_cache)
        self.assertEqual(total, 120)
        lib.next_page()
        self.assertEqual(lib.page, 1)
        self.assertEqual(len(lib._filtered_cache), total)
        self.assertLessEqual(len(lib.tree.get_children()), 40)
        first = lib.tree.get_children()[0]
        lib.tree.selection_set(first)
        lib.redraw()
        if lib.tree.exists(first):
            self.assertIn(first, lib.tree.selection())

    def test_detail_shows_independent_flags(self):
        app = self._app(10)
        self._app_inst = app
        app.show_view("library")
        lib = app.view_library
        lib.redraw()
        m = app.mods[0]
        m.usar = True
        m.on_disk = True
        lib.tree.selection_set(m.folder)
        lib.on_select()
        txt = lib.detail_badges.cget("text")
        self.assertIn("ACTIVO_EN_PLAN", txt)
        self.assertIn("INSTALADO_REAL", txt)

    def test_clean_boot_temp_data(self):
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "d"
            clean.mkdir()
            env = {**os.environ, "SGM_DATA_DIR": str(clean)}
            with mock.patch.dict(os.environ, env, clear=False):
                import importlib
                import app.core.paths as paths_mod

                importlib.reload(paths_mod)
                self.assertEqual(paths_mod.DATA.resolve(), clean.resolve())


if __name__ == "__main__":
    unittest.main()
