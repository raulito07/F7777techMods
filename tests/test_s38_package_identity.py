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

S38 — PAQUETE ≠ MOD ≠ ARCHIVO: entradas individuales en Biblioteca.
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

from app.core.apply import ApplyContext, plan_apply  # noqa: E402
from app.core.component_selection import VARIANTES_EXCLUYENTES, classify_components  # noqa: E402
from app.core.conflict_engine import ConflictSettings, collect_offers  # noqa: E402
from app.core.inventory import ModEntry, scan_staging  # noqa: E402
from app.core.library_status import filter_mods  # noqa: E402
from app.core.loadout_store import merge_loadout, save_loadout  # noqa: E402
from app.core.package_identity import (  # noqa: E402
    expand_independent_packages,
    is_component_id,
    migrate_package_loadout,
    package_folder_of,
    stable_component_id,
)


def _better_fixture(root: Path) -> ModEntry:
    stage = root / "BETTER-FFVII-REMAKE-NSFW-308381-2-1719165517"
    paks = [
        "zzCloudHyperHD_CGI_noeyes.pak",
        "SexierShivaFixed.pak",
        "tifa_black_sheer_stockings_p.pak",
    ]
    for n in paks:
        d = stage / "bundled" / f"Bundled - {Path(n).stem}"
        d.mkdir(parents=True, exist_ok=True)
        (d / n).write_bytes(b"PAK" + n.encode()[:12])
    (stage / "collection.json").write_text(
        json.dumps({"info": {"name": "BETTER"}, "mods": [{"name": "a"}, {"name": "b"}]}),
        encoding="utf-8",
    )
    return ModEntry(
        folder=stage.name,
        name="BETTER-FFVII-REMAKE-NSFW",
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=True,
        on_disk=False,
        stage_path=str(stage),
        usar=False,
    )


