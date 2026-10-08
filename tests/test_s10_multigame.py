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

S10 — perfiles independientes, destino pendiente, adaptadores, aislamiento.
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

from app.core.adapters import get_adapter  # noqa: E402
from app.core.apply import ApplyContext, ApplyError, execute, plan_apply  # noqa: E402
from app.core.conflict_engine import ConflictSettings, semantic_enabled as sem_eng  # noqa: E402
from app.core.content_classify import classify_mod  # noqa: E402
from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    ensure_registry,
    ensure_s10_profiles,
    game_paths_for,
    make_ff7_rebirth_record,
    make_stellar_blade_record,
    save_registry,
    validate_game_paths,
)
from app.core.inventory import ModEntry  # noqa: E402


def _mod(folder: str, stage: Path, files: dict[str, bytes], *, usar=True) -> ModEntry:
    d = stage / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (d / name).write_bytes(data)
    paks = [n for n in files if n.lower().endswith(".pak")]
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(d),
        usar=usar,
        pak_elegido=paks[0] if len(paks) == 1 else "",
    )


class S10MultigameTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.data = self.base / "data"
        self.data.mkdir()
        self.reg_path = self.data / "games.json"

    def tearDown(self):
        self._td.cleanup()

    def test_three_independent_profiles(self):
        reg = GamesRegistry()
        reg.games["ff7r_remake"] = GameRecord(
            id="ff7r_remake",
            name="REMAKE",
            adapter="ue4_paks_mods",
            mods_dir=str(self.base / "remake_mods"),
            stage_dir=str(self.base / "remake_stage"),
            data_mode="isolated",
            data_dir_name="ff7r_remake",
            destination_verified=True,
            path_status="installed",
        )
        (self.base / "remake_mods").mkdir()
        (self.base / "remake_stage").mkdir()
        (self.base / "rebirth_stage").mkdir()
        (self.base / "stellar_stage").mkdir()
        # Forzar perfiles s10 con stubs: monkey via ensure on empty ids
        reg.games["ff7_rebirth"] = GameRecord(
            id="ff7_rebirth",
            name="REBIRTH",
            adapter="ue5_iostore_mods",
            stage_dir=str(self.base / "rebirth_stage"),
            downloads_dir=str(self.base / "rebirth_dl"),
            data_mode="isolated",
            data_dir_name="ff7_rebirth",
            destination_verified=False,
            path_status="not_installed",
        )
        reg.games["stellar_blade"] = GameRecord(
            id="stellar_blade",
            name="STELLAR",
            adapter="ue5_iostore_mods",
            stage_dir=str(self.base / "stellar_stage"),
            downloads_dir=str(self.base / "stellar_dl"),
            data_mode="isolated",
            data_dir_name="stellar_blade",
            destination_verified=False,
            path_status="demo_only",
        )
        (self.base / "rebirth_dl").mkdir()
        (self.base / "stellar_dl").mkdir()
        save_registry(reg, self.reg_path)
        loaded = ensure_registry(self.reg_path, app_data=self.data)
        self.assertIn("ff7r_remake", loaded.games)
        self.assertIn("ff7_rebirth", loaded.games)
        self.assertIn("stellar_blade", loaded.games)
        p_r = game_paths_for(loaded.games["ff7r_remake"], app_data=self.data)
        p_b = game_paths_for(loaded.games["ff7_rebirth"], app_data=self.data)
        p_s = game_paths_for(loaded.games["stellar_blade"], app_data=self.data)
        self.assertNotEqual(p_r.data_dir, p_b.data_dir)
        self.assertNotEqual(p_b.data_dir, p_s.data_dir)

    def test_game_without_install_blocks_apply(self):
        mods = self.base / "mods"
        stage = self.base / "stage"
        mods.mkdir()
        stage.mkdir()
        m = _mod("M1", stage, {"a.pak": b"A", "a.utoc": b"U", "a.ucas": b"C"})
        ctx = ApplyContext(
            mods=mods,
            deploy=mods / "vortex.deployment.json",
            loadout_marker=mods / "_manual_loadout.json",
            manifest=self.data / "man.json",
            backups=self.data / "backups",
            stage=stage,
            data_dir=self.data,
        )
        settings = ConflictSettings(
            adapter_id="ue5_iostore_mods",
            install_mode="COPY",
            stage_root=stage,
            mods_root=mods,
            destination_verified=False,
        )
        plan = plan_apply([m], ctx, settings)
        with self.assertRaises(ApplyError) as cm:
            execute(plan, ctx, mods=[m])
        self.assertIn("no verificado", str(cm.exception).lower())

    def test_staging_without_destination_ok_to_register(self):
        rec = GameRecord(
            id="x",
            name="X",
            stage_dir=str(self.base / "st"),
            mods_dir="",
            destination_verified=False,
            adapter="ue5_iostore_mods",
        )
        (self.base / "st").mkdir()
        errs = validate_game_paths(rec)
        self.assertEqual(errs, [])

    def test_downloads_not_assumed_staging(self):
        rec = make_stellar_blade_record()
        self.assertTrue(rec.downloads_dir)
        self.assertNotEqual(rec.downloads_dir, rec.stage_dir)
        self.assertIn("downloads", rec.downloads_dir.replace("\\", "/"))

    def test_adapters_distinct_semantics(self):
        self.assertTrue(sem_eng("ue4_paks_mods"))
        self.assertFalse(sem_eng("ue5_iostore_mods"))
        self.assertFalse(sem_eng("generic_folder"))
        ad = get_adapter("ue5_iostore_mods")
        self.assertTrue(ad.iostore_sidecars)
        self.assertFalse(ad.semantic_slots)

    def test_iostore_classify_sidecars(self):
        stage = self.base / "stage"
        m = _mod(
            "Io",
            stage,
            {
                "Mod_P.pak": b"p",
                "Mod_P.utoc": b"t",
                "Mod_P.ucas": b"c",
                "README.txt": b"r",
            },
        )
        mc = classify_mod(m, "ue5_iostore_mods")
        self.assertIn("Mod_P.pak", mc.installable)
        self.assertIn("Mod_P.utoc", mc.installable)
        self.assertIn("Mod_P.ucas", mc.installable)
        self.assertTrue(any("README" in x.upper() for x in mc.documentation))

    def test_remake_semantics_not_on_rebirth(self):
        self.assertTrue(get_adapter("ue4_paks_mods").semantic_slots)
        self.assertFalse(get_adapter("ue5_iostore_mods").semantic_slots)
        rebirth = make_ff7_rebirth_record()
        self.assertEqual(rebirth.adapter, "ue5_iostore_mods")

    def test_ensure_s10_preserves_remake_id(self):
        reg = GamesRegistry(
            active_game_id="ff7r_remake",
            games={
                "ff7r_remake": GameRecord(
                    id="ff7r_remake",
                    name="KEEP",
                    adapter="ue4_paks_mods",
                    mods_dir=str(self.base / "m"),
                    stage_dir=str(self.base / "s"),
                    data_mode="legacy_root",
                    destination_verified=True,
                )
            },
        )
        (self.base / "m").mkdir()
        (self.base / "s").mkdir()
        ensure_s10_profiles(reg)
        self.assertEqual(reg.games["ff7r_remake"].name, "KEEP")
        self.assertIn("ff7_rebirth", reg.games)
        self.assertIn("stellar_blade", reg.games)

    def test_simulate_without_write_unverified(self):
        stage = self.base / "stage"
        sandbox = self.data / "_no_destination"
        sandbox.mkdir(parents=True)
        stage.mkdir()
        m = _mod("S", stage, {"x.pak": b"x"})
        ctx = ApplyContext(
            mods=sandbox,
            deploy=sandbox / "vortex.deployment.json",
            loadout_marker=sandbox / "_manual_loadout.json",
            manifest=self.data / "man.json",
            backups=self.data / "backups",
            stage=stage,
            data_dir=self.data,
        )
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            stage_root=stage,
            mods_root=sandbox,
            destination_verified=False,
        )
        plan = plan_apply([m], ctx, settings)
        self.assertIn("x.pak", plan.desired_meta)
        # no escritura en sandbox aún
        self.assertFalse((sandbox / "x.pak").exists())


if __name__ == "__main__":
    unittest.main()
