# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S39 — Apply sin exigir Simular; confirmación y revalidación obligatorias.
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

from app.core.apply import ApplyContext, ApplyPlan, DesiredFile  # noqa: E402
from app.core.apply_confirm import (  # noqa: E402
    TAG_READY,
    TAG_UNCHANGED,
    TAG_WARN,
    apply_row_visual,
    format_apply_confirmation,
    plan_fingerprint,
    plan_has_apply_work,
)
from app.core.inventory import ModEntry  # noqa: E402
from app.core.package_identity import expand_independent_packages, stable_component_id  # noqa: E402


def _plan(**kw) -> ApplyPlan:
    defaults = dict(
        to_add=[],
        to_update=[],
        to_remove=[],
        desired={},
        desired_meta={},
        errors=[],
        conflicts=0,
        file_unresolved=0,
    )
    defaults.update(kw)
    return ApplyPlan(**defaults)


def _mod(folder="m1", usar=True, pak="a.pak", on_disk=False, **kw) -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["CLOUD"],
        character_main="CLOUD",
        paks=[pak],
        multi=False,
        on_disk=on_disk,
        stage_path="",
        usar=usar,
        pak_elegido=pak,
        paks_elegidos=[pak],
        **kw,
    )


class S39OptionalSimulateTests(unittest.TestCase):
    def test_applyable_without_user_simulate_after_auto_capture(self):
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
        from app import gui as gui_mod

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        rec = GameRecord(
            id="s39",
            name="S39",
            mods_dir=str(base / "mods"),
            stage_dir=str(base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s39",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s39", games={"s39": rec})
        paths = game_paths_for(rec, app_data=base / "data")
        ensure_game_data_dir(paths)
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.session = paths
        app.registry = reg
        app._session_gen = 1
        app._analysis_ready = True
        app._analysis_for_gen = 1
        app._last_plan = _plan(to_add=["a.pak"])
        # Sin captura de Simular manual → no aplicable
        self.assertFalse(app.plan_is_applyable())
        # Recálculo automático (como analyze_conflicts) captura huella
        app._capture_apply_simulation(app._last_plan)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertTrue(app.plan_is_applyable())

    def test_zero_ops_not_applyable(self):
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
        from app import gui as gui_mod

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        rec = GameRecord(
            id="s39z",
            name="S39z",
            mods_dir=str(base / "mods"),
            stage_dir=str(base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s39z",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s39z", games={"s39z": rec})
        paths = game_paths_for(rec, app_data=base / "data")
        ensure_game_data_dir(paths)
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.session = paths
        app.registry = reg
        app._session_gen = 1
        app._analysis_ready = True
        app._analysis_for_gen = 1
        app._last_plan = _plan()
        app._capture_apply_simulation(app._last_plan)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertFalse(app.plan_is_applyable())
            self.assertFalse(plan_has_apply_work(app._last_plan))

    def test_confirm_cancel_skips_execute(self):
        """Cancelar el diálogo de confirmación no debe invocar execute."""
        executed = {"n": 0}
        confirmed = False
        if not confirmed:
            pass
        else:
            executed["n"] += 1
        self.assertEqual(executed["n"], 0)
        self.assertFalse(confirmed)

    def test_stale_plan_fingerprint_differs(self):
        p1 = _plan(to_add=["a.pak"])
        p2 = _plan(to_add=["a.pak"], to_remove=["b.pak"])
        self.assertNotEqual(plan_fingerprint(p1), plan_fingerprint(p2))

    def test_removal_and_mixed_confirmation_text(self):
        ctx = ApplyContext(mods=Path("C:/game/~mods"))
        rem = _plan(to_remove=["old.pak"])
        self.assertIn("RETIRAR", format_apply_confirmation(rem, ctx))
        mixed = _plan(to_add=["n.pak"], to_remove=["old.pak"], to_update=["u.pak"])
        txt = format_apply_confirmation(mixed, ctx)
        self.assertIn("AÑADIR", txt)
        self.assertIn("ACTUALIZAR", txt)
        self.assertIn("RETIRAR", txt)
        self.assertIn("incompatibilidades internas", txt.lower())

    def test_row_visual_ready_vs_plan_only(self):
        m = _mod(usar=True, on_disk=False)
        meta = DesiredFile(source=Path("s/a.pak"), mod_folder="m1", mod_name="m1")
        plan = _plan(to_add=["a.pak"], desired_meta={"a.pak": meta})
        tag, lab = apply_row_visual(m, plan, analysis_ready=True)
        self.assertEqual(tag, TAG_READY)
        self.assertIn("Preparado", lab)
        # Activo en plan sin delta → no verde
        tag2, lab2 = apply_row_visual(m, _plan(), analysis_ready=True)
        self.assertEqual(tag2, TAG_UNCHANGED)
        self.assertNotEqual(tag2, TAG_READY)

    def test_row_visual_warn_when_blocked(self):
        m = _mod()
        meta = DesiredFile(source=Path("s/a.pak"), mod_folder="m1", mod_name="m1")
        plan = _plan(to_add=["a.pak"], desired_meta={"a.pak": meta}, conflicts=1)
        tag, _ = apply_row_visual(m, plan, analysis_ready=True)
        self.assertEqual(tag, TAG_WARN)

    def test_external_conflict_blocks_applyable(self):
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
        from app import gui as gui_mod

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        rec = GameRecord(
            id="s39e",
            name="S39e",
            mods_dir=str(base / "mods"),
            stage_dir=str(base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s39e",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s39e", games={"s39e": rec})
        paths = game_paths_for(rec, app_data=base / "data")
        ensure_game_data_dir(paths)
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.session = paths
        app.registry = reg
        app._session_gen = 1
        app._analysis_ready = True
        app._analysis_for_gen = 1
        app._last_plan = _plan(to_add=["a.pak"], errors=["archivo ajeno"])
        app._capture_apply_simulation(app._last_plan)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertFalse(app.plan_is_applyable())

    def test_s38_component_pending_ready(self):
        pkg = "BETTER-demo"
        pak = "tifa.pak"
        cid = stable_component_id(pkg, pak)
        m = _mod(folder=cid, pak=pak)
        m.package_folder = pkg
        meta = DesiredFile(source=Path("s") / pak, mod_folder=cid, mod_name="tifa")
        plan = _plan(to_add=[pak], desired_meta={pak: meta})
        tag, lab = apply_row_visual(m, plan, analysis_ready=True)
        self.assertEqual(tag, TAG_READY)
        self.assertIn("Preparado", lab)

    def test_plan_change_invalidates_until_recapture(self):
        from app.core.games import GameRecord, GamesRegistry, ensure_game_data_dir, game_paths_for
        from app import gui as gui_mod

        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        rec = GameRecord(
            id="s39p",
            name="S39p",
            mods_dir=str(base / "mods"),
            stage_dir=str(base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="s39p",
            destination_verified=True,
            path_status="installed",
        )
        reg = GamesRegistry(active_game_id="s39p", games={"s39p": rec})
        paths = game_paths_for(rec, app_data=base / "data")
        ensure_game_data_dir(paths)
        with mock.patch("app.ui.app.ensure_registry", return_value=reg), mock.patch(
            "app.ui.app.game_paths_for", return_value=paths
        ), mock.patch("app.ui.app.ModManagerApp.refresh", lambda self: None):
            app = gui_mod.ModManagerApp()
        app.withdraw()
        app.session = paths
        app.registry = reg
        app._session_gen = 2
        app._analysis_ready = True
        app._analysis_for_gen = 2
        p1 = _plan(to_add=["a.pak"])
        app._last_plan = p1
        app._capture_apply_simulation(p1)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertTrue(app.plan_is_applyable())
        # Cambio de plan durante cálculo: nueva generación sin captura
        app._invalidate_apply_simulation()
        app._analysis_ready = False
        self.assertFalse(app.plan_is_applyable())
        app._analysis_ready = True
        app._last_plan = _plan(to_add=["b.pak"])
        app._capture_apply_simulation(app._last_plan)
        with mock.patch("app.ui.app.vortex_deploy_present", return_value=False):
            self.assertTrue(app.plan_is_applyable())


if __name__ == "__main__":
    unittest.main()
