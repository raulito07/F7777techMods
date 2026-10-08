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

Pruebas S02 — registro multijuego (solo temporales).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    add_game,
    remove_game,
    set_active_game,
    save_registry,
    load_registry,
    ensure_registry,
    game_paths_for,
    validate_game_paths,
    destination_conflict_message,
    prepare_ff7r_migration,
    execute_ff7r_migration_copy,
    make_ff7r_legacy_record,
)
from app.core.apply import plan_apply, execute, load_manifest  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.loadout_store import save_loadout, load_loadout  # noqa: E402


def _mod(folder: str, stage: Path, pak: str = "a.pak") -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=[pak],
        multi=False,
        on_disk=False,
        stage_path=str(stage),
        usar=True,
        pak_elegido=pak,
    )


class GamesS02Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.app_data = self.base / "data"
        self.app_data.mkdir()
        self.reg_path = self.app_data / "games.json"
        self.game_a_root = self.base / "gameA"
        self.game_b_root = self.base / "gameB"
        self.mods_a = self.game_a_root / "mods"
        self.mods_b = self.game_b_root / "mods"
        self.stage_a = self.base / "stageA"
        self.stage_b = self.base / "stageB"
        for p in (self.mods_a, self.mods_b, self.stage_a, self.stage_b):
            p.mkdir(parents=True)

    def tearDown(self):
        self._td.cleanup()

    def _rec(self, gid: str, name: str, mods: Path, stage: Path) -> GameRecord:
        return GameRecord(
            id=gid,
            name=name,
            mods_dir=str(mods),
            stage_dir=str(stage),
            game_root=str(mods.parent),
            adapter="generic_folder",
            platform="manual",
            data_mode="isolated",
            data_dir_name=gid,
        )

    def test_add_and_remove_game(self):
        reg = GamesRegistry()
        r = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        self.assertEqual(add_game(reg, r), [])
        save_registry(reg, self.reg_path)
        reg2 = load_registry(self.reg_path)
        self.assertIn("alpha", reg2.games)
        self.assertEqual(remove_game(reg2, "alpha"), [])
        self.assertNotIn("alpha", reg2.games)
        # datos en disco no se tocan al quitar del registro
        self.assertTrue(self.mods_a.exists())

    def test_switch_active_game(self):
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        b = self._rec("beta", "Beta", self.mods_b, self.stage_b)
        add_game(reg, a)
        add_game(reg, b)
        self.assertEqual(set_active_game(reg, "beta"), [])
        self.assertEqual(reg.active_game_id, "beta")
        paths = game_paths_for(reg.games["beta"], app_data=self.app_data)
        self.assertEqual(paths.mods_dir, self.mods_b)

    def test_validate_missing_paths(self):
        r = self._rec("x", "X", self.base / "missing_mods", self.stage_a)
        errs = validate_game_paths(r)
        self.assertTrue(any("no existe" in e for e in errs))

    def test_two_games_independent_data(self):
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        b = self._rec("beta", "Beta", self.mods_b, self.stage_b)
        add_game(reg, a)
        add_game(reg, b)
        pa = game_paths_for(a, app_data=self.app_data)
        pb = game_paths_for(b, app_data=self.app_data)
        pa.data_dir.mkdir(parents=True)
        pb.data_dir.mkdir(parents=True)
        save_loadout([_mod("m1", self.stage_a)], pa.loadout_json)
        save_loadout([_mod("m2", self.stage_b)], pb.loadout_json)
        self.assertNotEqual(pa.loadout_json, pb.loadout_json)
        self.assertIn("m1", load_loadout(pa.loadout_json))
        self.assertIn("m2", load_loadout(pb.loadout_json))
        self.assertNotIn("m1", load_loadout(pb.loadout_json))

    def test_cross_delete_protection(self):
        """Manifiesto de A no permite borrar archivos solo presentes en B."""
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        b = self._rec("beta", "Beta", self.mods_b, self.stage_b)
        add_game(reg, a)
        add_game(reg, b)
        pa = game_paths_for(a, app_data=self.app_data)
        pb = game_paths_for(b, app_data=self.app_data)
        pa.data_dir.mkdir(parents=True)
        pb.data_dir.mkdir(parents=True)

        # Foreign in A
        foreign = self.mods_a / "foreign.pak"
        foreign.write_bytes(b"FOREIGN")

        # Install into B
        mod_dir = self.stage_b / "ModB"
        mod_dir.mkdir()
        (mod_dir / "b.pak").write_bytes(b"BBB")
        plan_b = plan_apply([_mod("ModB", mod_dir, "b.pak")], pb.apply_context())
        execute(plan_b, pb.apply_context())
        self.assertTrue((self.mods_b / "b.pak").exists())

        # Apply empty plan on A — must NOT touch B, must keep foreign in A
        plan_a = plan_apply([], pa.apply_context())
        execute(plan_a, pa.apply_context())
        self.assertTrue(foreign.exists())
        self.assertTrue((self.mods_b / "b.pak").exists())
        self.assertEqual(load_manifest(pa.apply_context()), {})

    def test_shared_destination_blocked(self):
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        b = self._rec("beta", "Beta", self.mods_a, self.stage_b)  # same mods
        add_game(reg, a)
        errs = add_game(reg, b)
        self.assertTrue(errs)
        self.assertTrue(any("mismo destino" in e or "asignado" in e for e in errs))

    def test_persistence(self):
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        add_game(reg, a)
        reg.active_game_id = "alpha"
        save_registry(reg, self.reg_path)
        reg2 = load_registry(self.reg_path)
        self.assertEqual(reg2.active_game_id, "alpha")
        self.assertEqual(reg2.games["alpha"].mods_dir, str(self.mods_a))

    def test_ff7r_migration_prepare_and_copy(self):
        # Legacy files in app_data
        (self.app_data / "loadout.json").write_text('{"x":{"usar":true}}', encoding="utf-8")
        (self.app_data / "managed_manifest.json").write_text(
            '{"version":1,"files":{}}', encoding="utf-8"
        )
        reg = GamesRegistry()
        ff7 = make_ff7r_legacy_record(self.app_data)
        # Override paths to temp (no real Steam)
        ff7.mods_dir = str(self.mods_a)
        ff7.stage_dir = str(self.stage_a)
        ff7.game_root = str(self.game_a_root)
        reg.games[ff7.id] = ff7
        reg.active_game_id = ff7.id
        plan = prepare_ff7r_migration(reg, app_data=self.app_data)
        self.assertFalse(plan.blocked)
        self.assertIn("loadout.json", plan.files_to_copy)
        reg = execute_ff7r_migration_copy(reg, plan, registry_path=self.reg_path)
        self.assertEqual(reg.games[ff7.id].data_mode, "isolated")
        self.assertEqual(reg.games[ff7.id].migration_status, "complete")
        target = self.app_data / "games" / ff7.data_dir_name / "loadout.json"
        self.assertTrue(target.exists())
        # Original preserved
        self.assertTrue((self.app_data / "loadout.json").exists())

    def test_migration_blocked_on_conflict(self):
        (self.app_data / "loadout.json").write_text('{"a":1}', encoding="utf-8")
        target = self.app_data / "games" / "ff7r_remake"
        target.mkdir(parents=True)
        (target / "loadout.json").write_text('{"b":2}', encoding="utf-8")
        reg = GamesRegistry()
        ff7 = make_ff7r_legacy_record(self.app_data)
        ff7.mods_dir = str(self.mods_a)
        ff7.stage_dir = str(self.stage_a)
        ff7.game_root = str(self.game_a_root)
        reg.games[ff7.id] = ff7
        plan = prepare_ff7r_migration(reg, app_data=self.app_data)
        self.assertTrue(plan.blocked)

    def test_s01_engine_with_game_context(self):
        reg = GamesRegistry()
        a = self._rec("alpha", "Alpha", self.mods_a, self.stage_a)
        add_game(reg, a)
        paths = game_paths_for(a, app_data=self.app_data)
        paths.data_dir.mkdir(parents=True)
        mod_dir = self.stage_a / "ModA"
        mod_dir.mkdir()
        (mod_dir / "a.pak").write_bytes(b"AAA")
        ctx = paths.apply_context()
        plan = plan_apply([_mod("ModA", mod_dir)], ctx)
        self.assertFalse(plan.errors)
        execute(plan, ctx)
        self.assertEqual((self.mods_a / "a.pak").read_bytes(), b"AAA")
        self.assertIn("a.pak", load_manifest(ctx))

    def test_ensure_registry_creates_ff7r(self):
        (self.app_data / "loadout.json").write_text("{}", encoding="utf-8")
        reg = ensure_registry(self.reg_path, app_data=self.app_data)
        self.assertIn("ff7r_remake", reg.games)
        self.assertEqual(reg.games["ff7r_remake"].data_mode, "legacy_root")
        self.assertEqual(reg.games["ff7r_remake"].migration_status, "pending")


if __name__ == "__main__":
    unittest.main()
