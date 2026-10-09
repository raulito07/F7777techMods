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

Regresión: manifiesto legacy_root y fusión sin pisar loadout/plan.
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

from app.core.apply import ApplyContext, load_manifest  # noqa: E402
from app.core.games import GameRecord, game_paths_for  # noqa: E402
from app.core.manifest_merge import merge_managed_manifest  # noqa: E402


class ManifestTraceabilityTests(unittest.TestCase):
    def test_legacy_root_manifest_path_matches_apply_context(self):
        rec = GameRecord(
            id="ff7r_remake",
            name="FF7R",
            mods_dir=str(Path("C:/games/ff7r/~mods")),
            stage_dir=str(Path("C:/staging")),
            adapter="ue4_paks_mods",
            data_mode="legacy_root",
            data_dir_name="ff7r_remake",
            destination_verified=True,
        )
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        app_data = Path(td.name) / "appdata"
        app_data.mkdir()
        paths = game_paths_for(rec, app_data=app_data)
        self.assertEqual(paths.data_dir, app_data)
        mf = app_data / "managed_manifest.json"
        mf.write_text(
            json.dumps(
                {
                    "version": 2,
                    "updated_at": "t",
                    "files": {"FOV70.pak": {"sha256": "abc", "mod_folder": "f"}},
                }
            ),
            encoding="utf-8",
        )
        ctx = paths.apply_context()
        self.assertEqual(ctx.manifest, mf)
        self.assertIn("FOV70.pak", load_manifest(ctx))

    def test_merge_adds_fov70_without_overwriting_existing(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        target = base / "managed_manifest.json"
        source = base / "s19.json"
        target.write_text(
            json.dumps(
                {
                    "version": 2,
                    "updated_at": "now",
                    "files": {
                        "Other.pak": {"sha256": "1", "mod_folder": "o"},
                    },
                }
            ),
            encoding="utf-8",
        )
        source.write_text(
            json.dumps(
                {
                    "version": 2,
                    "updated_at": "s19",
                    "files": {
                        "FOV70.pak": {"sha256": "dea0", "mod_folder": "FOV70-788"},
                        "Other.pak": {"sha256": "old", "mod_folder": "x"},
                    },
                }
            ),
            encoding="utf-8",
        )
        added, skipped = merge_managed_manifest(target, source, only_rel={"FOV70.pak"})
        self.assertEqual(added, 1)
        self.assertEqual(skipped, 0)
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["files"]["Other.pak"]["sha256"], "1")
        self.assertEqual(data["files"]["FOV70.pak"]["mod_folder"], "FOV70-788")


if __name__ == "__main__":
    unittest.main()
