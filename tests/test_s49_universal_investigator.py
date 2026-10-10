# -*- coding: utf-8 -*-
"""
F7777techMods — S49 — investigador universal (fixtures; sin Vortex/Steam reales).
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

from app.core.inventory import ModEntry, collect_payload, scan_staging  # noqa: E402
from app.core.library_catalog_model import tags_for_mod  # noqa: E402
from app.core.library_status import (  # noqa: E402
    FORMATO_SIN_PAK,
    INVEST_CONFIRMADA,
    INVEST_DESCONOCIDA,
    INVEST_EXTERNA,
    INVEST_NO_SOPORTADA,
    compute_mod_status,
)
from app.core.mod_investigator import (  # noqa: E402
    InstallCapability,
    investigate_mod,
    investigate_mods,
    is_f7777_unknown,
    summarize_by_game,
)


def _mod(folder: str, stage: Path, **kw) -> ModEntry:
    payload_files, payload_exts = collect_payload(stage)
    paks = sorted(p.name for p in stage.rglob("*.pak"))
    base = dict(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(stage),
        usar=False,
        payload_files=payload_files,
        payload_exts=payload_exts,
    )
    base.update(kw)
    return ModEntry(**base)


def _write(root: Path, rel: str, data: bytes = b"x") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class S49UniversalInvestigatorTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_inventory_includes_unknown_formats(self):
        stage = self.root / "stage"
        m1 = stage / "MediaMod"
        m2 = stage / "PakMod"
        _write(m1, "cut.emov", b"emov")
        _write(m2, "a.pak", b"pak")
        mods = scan_staging(stage)
        by = {m.folder: m for m in mods}
        self.assertIn("MediaMod", by)
        self.assertIn("PakMod", by)
        self.assertEqual(by["MediaMod"].paks, [])
        self.assertIn(".emov", by["MediaMod"].payload_exts)
        tags = tags_for_mod(by["MediaMod"])
        self.assertIn("CON_ARCHIVOS", tags)
        self.assertIn("FORMATO_NO_INSTALABLE", tags)

    def test_stable_identity_without_pak(self):
        stage = self.root / "s" / "Tool-99-1"
        _write(stage, "inject.dll")
        mods = scan_staging(stage.parent)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].folder, "Tool-99-1")

    def test_confirmed_pak_apply_allowed(self):
        stage = self.root / "pakmod"
        _write(stage, "x.pak")
        m = _mod("pakmod", stage)
        rep = investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.CONFIRMED)
        self.assertTrue(rep.apply_allowed)
        self.assertTrue(rep.f7777_installable)
        st = compute_mod_status(m, investigation=rep)
        self.assertTrue(st.has(INVEST_CONFIRMADA))

    def test_emov_not_apply_ue4(self):
        stage = self.root / "emovmod"
        _write(stage, "Movies/010.emov")
        m = _mod("emovmod", stage)
        rep = investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.UNSUPPORTED)
        self.assertFalse(rep.apply_allowed)
        self.assertTrue(is_f7777_unknown(rep))
        st = compute_mod_status(m, investigation=rep)
        self.assertTrue(st.has(INVEST_NO_SOPORTADA))
        self.assertTrue(st.has(FORMATO_SIN_PAK))

    def test_lua_external(self):
        stage = self.root / "luamod"
        _write(stage, "Scripts/main.lua", b"print(1)")
        m = _mod("luamod", stage)
        rep = investigate_mod(m, adapter_id="ue5_iostore_mods", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.EXTERNAL)
        self.assertFalse(rep.apply_allowed)
        st = compute_mod_status(m, investigation=rep)
        self.assertTrue(st.has(INVEST_EXTERNA))

    def test_ambiguous_ini_probable(self):
        stage = self.root / "inimod"
        _write(stage, "Engine.ini", b"[/Script]\n")
        m = _mod("inimod", stage)
        rep = investigate_mod(m, adapter_id="generic_folder", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.PROBABLE)
        self.assertFalse(rep.apply_allowed)

    def test_meta_only_unknown(self):
        stage = self.root / "metamod"
        _write(stage, "collection.json", b"{}")
        m = _mod("metamod", stage)
        rep = investigate_mod(m, adapter_id="ue5_iostore_mods", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.UNKNOWN)
        st = compute_mod_status(m, investigation=rep)
        self.assertTrue(st.has(INVEST_DESCONOCIDA))

    def test_no_game_installed(self):
        stage = self.root / "orphan"
        _write(stage, "a.pak")
        m = _mod("orphan", stage)
        rep = investigate_mod(
            m,
            adapter_id="ue4_paks_mods",
            game_root=self.root / "missing_game",
            load_vortex=False,
        )
        self.assertEqual(rep.capability, InstallCapability.CONFIRMED)
        self.assertTrue(rep.apply_allowed)

    def test_multi_component_inventory(self):
        stage = self.root / "multi"
        _write(stage, "a.pak")
        _write(stage, "b.pak")
        _write(stage, "readme.txt", b"hi")
        mods = scan_staging(stage.parent)
        self.assertEqual(len(mods), 1)
        self.assertTrue(mods[0].multi)
        self.assertGreaterEqual(len(mods[0].payload_files), 3)

    def test_sbil0_three_packages_distinct(self):
        stage = self.root / "stage"
        for part in ("Part1", "Part2", "Part3"):
            d = stage / f"140-SBIL0_{part}_Fixed-111-2-1"
            for i in range(2):
                _write(d, f"clip{i}.emov", b"e")
        mods = scan_staging(stage)
        folders = sorted(m.folder for m in mods)
        self.assertEqual(len(folders), 3)
        reps = investigate_mods(
            mods, adapter_id="ue4_paks_mods", game_id="ff7r_remake", load_vortex=False
        )
        for r in reps.values():
            self.assertEqual(r.capability, InstallCapability.UNSUPPORTED)
            self.assertFalse(r.apply_allowed)

    def test_external_tool_dll(self):
        stage = self.root / "hook"
        _write(stage, "FFVIIHook.dll")
        m = _mod("hook", stage)
        rep = investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        self.assertEqual(rep.capability, InstallCapability.EXTERNAL)

    def test_vortex_historical_not_deploy(self):
        roaming = self.root / "Vortex"
        backup_dir = roaming / "temp" / "state_backups_full"
        backup_dir.mkdir(parents=True)
        mod_id = "OnlyEnabled-1-1"
        stage = roaming / "g1" / "mods" / mod_id
        _write(stage, "weird.bin", b"z")
        obj = {
            "persistent": {
                "profiles": {
                    "p1": {
                        "gameId": "g1",
                        "name": "Main",
                        "lastActivated": 9,
                        "modState": {mod_id: {"enabled": True}},
                    }
                },
                "mods": {
                    "g1": {
                        mod_id: {
                            "id": mod_id,
                            "state": "installed",
                            "type": "",
                            "archiveId": "aid",
                            "attributes": {},
                        }
                    }
                },
            }
        }
        (backup_dir / "hourly.json").write_text(json.dumps(obj), encoding="utf-8")
        m = _mod(mod_id, stage)
        rep = investigate_mod(
            m,
            adapter_id="generic_folder",
            vortex_game_id="g1",
            vortex_roaming=roaming,
            load_vortex=True,
        )
        self.assertTrue(rep.vortex.enabled_historical)
        self.assertIsNone(rep.vortex.enabled_verified)
        self.assertFalse(rep.vortex.deployment_manifest_found)
        self.assertFalse(rep.apply_allowed)
        # enabled/installed no implica confirmado
        self.assertNotEqual(rep.capability, InstallCapability.CONFIRMED)

    def test_no_accidental_write(self):
        stage = self.root / "safe"
        target = _write(stage, "a.pak", b"ORIG")
        before = target.read_bytes()
        mtime = target.stat().st_mtime_ns
        m = _mod("safe", stage)
        investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(target.stat().st_mtime_ns, mtime)

    def test_summarize_by_game(self):
        a = self.root / "ga"
        b = self.root / "gb"
        _write(a, "a.pak")
        _write(b, "x.emov")
        ma = _mod("ga", a)
        mb = _mod("gb", b)
        ra = investigate_mod(
            ma, adapter_id="ue4_paks_mods", game_id="gameA", load_vortex=False
        )
        rb = investigate_mod(
            mb, adapter_id="ue4_paks_mods", game_id="gameB", load_vortex=False
        )
        summary = summarize_by_game({"ga": ra, "gb": rb})
        self.assertEqual(summary["gameA"]["total"], 1)
        self.assertEqual(summary["gameB"]["NO_SOPORTADO"], 1)

    def test_library_summary_text(self):
        stage = self.root / "sum"
        _write(stage, "a.pak")
        m = _mod("sum", stage)
        rep = investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        txt = rep.library_summary()
        self.assertIn("Investigación S49", txt)
        self.assertIn("INSTALACION_CONFIRMADA", txt)
        self.assertIn("Apply permitido", txt)

    def test_fictional_multi_game_batch(self):
        """Varios juegos ficticios / formatos distintos."""
        games = {
            "alpha": ("ue4_paks_mods", [("m1", "a.pak", b"1"), ("m2", "c.emov", b"2")]),
            "beta": ("ue5_iostore_mods", [("m3", "t.pak", b"3"), ("m4", "s.lua", b"4")]),
            "gamma": ("generic_folder", [("m5", "only.json", b"{}")]),
        }
        all_reps = {}
        for gid, (aid, items) in games.items():
            stage = self.root / gid / "mods"
            mods = []
            for folder, rel, data in items:
                d = stage / folder
                _write(d, rel, data)
                mods.append(_mod(folder, d))
            reps = investigate_mods(
                mods, adapter_id=aid, game_id=gid, load_vortex=False
            )
            all_reps.update(reps)
        self.assertEqual(len(all_reps), 5)
        self.assertEqual(all_reps["m1"].capability, InstallCapability.CONFIRMED)
        self.assertEqual(all_reps["m2"].capability, InstallCapability.UNSUPPORTED)
        self.assertEqual(all_reps["m4"].capability, InstallCapability.EXTERNAL)
        self.assertEqual(all_reps["m5"].capability, InstallCapability.UNKNOWN)
        for r in all_reps.values():
            if r.capability != InstallCapability.CONFIRMED:
                self.assertFalse(r.apply_allowed)


if __name__ == "__main__":
    unittest.main()
