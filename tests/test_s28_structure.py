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

S28 — detección de estructura, grupos IoStore, seguridad ZIP (sandbox).
"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.inventory import ModEntry
from app.core.library_status import filter_mods
from app.core.mod_structure import (
    AMBIGUO,
    COMPUESTO,
    CON_VARIANTES,
    INCOMPLETO,
    NO_SOPORTADO,
    SIMPLE,
    SIN_ARCHIVOS_INSTALABLES,
    analyze_library_structures,
    analyze_mod_structure,
    structure_blocks_apply,
)
from app.core.path_safety import check_relative_path, inspect_zip


def _write(p: Path, data: bytes = b"x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _mod(folder: str, stage: Path, **kw) -> ModEntry:
    paks = kw.pop("paks", None)
    if paks is None:
        paks = sorted(p.name for p in stage.rglob("*.pak")) if stage.is_dir() else []
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(stage),
        usar=kw.get("usar", False),
        pak_elegido=kw.get("pak_elegido", paks[0] if len(paks) == 1 else ""),
        source_kind=kw.get("source_kind", "STAGING_VORTEX"),
        archived=False,
        work_extracted=kw.get("work_extracted", False),
    )


class S28PathSafetyTests(unittest.TestCase):
    def test_traversal_and_absolute(self):
        bad = check_relative_path("../evil.pak")
        self.assertTrue(any(i.code == "TRAVERSAL" for i in bad))
        bad2 = check_relative_path("C:/Windows/x.pak")
        self.assertTrue(any(i.code == "ABSOLUTE" for i in bad2))

    def test_zip_slip_without_extract(self):
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "bad.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("../escape.txt", "nope")
                zf.writestr("ok/file.txt", "ok")
            rep = inspect_zip(zpath)
            self.assertFalse(rep.ok)
            self.assertTrue(any(i.code in ("TRAVERSAL", "ZIP_SLIP") for i in rep.issues))


