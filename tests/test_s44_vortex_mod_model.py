# -*- coding: utf-8 -*-
"""
F7777techMods — S44 — modelo inteligente mods/Vortex (fixtures, sin datos reales).
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

from app.core.inventory import ModEntry  # noqa: E402
from app.core.library_status import (  # noqa: E402
    COMPAT_DESCONOCIDA,
    GESTIONADO_F7777,
    VORTEX_ENABLED_HISTORICO,
    compute_mod_status,
)
from app.core.package_identity import SEP, stable_component_id  # noqa: E402
from app.core.vortex_mod_context import (  # noqa: E402
    build_mod_intelligence_map,
    live_vortex_sync_available,
)
from app.core.vortex_sync import probe_vortex_enable_state  # noqa: E402


def _mod(folder: str, **kw) -> ModEntry:
    base = dict(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=["x.pak"],
        multi=False,
        on_disk=False,
        stage_path="",
        usar=False,
    )
    base.update(kw)
    return ModEntry(**base)


def _write_backup(roaming: Path, game_id: str, *, enabled: dict, mods_meta: dict | None = None):
    backup_dir = roaming / "temp" / "state_backups_full"
    backup_dir.mkdir(parents=True, exist_ok=True)
    mod_state = {k: {"enabled": v} for k, v in enabled.items()}
    mods_block = {}
    if mods_meta:
        for k, attrs in mods_meta.items():
            mods_block[k] = {
                "id": k,
                "archiveId": attrs.get("archiveId", ""),
                "attributes": attrs,
            }
    obj = {
        "persistent": {
            "profiles": {
                "p1": {
                    "gameId": game_id,
                    "name": "Main",
                    "lastActivated": 9,
                    "modState": mod_state,
                    "loadOrder": list(enabled.keys()),
                }
            },
            "mods": {game_id: mods_block},
        }
    }
    path = backup_dir / "hourly.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


class S44VortexModModelTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.roaming = Path(self._td.name) / "Vortex"
        self.roaming.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_live_sync_not_available(self):
        self.assertFalse(live_vortex_sync_available())

    def test_historical_enabled_not_verified(self):
        pkg = "Pack-1234-1-0"
        comp = stable_component_id(pkg, "Cloud.pak")
        _write_backup(
            self.roaming,
            "g1",
            enabled={pkg: True},
            mods_meta={
                pkg: {
                    "archiveId": "arch-1",
                    "modId": "99",
                    "fileId": "1",
                    "installedAsDependency": True,
                    "rules": [{"type": "after"}],
                }
            },
        )
        snap = probe_vortex_enable_state("g1", roaming=self.roaming)
        stage = Path(self._td.name) / "stage" / "comp"
        stage.mkdir(parents=True)
        mods = [_mod(comp, package_folder=pkg, stage_path=str(stage))]
        intel = build_mod_intelligence_map(
            mods, snap=snap, game_id="g1", adapter_id="ue4_paks_mods"
        )[comp]
        self.assertTrue(intel.vortex_enabled_historical)
        self.assertIsNone(intel.vortex_enabled_verified)
        self.assertEqual(intel.vortex_staging_key, pkg)
        self.assertTrue(intel.aux.collection_dependency)
        self.assertEqual(intel.aux.load_order_index, 0)

        st = compute_mod_status(mods[0], intel=intel)
        self.assertIn(VORTEX_ENABLED_HISTORICO, st.flags)
        self.assertIn(COMPAT_DESCONOCIDA, st.flags)

    def test_managed_f7777_flag(self):
        from app.core.apply import ApplyContext

        sandbox = Path(self._td.name) / "game"
        mods_dir = sandbox / "mods"
        mods_dir.mkdir(parents=True)
        manifest = sandbox / "managed_manifest.json"
        folder = "ModA"
        manifest.write_text(
            json.dumps(
                {
                    "version": 2,
                    "files": {
                        "foo.pak": {
                            "mod_folder": folder,
                            "source": "x",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        ctx = ApplyContext(
            mods=mods_dir,
            deploy=mods_dir / "vortex.deployment.json",
            manifest=manifest,
            backups=sandbox / "bk",
            stage=sandbox / "st",
        )
        mods = [_mod(folder, usar=True, on_disk=True, stage_path=str(sandbox / "st" / folder))]
        (sandbox / "st" / folder).mkdir(parents=True)
        intel = build_mod_intelligence_map(mods, game_id="g1", ctx=ctx)[folder]
        self.assertTrue(intel.managed_f7777)
        st = compute_mod_status(mods[0], intel=intel)
        self.assertIn(GESTIONADO_F7777, st.flags)

    def test_components_stay_separate_entries(self):
        pkg = "Bundle-1"
        c1 = stable_component_id(pkg, "a.pak")
        c2 = stable_component_id(pkg, "b.pak")
        mods = [
            _mod(c1, package_folder=pkg, paks=["a.pak"]),
            _mod(c2, package_folder=pkg, paks=["b.pak"]),
        ]
        intel = build_mod_intelligence_map(mods, game_id="g1")
        self.assertEqual(len(intel), 2)
        self.assertNotEqual(c1, c2)


if __name__ == "__main__":
    unittest.main()
