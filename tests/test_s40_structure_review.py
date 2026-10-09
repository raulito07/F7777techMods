# -*- coding: utf-8 -*-
"""
F7777techMods — S40 revisión de estructura utilizable.
Versión: 0.1.0 — Four Seven Tech / Raúl Ruano Gil — GPL-3.0-or-later
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.inventory import ModEntry  # noqa: E402
from app.core.mod_structure import (  # noqa: E402
    FORMATO_NO_PAK,
    analyze_mod_structure,
    structure_blocks_apply,
)
from app.core.structure_resolution import (  # noqa: E402
    ACK_UNSUPPORTED,
    StructureResolution,
    effective_blocks_prepare,
    load_structure_resolutions,
    save_structure_resolutions,
    structure_procedure,
    structure_row_state,
)


def _emov_mod(folder: str, root: Path) -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=[],
        multi=False,
        on_disk=False,
        stage_path=str(root),
        usar=True,
    )


class S40StructureReviewTests(unittest.TestCase):
    def test_emov_classified_formato_no_pak(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "010-MAKO1"
        root.mkdir(parents=True)
        nested = root / "010-MAKO1" / "MV_MAKO1_0220"
        nested.mkdir(parents=True)
        (nested / "MV_MAKO1_0220_US.emov").write_bytes(b"x")
        m = _emov_mod("010-MAKO1_pkg", root)
        r = analyze_mod_structure(m, "ue4_paks_mods")
        self.assertEqual(r.classification, FORMATO_NO_PAK)
        self.assertFalse(r.blocks_prepare)
        self.assertIn(".emov", r.explanation.lower())
        self.assertFalse(effective_blocks_prepare(r, None))
        tag, lab = structure_row_state(r, None, usar=True)
        self.assertEqual(tag, "pending")
        self.assertIn("PAK", lab)

    def test_town8_two_emov_same_mod(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "020-TOWN8"
        root.mkdir(parents=True)
        for name in ("MV_TOWN8_0230_US.emov", "MV_TOWN8_0300.emov"):
            p = root / "020-TOWN8" / "MV_TOWN8_0230"
            p.mkdir(parents=True, exist_ok=True)
            (p / name).write_bytes(b"x")
        m = _emov_mod("020-TOWN8", root)
        r = analyze_mod_structure(m, "ue4_paks_mods")
        self.assertEqual(r.classification, FORMATO_NO_PAK)
        proc = structure_procedure(r)
        self.assertIn("adaptador", proc.lower())

    def test_ack_unsupported_clears_block_and_row(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "pkg"
        root.mkdir()
        (root / "a.emov").write_bytes(b"1")
        m = _emov_mod("pkg", root)
        r = analyze_mod_structure(m, "ue4_paks_mods")
        res = StructureResolution(
            folder="pkg",
            fingerprint=r.fingerprint,
            action=ACK_UNSUPPORTED,
            note="ok",
        )
        self.assertFalse(effective_blocks_prepare(r, res))
        tag, lab = structure_row_state(r, res, usar=True)
        self.assertEqual(tag, "unchanged")
        self.assertIn("reconocido", lab.lower())

    def test_structure_blocks_apply_ignores_emov_active(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "a"
        root.mkdir()
        (root / "v.emov").write_bytes(b"1")
        m = _emov_mod("a", root)
        r = analyze_mod_structure(m, "ue4_paks_mods")
        reports = {m.folder: r}
        self.assertFalse(structure_blocks_apply(reports, [m], {}))

    def test_resolution_persist_roundtrip(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "structure_resolutions.json"
        data = {
            "x": StructureResolution(
                folder="x", fingerprint="fp1", action=ACK_UNSUPPORTED
            ).to_dict()
        }
        save_structure_resolutions(path, {"x": StructureResolution.from_dict(data["x"])})
        loaded = load_structure_resolutions(path)
        self.assertIn("x", loaded)
        self.assertEqual(loaded["x"].action, ACK_UNSUPPORTED)

    def test_real_mako_readonly_if_present(self):
        stage = Path(os.environ.get("APPDATA", "")) / "Vortex" / "finalfantasy7remake" / "mods"
        if not stage.is_dir():
            self.skipTest("staging no disponible")
        folder = next(
            (p for p in stage.iterdir() if p.is_dir() and "010-MAKO1" in p.name),
            None,
        )
        if folder is None:
            self.skipTest("010-MAKO1 no instalado")
        m = ModEntry(
            folder=folder.name,
            name=folder.name,
            characters=["OTROS"],
            character_main="OTROS",
            paks=[],
            multi=False,
            on_disk=False,
            stage_path=str(folder),
            usar=True,
        )
        r = analyze_mod_structure(m, "ue4_paks_mods")
        self.assertEqual(r.classification, FORMATO_NO_PAK)
        self.assertFalse(structure_blocks_apply({m.folder: r}, [m], {}))


if __name__ == "__main__":
    unittest.main()
