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

from app.core.apply import ApplyContext  # noqa: E402
from app.core.installed_state import enrich_installed_from_manifest, plan_flags_for_dest_file  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.library_status import ACTIVO_EN_PLAN, INSTALADO_REAL, compute_mod_status  # noqa: E402
from app.core.provenance import scan_destination  # noqa: E402


class InstalledPlanStateTests(unittest.TestCase):
    def test_fov70_physical_plan_off_still_installed_real(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        mods_dir = base / "~mods"
        data = base / "data"
        mods_dir.mkdir()
        data.mkdir()
        (mods_dir / "FOV70.pak").write_bytes(b"x" * 2934)
        (data / "managed_manifest.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "files": {
                        "FOV70.pak": {
                            "mod_folder": "FOV70-788",
                            "sha256": "abc",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        ctx = ApplyContext(mods=mods_dir, manifest=data / "managed_manifest.json", data_dir=data)
        m = ModEntry(
            folder="FOV70-788",
            name="FOV70",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["FOV70.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(base / "stage" / "FOV70-788"),
            usar=False,
        )
        enrich_installed_from_manifest([m], ctx)
        st = compute_mod_status(m)
        self.assertIn(INSTALADO_REAL, st.flags)
        self.assertNotIn(ACTIVO_EN_PLAN, st.flags)
        inv = scan_destination(mods_dir, manifest={"FOV70.pak": {"mod_folder": "FOV70-788"}}, deploy_path=mods_dir / "x.json")
        self.assertEqual(len(inv.files), 1)
        _a, pend, note = plan_flags_for_dest_file("FOV70.pak", {"mod_folder": "FOV70-788"}, [m])
        self.assertTrue(pend)
        self.assertIn("plan NO", note)

    def test_plan_only_mod_not_in_physical_inventory(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        mods_dir = base / "~mods"
        mods_dir.mkdir()
        m = ModEntry(
            folder="Learn",
            name="Learn",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["LearnEnemySkill.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(base / "stage"),
            usar=True,
        )
        ctx = ApplyContext(mods=mods_dir, manifest=base / "managed_manifest.json", data_dir=base)
        enrich_installed_from_manifest([m], ctx)
        inv = scan_destination(mods_dir, manifest={}, deploy_path=mods_dir / "x.json")
        self.assertEqual(inv.files, [])
        st = compute_mod_status(m)
        self.assertIn(ACTIVO_EN_PLAN, st.flags)
        self.assertNotIn(INSTALADO_REAL, st.flags)


if __name__ == "__main__":
    unittest.main()
