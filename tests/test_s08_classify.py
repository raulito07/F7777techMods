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

S08 — clasificación, filtros ue4_paks_mods, subconjunto seguro (temporales).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import ApplyContext, plan_apply  # noqa: E402
from app.core.conflict_engine import ConflictSettings, analyze_file_conflicts  # noqa: E402
from app.core.content_classify import ContentKind, classify_mod  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.safe_loadout import propose_safe_subset  # noqa: E402


def _mod(folder: str, stage: Path, paks: list[str], *, usar=True, multi=False, chosen="") -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=multi or len(paks) > 1,
        on_disk=False,
        stage_path=str(stage),
        usar=usar,
        pak_elegido=chosen,
    )


def _write(d: Path, rel: str, data: bytes = b"x") -> Path:
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class S08ClassifyTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.mods = self.base / "mods"
        self.mods.mkdir(parents=True)
        self.stage.mkdir(parents=True)

    def tearDown(self):
        self._td.cleanup()

    def test_readme_excluded_ue4(self):
        d = self.stage / "ModA"
        _write(d, "Cool.pak", b"pakdata")
        _write(d, "README.txt", b"docs")
        m = _mod("ModA", d, ["Cool.pak"], chosen="Cool.pak")
        mc = classify_mod(m, "ue4_paks_mods")
        self.assertIn("Cool.pak", mc.installable)
        self.assertTrue(any("README" in x.upper() for x in mc.documentation))
        settings = ConflictSettings(adapter_id="ue4_paks_mods")
        analysis = analyze_file_conflicts([m], settings)
        self.assertIn("Cool.pak", analysis.desired_offers)
        self.assertFalse(any("readme" in k.lower() for k in analysis.desired_offers))

    def test_valid_pak_included(self):
        d = self.stage / "ModB"
        _write(d, "Only.pak", b"abc")
        m = _mod("ModB", d, ["Only.pak"], chosen="Only.pak")
        settings = ConflictSettings(adapter_id="ue4_paks_mods")
        analysis = analyze_file_conflicts([m], settings)
        self.assertEqual(set(analysis.desired_offers), {"Only.pak"})

    def test_mod_without_pak_classified(self):
        d = self.stage / "NoPak"
        _write(d, "README.md", b"x")
        _write(d, "d3dx.ini", b"reshade")
        m = _mod("NoPak", d, [])
        mc = classify_mod(m, "ue4_paks_mods")
        self.assertFalse(mc.has_installable)
        self.assertTrue(mc.documentation or mc.special)
        self.assertIn(mc.summary_kind(), ("DESTINO_ESPECIAL", "SOLO_DOCS", "DESCONOCIDO"))

    def test_variant_blocks_without_choice(self):
        d = self.stage / "Multi"
        _write(d, "A.pak", b"1")
        _write(d, "B.pak", b"2")
        m = _mod("Multi", d, ["A.pak", "B.pak"], multi=True, chosen="")
        settings = ConflictSettings(adapter_id="ue4_paks_mods")
        analysis = analyze_file_conflicts([m], settings)
        self.assertTrue(analysis.variant_issues)
        self.assertEqual(analysis.desired_offers, {})
        mc = classify_mod(m, "ue4_paks_mods")
        self.assertTrue(mc.variant_pending)

    def test_special_dest_identified(self):
        d = self.stage / "Hook"
        _write(d, "FFVIIHook.dll", b"dll")
        _write(d, "Real.pak", b"pak")
        m = _mod("Hook", d, ["Real.pak"], chosen="Real.pak")
        mc = classify_mod(m, "ue4_paks_mods")
        self.assertTrue(mc.special)
        self.assertTrue(mc.has_installable)

    def test_generic_folder_no_ff7r_pak_only_rule(self):
        d = self.stage / "Gen"
        _write(d, "subdir/data.bin", b"bin")
        _write(d, "README.txt", b"doc")
        m = _mod("Gen", d, [])
        mc = classify_mod(m, "generic_folder")
        self.assertIn("subdir/data.bin", mc.installable)
        # generic no aplica exclusión FF7R: README también instalable
        self.assertTrue(any("README" in x.upper() for x in mc.installable))
        settings = ConflictSettings(adapter_id="generic_folder")
        analysis = analyze_file_conflicts([m], settings)
        self.assertIn("subdir/data.bin", analysis.desired_offers)
        self.assertTrue(any("readme" in k.lower() for k in analysis.desired_offers))

    def test_classify_does_not_delete_files(self):
        d = self.stage / "Keep"
        p = _write(d, "X.pak", b"keep")
        r = _write(d, "README.txt", b"keep")
        m = _mod("Keep", d, ["X.pak"], chosen="X.pak")
        classify_mod(m, "ue4_paks_mods")
        analyze_file_conflicts([m], ConflictSettings(adapter_id="ue4_paks_mods"))
        self.assertTrue(p.is_file())
        self.assertTrue(r.is_file())
        self.assertEqual(p.read_bytes(), b"keep")

    def test_safe_subset_simulates(self):
        d1 = self.stage / "S1"
        d2 = self.stage / "S2"
        _write(d1, "One.pak", b"1")
        _write(d1, "README.txt", b"d")
        _write(d2, "Two.pak", b"2")
        m1 = _mod("S1", d1, ["One.pak"], chosen="One.pak")
        m2 = _mod("S2", d2, ["Two.pak"], chosen="Two.pak")
        # Multi pendiente debe excluirse
        d3 = self.stage / "Bad"
        _write(d3, "A.pak", b"a")
        _write(d3, "B.pak", b"b")
        m3 = _mod("Bad", d3, ["A.pak", "B.pak"], multi=True, chosen="")
        settings = ConflictSettings(adapter_id="ue4_paks_mods", mods_root=self.mods)
        ctx = ApplyContext(mods=self.mods, stage=self.stage)
        prop = propose_safe_subset([m1, m2, m3], settings, ctx)
        self.assertIn("S1", prop.candidate_folders)
        self.assertIn("S2", prop.candidate_folders)
        self.assertNotIn("Bad", prop.candidate_folders)
        dests = {f["dest_rel"] for f in prop.files_to_copy}
        self.assertEqual(dests, {"One.pak", "Two.pak"})
        self.assertTrue(prop.ok_for_controlled_test)
        # No mutó usar de originales
        self.assertTrue(m3.usar)
        self.assertEqual(m3.pak_elegido, "")

    def test_readme_collision_no_longer_blocks_ue4(self):
        d1 = self.stage / "R1"
        d2 = self.stage / "R2"
        _write(d1, "A.pak", b"a")
        _write(d1, "README.txt", b"same")
        _write(d2, "B.pak", b"b")
        _write(d2, "README.txt", b"same")
        m1 = _mod("R1", d1, ["A.pak"], chosen="A.pak")
        m2 = _mod("R2", d2, ["B.pak"], chosen="B.pak")
        settings = ConflictSettings(adapter_id="ue4_paks_mods")
        analysis = analyze_file_conflicts([m1, m2], settings)
        self.assertEqual(set(analysis.desired_offers), {"A.pak", "B.pak"})
        unresolved_docs = [
            fc
            for fc in analysis.file_conflicts
            if "readme" in fc.dest_rel.lower() and not fc.resolved
        ]
        self.assertEqual(unresolved_docs, [])


if __name__ == "__main__":
    unittest.main()