class PackageIdentityTests(unittest.TestCase):
    def test_better_splits_into_three_searchable_entries(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        pkg = _better_fixture(Path(td.name))
        expanded = expand_independent_packages([pkg])
        self.assertEqual(len(expanded), 3)
        self.assertTrue(all(is_component_id(m.folder) for m in expanded))
        self.assertTrue(all(m.package_folder == pkg.folder for m in expanded))
        # No cuarta entrada instalable del paquete
        self.assertFalse(any(m.folder == pkg.folder for m in expanded))
        # Buscables por personaje
        self.assertTrue(filter_mods(expanded, query="tifa"))
        self.assertTrue(filter_mods(expanded, query="cloud"))
        self.assertTrue(filter_mods(expanded, query="shiva"))
        names = {m.name.lower() for m in expanded}
        self.assertTrue(any("cloud" in n for n in names))
        self.assertTrue(any("tifa" in n for n in names))
        self.assertTrue(any("shiva" in n for n in names))

    def test_select_one_two_three_no_duplicates(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        pkg = _better_fixture(Path(td.name))
        mods = expand_independent_packages([pkg])
        cloud = next(m for m in mods if "cloud" in m.name.lower())
        tifa = next(m for m in mods if "tifa" in m.name.lower())
        shiva = next(m for m in mods if "shiva" in m.name.lower())
        cloud.usar = True
        by_key, _, _ = collect_offers(
            [cloud, tifa, shiva],
            ConflictSettings(adapter_id="ue4_paks_mods"),
        )
        names = sorted({o.dest_rel for offers in by_key.values() for o in offers})
        self.assertEqual(names, ["zzCloudHyperHD_CGI_noeyes.pak"])
        tifa.usar = True
        shiva.usar = True
        by_key, _, _ = collect_offers(
            mods, ConflictSettings(adapter_id="ue4_paks_mods")
        )
        names = {o.dest_rel for offers in by_key.values() for o in offers}
        self.assertEqual(len(names), 3)

    def test_exclusive_variants_not_split(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "fov"
        stage.mkdir()
        (stage / "Camera_FOV70.pak").write_bytes(b"a")
        (stage / "Camera_FOV90.pak").write_bytes(b"b")
        m = ModEntry(
            folder="fov",
            name="fov",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["Camera_FOV70.pak", "Camera_FOV90.pak"],
            multi=True,
            on_disk=False,
            stage_path=str(stage),
        )
        self.assertEqual(classify_components(m).mode, VARIANTES_EXCLUYENTES)
        expanded = expand_independent_packages([m])
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].folder, "fov")

    def test_iostore_not_split_as_independents(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "ios"
        stage.mkdir()
        for n in ("Pack.pak", "Pack.utoc", "Pack.ucas", "Other.pak", "Other.utoc", "Other.ucas"):
            (stage / n).write_bytes(b"x")
        m = ModEntry(
            folder="ios",
            name="ios",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["Pack.pak", "Other.pak"],
            multi=True,
            on_disk=False,
            stage_path=str(stage),
        )
        expanded = expand_independent_packages([m])
        self.assertEqual(len(expanded), 1)

    def test_multi_character_single_pak_one_entry(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "mix"
        stage.mkdir()
        (stage / "tifa_and_cloud_combo.pak").write_bytes(b"x")
        m = ModEntry(
            folder="mix",
            name="mix",
            characters=["TIFA", "CLOUD"],
            character_main="TIFA",
            paks=["tifa_and_cloud_combo.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(stage),
        )
        expanded = expand_independent_packages([m])
        self.assertEqual(len(expanded), 1)
        # Buscable por ambas etiquetas sin duplicar archivo
        self.assertEqual(len(filter_mods(expanded, query="tifa")), 1)
        self.assertEqual(len(filter_mods(expanded, query="cloud")), 1)

    def test_ambiguous_not_auto_split(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "amb"
        stage.mkdir()
        (stage / "AlphaThing.pak").write_bytes(b"a")
        (stage / "BetaThing.pak").write_bytes(b"b")
        m = ModEntry(
            folder="amb",
            name="amb",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["AlphaThing.pak", "BetaThing.pak"],
            multi=True,
            on_disk=False,
            stage_path=str(stage),
        )
        expanded = expand_independent_packages([m])
        self.assertEqual(len(expanded), 1)

    def test_migrate_s37_paks_elegidos(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        pkg = _better_fixture(Path(td.name))
        mods = expand_independent_packages([pkg])
        saved = {
            pkg.folder: {
                "usar": True,
                "paks_elegidos": ["zzCloudHyperHD_CGI_noeyes.pak", "SexierShivaFixed.pak"],
            }
        }
        migrate_package_loadout(mods, saved)
        active = [m for m in mods if m.usar]
        self.assertEqual(len(active), 2)
        dests = {m.pak_elegido for m in active}
        self.assertEqual(
            dests, {"zzCloudHyperHD_CGI_noeyes.pak", "SexierShivaFixed.pak"}
        )

    def test_persist_component_loadout(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        pkg = _better_fixture(Path(td.name))
        mods = expand_independent_packages([pkg])
        mods[0].usar = True
        path = Path(td.name) / "loadout.json"
        save_loadout(mods, path)
        mods2 = expand_independent_packages([_better_fixture(Path(td.name) / "b2")])
        # same package folder name for stable ids
        merge_loadout(mods2, path)
        self.assertTrue(any(m.usar for m in mods2 if m.folder == mods[0].folder))

    def test_conflict_across_packages_same_dest(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        s1 = base / "p1"
        s2 = base / "p2"
        mods_dir = base / "mods"
        mods_dir.mkdir()
        for s in (s1, s2):
            s.mkdir()
            (s / "Same.pak").write_bytes(b"A" if s == s1 else b"B")
        m1 = ModEntry(
            folder=stable_component_id("p1", "Same.pak"),
            name="Same A",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["Same.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(s1),
            usar=True,
            pak_elegido="Same.pak",
            package_folder="p1",
        )
        m2 = ModEntry(
            folder=stable_component_id("p2", "Same.pak"),
            name="Same B",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["Same.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(s2),
            usar=True,
            pak_elegido="Same.pak",
            package_folder="p2",
        )
        plan = plan_apply(
            [m1, m2],
            ApplyContext(mods=mods_dir, stage=base, data_dir=base / "data"),
            ConflictSettings(adapter_id="ue4_paks_mods"),
        )
        self.assertTrue(plan.errors or plan.file_unresolved or plan.conflicts)

    def test_stable_id_deterministic(self):
        a = stable_component_id("pkg", "tifa.pak")
        b = stable_component_id("pkg", "tifa.pak")
        self.assertEqual(a, b)
        self.assertEqual(package_folder_of(a), "pkg")

    def test_real_better_readonly_if_present(self):
        import os

        stage = Path(os.environ.get("APPDATA", "")) / "Vortex" / "finalfantasy7remake" / "mods"
        if not stage.is_dir():
            self.skipTest("staging real no disponible")
        rows = scan_staging(stage)
        better = next((m for m in rows if "BETTER-FFVII-REMAKE-NSFW" in m.folder), None)
        if better is None:
            self.skipTest("colección BETTER no instalada")
        expanded = expand_independent_packages([better])
        self.assertGreaterEqual(len(expanded), 3)
        blob = " ".join(m.name.lower() + " " + " ".join(m.paks).lower() for m in expanded)
        self.assertIn("cloud", blob)
        self.assertIn("tifa", blob)
        self.assertIn("shiva", blob)
        self.assertFalse(any(m.folder == better.folder for m in expanded))


if __name__ == "__main__":
    unittest.main()