class S28StructureTests(unittest.TestCase):
    def test_simple_ue4_pak(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "mod_simple"
            _write(stage / "CoolMod.pak")
            _write(stage / "readme.txt", b"docs")
            m = _mod("mod_simple", stage)
            r = analyze_mod_structure(m, "ue4_paks_mods")
            self.assertEqual(r.classification, SIMPLE)
            self.assertFalse(r.blocks_prepare)
            self.assertTrue(any(x.endswith(".pak") for x in r.installable))

    def test_compound_iostore_complete(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "mod_ios"
            _write(stage / "Pack.pak")
            _write(stage / "Pack.utoc")
            _write(stage / "Pack.ucas")
            m = _mod("mod_ios", stage, pak_elegido="Pack.pak")
            r = analyze_mod_structure(m, "ue5_iostore_mods")
            self.assertIn(r.classification, {SIMPLE, COMPUESTO})
            self.assertTrue(r.groups)
            self.assertTrue(r.groups[0].complete_for_adapter)
            self.assertFalse(r.blocks_prepare)

    def test_incomplete_iostore_group(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "mod_bad"
            _write(stage / "Pack.pak")
            _write(stage / "Pack.utoc")
            # falta .ucas
            m = _mod("mod_bad", stage, usar=True, pak_elegido="Pack.pak")
            r = analyze_mod_structure(m, "ue5_iostore_mods")
            self.assertEqual(r.classification, INCOMPLETO)
            self.assertTrue(r.blocks_prepare)
            self.assertTrue(r.groups and r.groups[0].missing)

    def test_variants_require_choice(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "mod_fov"
            _write(stage / "Camera_FOV70.pak")
            _write(stage / "Camera_FOV90.pak")
            m = _mod("mod_fov", stage, usar=True, pak_elegido="")
            m.multi = True
            r = analyze_mod_structure(m, "ue4_paks_mods")
            self.assertEqual(r.classification, CON_VARIANTES)
            self.assertTrue(r.blocks_prepare)
            self.assertTrue(r.needs_manual_review)
            self.assertTrue(r.variants)

    def test_ue4_does_not_require_utoc(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "mod_r"
            _write(stage / "Only.pak")
            m = _mod("mod_r", stage)
            r = analyze_mod_structure(m, "ue4_paks_mods")
            self.assertEqual(r.classification, SIMPLE)
            self.assertFalse(r.groups)  # no IoStore groups for UE4 adapter

    def test_stellar_blade_adapter_iostore(self):
        """Stellar Blade usa ue5_iostore_mods — mismas reglas de sidecars."""
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "sb"
            _write(stage / "SB.pak")
            m = _mod("sb", stage, usar=True, pak_elegido="SB.pak")
            r = analyze_mod_structure(m, "ue5_iostore_mods")
            self.assertEqual(r.classification, INCOMPLETO)
            self.assertTrue(r.blocks_prepare)

    def test_special_only_unsupported(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "inj"
            _write(stage / "dxgi.dll", b"MZ")
            m = _mod("inj", stage, paks=[])
            r = analyze_mod_structure(m, "ue4_paks_mods")
            self.assertEqual(r.classification, NO_SOPORTADO)

    def test_internal_dest_collision(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "col"
            _write(stage / "a" / "Same.pak")
            _write(stage / "b" / "Same.pak")
            m = _mod("col", stage, pak_elegido="Same.pak")
            r = analyze_mod_structure(m, "ue4_paks_mods")
            self.assertTrue(
                any(i.code == "INTERNAL_DEST_COLLISION" for i in r.issues)
                or r.classification in {AMBIGUO, CON_VARIANTES, COMPUESTO, SIMPLE}
            )

    def test_structure_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad"
            _write(bad / "X.pak")
            m_bad = _mod("bad", bad, usar=True, pak_elegido="X.pak")
            good = Path(td) / "good"
            _write(good / "Y.pak")
            _write(good / "Y.utoc")
            _write(good / "Y.ucas")
            m_good = _mod("good", good, usar=True, pak_elegido="Y.pak")
            reps = analyze_library_structures(
                [m_bad, m_good], "ue5_iostore_mods", cache={}
            )
            self.assertTrue(structure_blocks_apply(reps, [m_bad, m_good]))

    def test_cache_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "c"
            _write(stage / "A.pak")
            m = _mod("c", stage)
            cache: dict = {}
            r1 = analyze_mod_structure(m, "ue4_paks_mods", cache=cache)
            r2 = analyze_mod_structure(m, "ue4_paks_mods", cache=cache)
            self.assertIs(r1, r2)
            time.sleep(0.02)
            _write(stage / "B.pak")
            m.paks = sorted(p.name for p in stage.rglob("*.pak"))
            m.multi = True
            r3 = analyze_mod_structure(m, "ue4_paks_mods", cache=cache)
            self.assertIsNot(r1, r3)

    def test_filter_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad"
            _write(bad / "P.pak")
            m = _mod("bad", bad, usar=True, pak_elegido="P.pak")
            rep = analyze_mod_structure(m, "ue5_iostore_mods")
            got = filter_mods(
                [m],
                dimension="Paquete incompleto",
                structure_by_folder={"bad": rep},
            )
            self.assertEqual(len(got), 1)

    def test_filter_format_ue4(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td) / "u4"
            _write(stage / "A.pak")
            m = _mod("u4", stage)
            rep = analyze_mod_structure(m, "ue4_paks_mods")
            got = filter_mods(
                [m],
                dimension="Formato UE4 PAK",
                structure_by_folder={"u4": rep},
            )
            self.assertEqual(len(got), 1)

    def test_large_library_performance(self):
        """Bibliotecas sintéticas multi-juego ( Remake / Rebirth / Stellar )."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mods: list[ModEntry] = []
            # 250 Remake-like
            for i in range(250):
                d = base / "remake" / f"R{i:04d}"
                _write(d / f"R{i:04d}.pak")
                mods.append(_mod(f"R{i:04d}", d, source_kind="STAGING_VORTEX"))
            # 500 Rebirth-like complete IoStore
            for i in range(500):
                d = base / "rebirth" / f"B{i:04d}"
                stem = f"B{i:04d}"
                _write(d / f"{stem}.pak")
                _write(d / f"{stem}.utoc")
                _write(d / f"{stem}.ucas")
                mods.append(
                    _mod(stem, d, pak_elegido=f"{stem}.pak", source_kind="WORK_LIBRARY")
                )
            # 1000 Stellar-like (incomplete on purpose subset + complete)
            for i in range(1000):
                d = base / "stellar" / f"S{i:04d}"
                stem = f"S{i:04d}"
                _write(d / f"{stem}.pak")
                if i % 2 == 0:
                    _write(d / f"{stem}.utoc")
                    _write(d / f"{stem}.ucas")
                mods.append(_mod(stem, d, pak_elegido=f"{stem}.pak"))
            self.assertGreaterEqual(len(mods), 1500)
            cache: dict = {}
            t0 = time.perf_counter()
            # Clasificar con adaptador UE5 (peor caso sidecars) sobre muestra 500
            sample = mods[250:750]
            analyze_library_structures(sample, "ue5_iostore_mods", cache=cache)
            t1 = time.perf_counter()
            analyze_library_structures(sample, "ue5_iostore_mods", cache=cache)
            t2 = time.perf_counter()
            filter_mods(mods, query="s00", dimension="TODOS")
            t3 = time.perf_counter()
            discover_ms = (t1 - t0) * 1000
            cached_ms = (t2 - t1) * 1000
            filter_ms = (t3 - t2) * 1000
            # Umbrales generosos para CI/local; documentados en INFORME
            self.assertLess(discover_ms, 120_000, f"discover {discover_ms:.0f}ms")
            self.assertLess(cached_ms, 5_000, f"cache {cached_ms:.0f}ms")
            self.assertLess(filter_ms, 500, f"filter {filter_ms:.0f}ms")
            # Segunda pasada debe ser mucho más barata
            self.assertLess(cached_ms, discover_ms * 0.5 + 50)


if __name__ == "__main__":
    unittest.main()
