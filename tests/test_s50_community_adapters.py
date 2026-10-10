# -*- coding: utf-8 -*-
"""
F7777techMods — S50 — arquitectura abierta / adaptadores comunitarios.
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

from app.core.adapters import ADAPTERS, get_adapter  # noqa: E402
from app.core.community_adapter_api import (  # noqa: E402
    COMMUNITY_ADAPTER_API_VERSION,
    RecognitionLayer,
)
from app.core.community_adapter_loader import (  # noqa: E402
    load_community_adapter_file,
    load_community_adapters_dir,
)
from app.core.community_adapter_registry import (  # noqa: E402
    build_community_registry,
    detect_conflicts,
    describe_support_gap,
)
from app.core.community_adapter_security import (  # noqa: E402
    community_cannot_bypass_apply_guards,
    path_is_unsafe,
    sanitize_community_document,
)
from app.core.inventory import ModEntry, scan_staging  # noqa: E402
from app.core.mod_investigator import InstallCapability, investigate_mod  # noqa: E402
from app.core.player_support_messages import (  # noqa: E402
    player_facing_investigation,
    player_facing_unknown_game,
)


def _base(**kw):
    doc = {
        "api_version": "1.0",
        "adapter_id": "test_game_adapter",
        "display_name": "Test Game",
        "game_ids": ["test_game"],
        "permissions": ["declare_formats", "declare_destinations"],
        "formats": [
            {
                "id": "tg_pak",
                "extensions": [".tgpak"],
                "installer_id": "",
                "label": "Test pack",
            }
        ],
        "destinations": [
            {
                "id": "mods",
                "relative_path": "Mods",
                "format_ids": ["tg_pak"],
                "verified": False,
                "evidence": "sin_pruebas",
            }
        ],
        "auto_install_allowed": False,
    }
    doc.update(kw)
    return doc


class S50CommunityAdapterTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _write(self, name: str, doc: dict) -> Path:
        p = self.root / name
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def test_api_version_constant(self):
        self.assertEqual(COMMUNITY_ADAPTER_API_VERSION, "1.0")

    def test_official_adapters_unchanged(self):
        self.assertIn("ue4_paks_mods", ADAPTERS)
        self.assertIn("ue5_iostore_mods", ADAPTERS)
        self.assertIn("generic_folder", ADAPTERS)
        ad = get_adapter("ue4_paks_mods")
        self.assertTrue(ad.pak_centric)
        self.assertEqual(ad.suggest_mods_subdir, "End/Content/Paks/~mods")

    def test_valid_community_adapter(self):
        p = self._write("ok.json", _base())
        lr = load_community_adapter_file(p)
        self.assertTrue(lr.ok, lr.errors)
        self.assertFalse(lr.spec.auto_install_allowed)
        self.assertEqual(lr.spec.formats[0].extensions, (".tgpak",))

    def test_invalid_adapter_bad_id(self):
        p = self._write("bad.json", _base(adapter_id="BAD ID"))
        lr = load_community_adapter_file(p)
        self.assertFalse(lr.ok)

    def test_invalid_api_version(self):
        p = self._write("ver.json", _base(api_version="9.9"))
        lr = load_community_adapter_file(p)
        self.assertFalse(lr.ok)

    def test_forbidden_keys_rejected(self):
        doc = _base(force_apply=True, bypass_backup=True)
        p = self._write("evil.json", doc)
        lr = load_community_adapter_file(p)
        self.assertFalse(lr.ok)
        self.assertTrue(any("prohibidas" in e.lower() or "prohibido" in e.lower() or "Claves" in e for e in lr.errors))

    def test_code_block_rejected(self):
        doc = _base(code={"entrypoint": "evil.py"})
        p = self._write("code.json", doc)
        lr = load_community_adapter_file(p)
        self.assertFalse(lr.ok)

    def test_unsafe_path_rejected(self):
        bad, why = path_is_unsafe("../Windows")
        self.assertTrue(bad)
        doc = _base(
            destinations=[
                {
                    "id": "x",
                    "relative_path": "C:/Games/Hack",
                    "verified": False,
                    "evidence": "sin_pruebas",
                }
            ]
        )
        p = self._write("path.json", doc)
        lr = load_community_adapter_file(p)
        self.assertFalse(lr.ok)

    def test_auto_install_forced_false(self):
        doc = _base()
        doc["auto_install_allowed"] = True
        sec = sanitize_community_document(doc)
        self.assertFalse(sec.auto_install_allowed)
        self.assertFalse(doc["auto_install_allowed"])

    def test_format_without_installer_warning(self):
        p = self._write("fmt.json", _base())
        lr = load_community_adapter_file(p)
        self.assertTrue(lr.ok)
        self.assertTrue(any("sin installer" in w.lower() for w in lr.warnings))

    def test_compatibility_untested_warning(self):
        doc = _base(
            compatibility={
                "summary": "creo que funciona",
                "evidence": "sin_pruebas",
                "test_refs": [],
            }
        )
        p = self._write("compat.json", doc)
        lr = load_community_adapter_file(p)
        self.assertTrue(lr.ok)
        self.assertTrue(any("sin pruebas" in w.lower() for w in lr.warnings))

    def test_adapter_conflict_same_game_format_dest(self):
        a = _base(adapter_id="alpha_ad", game_ids=["shared_game"])
        b = _base(
            adapter_id="beta_ad",
            game_ids=["shared_game"],
            destinations=[
                {
                    "id": "other",
                    "relative_path": "Other/Mods",
                    "format_ids": ["tg_pak"],
                    "verified": False,
                    "evidence": "sin_pruebas",
                }
            ],
        )
        pa = self._write("a.json", a)
        pb = self._write("b.json", b)
        sa = load_community_adapter_file(pa).spec
        sb = load_community_adapter_file(pb).spec
        conflicts = detect_conflicts([sa, sb])
        self.assertTrue(any(c.kind == "format_destination_mismatch" for c in conflicts))

    def test_conflict_with_official_id(self):
        doc = _base(adapter_id="ue4_paks_mods")
        p = self._write("off.json", doc)
        # load ok structurally but registry blocks
        lr = load_community_adapter_file(p)
        self.assertTrue(lr.ok)
        reg = build_community_registry(self.root)
        self.assertNotIn("ue4_paks_mods", reg.specs)
        self.assertTrue(reg.load_errors or reg.warnings)

    def test_examples_load(self):
        examples = ROOT / "community_adapters" / "examples"
        results = load_community_adapters_dir(examples)
        self.assertGreaterEqual(len(results), 3)
        self.assertTrue(all(r.ok for r in results), [r.errors for r in results if not r.ok])
        reg = build_community_registry(ROOT / "community_adapters")
        self.assertIn("aurora_legends_datapack", reg.specs)
        self.assertFalse(any(s.auto_install_allowed for s in reg.specs.values()))

    def test_unknown_game_message(self):
        txt = player_facing_unknown_game(game_name="Nuevo Juego", game_id="nuevo_juego")
        self.assertIn("poco conocido", txt.lower())
        self.assertIn("GAME_ADAPTER_GUIDE", txt)

    def test_unknown_mod_stays_in_inventory(self):
        stage = self.root / "stage" / "WeirdMod"
        stage.mkdir(parents=True)
        (stage / "mystery.xyz").write_bytes(b"x")
        mods = scan_staging(stage.parent)
        self.assertEqual(len(mods), 1)
        self.assertIn(".xyz", mods[0].payload_exts)
        rep = investigate_mod(mods[0], adapter_id="generic_folder", load_vortex=False)
        self.assertNotEqual(rep.capability, InstallCapability.CONFIRMED)
        self.assertFalse(rep.apply_allowed)
        player = player_facing_investigation(rep)
        self.assertNotIn("{", player)  # sin JSON al jugador
        self.assertIn("Biblioteca", player)

    def test_unknown_format_recognition_layers(self):
        p = self._write("layers.json", _base())
        spec = load_community_adapter_file(p).spec
        snap = spec.recognition_snapshot(formats_present=[".tgpak"])
        self.assertTrue(snap[RecognitionLayer.GAME_RECOGNIZED])
        self.assertTrue(snap[RecognitionLayer.FORMAT_RECOGNIZED])
        self.assertFalse(snap[RecognitionLayer.AUTO_INSTALL_COMPATIBLE])

    def test_game_not_installed_gap(self):
        gap = describe_support_gap(
            game_id="missing_game",
            official_adapter_id="generic_folder",
            game_installed=False,
            formats_present=[".dat"],
        )
        self.assertFalse(gap["game_installed"])
        self.assertIn("contribution_hint", gap)
        self.assertFalse(gap["recognition"][RecognitionLayer.AUTO_INSTALL_COMPATIBLE.value])

    def test_guards_always_on(self):
        g = community_cannot_bypass_apply_guards()
        self.assertTrue(g["backup_required"])
        self.assertTrue(g["rollback"])
        self.assertFalse(g["community_auto_install"])

    def test_player_message_no_technical_json(self):
        stage = self.root / "m"
        stage.mkdir()
        (stage / "a.pak").write_bytes(b"p")
        m = ModEntry(
            folder="m",
            name="m",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["a.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(stage),
            payload_files=["a.pak"],
            payload_exts=[".pak"],
        )
        rep = investigate_mod(m, adapter_id="ue4_paks_mods", load_vortex=False)
        txt = player_facing_investigation(rep)
        self.assertIn("segura", txt.lower())
        self.assertNotIn("INSTALACION_CONFIRMADA", txt)


if __name__ == "__main__":
    unittest.main()
