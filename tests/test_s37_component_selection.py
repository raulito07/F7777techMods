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

S37 — independientes vs variantes excluyentes vs grupos obligatorios.
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
from app.core.component_selection import (  # noqa: E402
    GRUPOS_OBLIGATORIOS,
    INDEPENDIENTES,
    REVISION_MANUAL,
    VARIANTES_EXCLUYENTES,
    classify_components,
    selected_paks,
    set_selected_paks,
)
from app.core.conflict_engine import ConflictSettings, collect_offers  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.loadout_store import merge_loadout, save_loadout  # noqa: E402


def _mod(folder: str, stage: Path, paks: list[str], **kw) -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(stage),
        usar=kw.get("usar", True),
        pak_elegido=kw.get("pak_elegido", ""),
        paks_elegidos=list(kw.get("paks_elegidos") or []),
    )


def _write_paks(stage: Path, names: list[str], *, bundled: bool = False) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    for n in names:
        if bundled:
            d = stage / "bundled" / f"Bundled - {Path(n).stem}"
            d.mkdir(parents=True, exist_ok=True)
            (d / n).write_bytes(b"PAK" + n.encode()[:20])
        else:
            (stage / n).write_bytes(b"PAK" + n.encode()[:20])


class ComponentSelectionTests(unittest.TestCase):
    def test_better_collection_is_independent(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "BETTER-FFVII-REMAKE-NSFW"
        paks = [
            "zzCloudHyperHD_CGI_noeyes.pak",
            "SexierShivaFixed.pak",
            "tifa_black_sheer_stockings_p.pak",
        ]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text(
            json.dumps({"info": {"name": "BETTER"}, "mods": [{"name": "a"}, {"name": "b"}]}),
            encoding="utf-8",
        )
        m = _mod(stage.name, stage, paks)
        rep = classify_components(m)
        self.assertEqual(rep.mode, INDEPENDIENTES)
        self.assertFalse(rep.mode == VARIANTES_EXCLUYENTES)

    def test_cloud_only_plan(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "col"
        mods_dir = Path(td.name) / "mods"
        mods_dir.mkdir()
        paks = [
            "zzCloudHyperHD_CGI_noeyes.pak",
            "SexierShivaFixed.pak",
            "tifa_black_sheer_stockings_p.pak",
        ]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text("{}", encoding="utf-8")
        m = _mod(stage.name, stage, paks, usar=True)
        set_selected_paks(m, ["zzCloudHyperHD_CGI_noeyes.pak"])
        by_key, variants, errors = collect_offers(
            [m], ConflictSettings(adapter_id="ue4_paks_mods", stage_root=stage)
        )
        names = {o.dest_rel for offers in by_key.values() for o in offers}
        self.assertEqual(names, {"zzCloudHyperHD_CGI_noeyes.pak"})
        self.assertFalse(variants)
        self.assertNotIn("tifa_black_sheer_stockings_p.pak", names)
        self.assertNotIn("SexierShivaFixed.pak", names)

    def test_all_three_independent(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "col"
        paks = [
            "zzCloudHyperHD_CGI_noeyes.pak",
            "SexierShivaFixed.pak",
            "tifa_black_sheer_stockings_p.pak",
        ]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text("{}", encoding="utf-8")
        m = _mod(stage.name, stage, paks, usar=True)
        set_selected_paks(m, paks)
        by_key, _, _ = collect_offers(
            [m], ConflictSettings(adapter_id="ue4_paks_mods", stage_root=stage)
        )
        names = {o.dest_rel for offers in by_key.values() for o in offers}
        self.assertEqual(names, set(paks))

    def test_tifa_only_and_shiva_only(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "col"
        paks = [
            "zzCloudHyperHD_CGI_noeyes.pak",
            "SexierShivaFixed.pak",
            "tifa_black_sheer_stockings_p.pak",
        ]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text("{}", encoding="utf-8")
        for only in ("tifa_black_sheer_stockings_p.pak", "SexierShivaFixed.pak"):
            m = _mod(stage.name, stage, paks, usar=True)
            set_selected_paks(m, [only])
            by_key, _, _ = collect_offers(
                [m], ConflictSettings(adapter_id="ue4_paks_mods", stage_root=stage)
            )
            names = {o.dest_rel for offers in by_key.values() for o in offers}
            self.assertEqual(names, {only})

    def test_exclusive_fov_variants(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "fov"
        paks = ["Camera_FOV70.pak", "Camera_FOV90.pak"]
        _write_paks(stage, paks)
        m = _mod(stage.name, stage, paks, usar=True)
        rep = classify_components(m)
        self.assertEqual(rep.mode, VARIANTES_EXCLUYENTES)
        set_selected_paks(m, ["Camera_FOV70.pak"], exclusive=True)
        by_key, _, _ = collect_offers(
            [m], ConflictSettings(adapter_id="ue4_paks_mods", stage_root=stage)
        )
        names = {o.dest_rel for offers in by_key.values() for o in offers}
        self.assertEqual(names, {"Camera_FOV70.pak"})

    def test_iostore_groups_mode(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "ios"
        stage.mkdir()
        (stage / "Pack.pak").write_bytes(b"p")
        (stage / "Pack.utoc").write_bytes(b"t")
        (stage / "Pack.ucas").write_bytes(b"c")
        m = _mod(stage.name, stage, ["Pack.pak"], usar=True)
        # solo 1 pak pero sidecars → grupos
        rep = classify_components(m)
        # with 1 pak classify returns INDEPENDIENTES; ensure multi-pak + sidecars
        (stage / "Other.pak").write_bytes(b"o")
        (stage / "Other.utoc").write_bytes(b"t")
        (stage / "Other.ucas").write_bytes(b"c")
        m.paks = ["Pack.pak", "Other.pak"]
        m.multi = True
        rep = classify_components(m)
        self.assertEqual(rep.mode, GRUPOS_OBLIGATORIOS)

    def test_cancel_leaves_pending(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "col"
        paks = ["A_cloud.pak", "B_tifa.pak"]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text("{}", encoding="utf-8")
        m = _mod(stage.name, stage, paks, usar=True)
        self.assertEqual(selected_paks(m), [])
        by_key, variants, errors = collect_offers(
            [m], ConflictSettings(adapter_id="ue4_paks_mods", stage_root=stage)
        )
        self.assertTrue(variants or errors)
        self.assertEqual(by_key, {})

    def test_persist_loadout_components(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "col"
        paks = ["zzCloudHyperHD_CGI_noeyes.pak", "SexierShivaFixed.pak"]
        _write_paks(stage, paks, bundled=True)
        (stage / "collection.json").write_text("{}", encoding="utf-8")
        m = _mod(stage.name, stage, paks, usar=True)
        set_selected_paks(m, ["zzCloudHyperHD_CGI_noeyes.pak"])
        path = Path(td.name) / "loadout.json"
        save_loadout([m], path)
        m2 = _mod(stage.name, stage, paks, usar=False)
        merge_loadout([m2], path)
        self.assertEqual(selected_paks(m2), ["zzCloudHyperHD_CGI_noeyes.pak"])
        self.assertTrue(m2.usar)

    def test_dest_conflict_still_blocks(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        s1 = base / "a"
        s2 = base / "b"
        mods = base / "mods"
        mods.mkdir()
        (s1).mkdir(parents=True)
        (s2).mkdir(parents=True)
        (s1 / "Same.pak").write_bytes(b"CONTENT_A_DIFFERENT")
        (s2 / "Same.pak").write_bytes(b"CONTENT_B_OTHER_BYTES")
        m1 = _mod("A", s1, ["Same.pak"], usar=True, pak_elegido="Same.pak")
        m2 = _mod("B", s2, ["Same.pak"], usar=True, pak_elegido="Same.pak")
        plan = plan_apply(
            [m1, m2],
            ApplyContext(mods=mods, stage=base, data_dir=base / "data"),
            ConflictSettings(adapter_id="ue4_paks_mods"),
        )
        self.assertTrue(plan.errors or plan.file_unresolved or plan.conflicts >= 1)

    def test_ambiguous_is_manual_not_exclusive(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        stage = Path(td.name) / "amb"
        paks = ["AlphaThing.pak", "BetaThing.pak"]
        _write_paks(stage, paks)
        m = _mod(stage.name, stage, paks)
        rep = classify_components(m)
        self.assertIn(rep.mode, (REVISION_MANUAL, INDEPENDIENTES))
        self.assertNotEqual(rep.mode, VARIANTES_EXCLUYENTES)


if __name__ == "__main__":
    unittest.main()
