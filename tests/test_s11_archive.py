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

S11 — catálogo, zip slip, sandbox, plan (solo temporales).
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.archive_catalog import (  # noqa: E402
    ArchiveLinkStatus,
    build_catalog,
)
from app.core.archive_extract import (  # noqa: E402
    cleanup_sandbox,
    extract_to_sandbox,
    list_zip_members,
)
from app.core.archive_plan import simulate_archive_plan  # noqa: E402
from app.core.archive_verify import verify_mod_package  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402


def _mod(folder: str, stage: Path, files: dict[str, bytes]) -> ModEntry:
    d = stage / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    paks = [n for n in files if n.endswith(".pak")]
    return ModEntry(
        folder=folder,
        name=folder.split("-")[0] if "-" in folder else folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=False,
        on_disk=False,
        stage_path=str(d),
        nexus_id="1234" if "-1234-" in folder else None,
        usar=False,
        pak_elegido=paks[0] if paks else "",
    )


def _write_zip(path: Path, mapping: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in mapping.items():
            zf.writestr(name, data)


class S11ArchiveTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.dl = self.base / "downloads"
        self.stage.mkdir()
        self.dl.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_zip_intact_and_corrupt(self):
        z = self.dl / "ok.zip"
        _write_zip(z, {"a.pak": b"AAA"})
        names, errs = list_zip_members(z)
        self.assertEqual(errs, [])
        self.assertTrue(any("a.pak" in n for n in names))
        bad = self.dl / "bad.zip"
        bad.write_bytes(b"not-a-zip")
        names2, errs2 = list_zip_members(bad)
        self.assertTrue(errs2)

    def test_zip_slip_blocked(self):
        z = self.dl / "slip.zip"
        # crear zip con path traversal
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../escape.pak", b"EVIL")
        z.write_bytes(buf.getvalue())
        res = extract_to_sandbox(z, parent=self.base / "sb")
        self.assertFalse(res.ok)
        self.assertTrue(any("traversal" in e.lower() or "escape" in e.lower() for e in res.errors))
        cleanup_sandbox(res.sandbox)

    def test_staging_without_zip(self):
        m = _mod("OnlyStage-999-1", self.stage, {"x.pak": b"x"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(cat.mods[0].status, ArchiveLinkStatus.STAGING_ONLY.value)

    def test_zip_without_staging(self):
        _write_zip(self.dl / "orphan-555-1.zip", {"y.pak": b"y"})
        cat = build_catalog(
            game_id="t", mods=[], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(len(cat.download_only), 1)

    def test_nexus_match_and_verify_restore(self):
        folder = "CoolMod-1234-1-0-1700000000"
        m = _mod(folder, self.stage, {"Cool.pak": b"DATA"})
        _write_zip(self.dl / "CoolMod-1234-1-0-1700000000.zip", {"Cool.pak": b"DATA"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertTrue(cat.mods[0].archive_path)
        rep = verify_mod_package(
            cat.mods[0], deep_extract=True, sandbox_parent=self.base / "sb"
        )
        self.assertTrue(rep.recoverable)
        self.assertEqual(cat.mods[0].status, ArchiveLinkStatus.VERIFIED.value)

    def test_ambiguous_correspondence(self):
        folder = "Twin-42-1"
        m = _mod(folder, self.stage, {"t.pak": b"t"})
        _write_zip(self.dl / "Twin-42-1-a.zip", {"t.pak": b"t"})
        _write_zip(self.dl / "Twin-42-1-b.zip", {"t.pak": b"t"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(cat.mods[0].status, ArchiveLinkStatus.AMBIGUOUS.value)

    def test_special_installer_blocked(self):
        m = _mod("HookTool-1", self.stage, {"setup.exe": b"MZ", "d3dx.ini": b"x"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(cat.mods[0].status, ArchiveLinkStatus.SPECIAL_INSTALLER.value)

    def test_content_mismatch_not_recoverable(self):
        folder = "Mismatch-77-1"
        m = _mod(folder, self.stage, {"real.pak": b"R"})
        _write_zip(self.dl / "Mismatch-77-1.zip", {"other.pak": b"O"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        rep = verify_mod_package(cat.mods[0], deep_extract=False)
        self.assertFalse(rep.recoverable)
        self.assertNotEqual(rep.status, ArchiveLinkStatus.VERIFIED.value)

    def test_plan_blocks_without_sandbox_proof(self):
        folder = "PlanMod-8-1"
        m = _mod(folder, self.stage, {"p.pak": b"P"})
        _write_zip(self.dl / "PlanMod-8-1.zip", {"p.pak": b"P"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        verify_mod_package(cat.mods[0], deep_extract=False)
        sim = simulate_archive_plan(cat, [m])
        self.assertEqual(sim.archivable_count, 0)
        self.assertTrue(sim.rows[0].blocked)

    def test_plan_allows_after_sandbox_proof(self):
        folder = "PlanOk-9-1"
        m = _mod(folder, self.stage, {"p.pak": b"P"})
        _write_zip(self.dl / "PlanOk-9-1.zip", {"p.pak": b"P"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        verify_mod_package(
            cat.mods[0], deep_extract=True, sandbox_parent=self.base / "sb"
        )
        sim = simulate_archive_plan(cat, [m])
        self.assertEqual(sim.archivable_count, 1)
        self.assertFalse(sim.rows[0].blocked)

    def test_game_isolation_catalogs(self):
        m1 = _mod("A-1-1", self.stage, {"a.pak": b"a"})
        stage2 = self.base / "stage2"
        stage2.mkdir()
        m2 = _mod("B-2-2", stage2, {"b.pak": b"b"})
        c1 = build_catalog(game_id="g1", mods=[m1], downloads_dir=self.dl, stage_dir=self.stage)
        c2 = build_catalog(game_id="g2", mods=[m2], downloads_dir=self.dl, stage_dir=stage2)
        self.assertEqual(c1.game_id, "g1")
        self.assertEqual(c2.mods[0].folder, "B-2-2")
        self.assertNotEqual(c1.mods[0].folder, c2.mods[0].folder)

    def test_zip_bomb_limits(self):
        from app.core.archive_extract import MAX_FILES, extract_to_sandbox

        z = self.dl / "bomb.zip"
        with zipfile.ZipFile(z, "w", compression=zipfile.ZIP_STORED) as zf:
            for i in range(MAX_FILES + 5):
                zf.writestr(f"f{i}.txt", b"x")
        res = extract_to_sandbox(z, parent=self.base / "sb_bomb")
        self.assertFalse(res.ok)
        self.assertTrue(any("límite" in e.lower() or "limit" in e.lower() or "MAX" in e for e in res.errors) or any("archivos" in e.lower() for e in res.errors))
        cleanup_sandbox(res.sandbox)

    def test_variant_recoverable_vs_not(self):
        folder = "VarMod-55-1"
        m = _mod(folder, self.stage, {"A.pak": b"A", "B.pak": b"B"})
        m.pak_elegido = "A.pak"
        _write_zip(self.dl / "VarMod-55-1.zip", {"A.pak": b"A", "B.pak": b"B"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        rep = verify_mod_package(
            cat.mods[0], deep_extract=True, sandbox_parent=self.base / "sbv"
        )
        self.assertTrue(rep.recoverable)
        # variante no recuperable: staging tiene C.pak que no está en ZIP
        folder2 = "VarBad-56-1"
        m2 = _mod(folder2, self.stage, {"C.pak": b"C"})
        _write_zip(self.dl / "VarBad-56-1.zip", {"D.pak": b"D"})
        cat2 = build_catalog(
            game_id="t", mods=[m2], downloads_dir=self.dl, stage_dir=self.stage
        )
        rep2 = verify_mod_package(cat2.mods[0], deep_extract=False)
        self.assertFalse(rep2.recoverable)

    def test_hardlink_blocks_plan(self):
        folder = "HL-10-1"
        m = _mod(folder, self.stage, {"h.pak": b"H"})
        _write_zip(self.dl / "HL-10-1.zip", {"h.pak": b"H"})
        cat = build_catalog(
            game_id="t", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        verify_mod_package(
            cat.mods[0], deep_extract=True, sandbox_parent=self.base / "sbh"
        )
        mods_dir = self.base / "mods"
        mods_dir.mkdir()
        src = Path(m.stage_path) / "h.pak"
        dst = mods_dir / "h.pak"
        try:
            os.link(src, dst)
        except OSError:
            self.skipTest("hardlink no soportado en este volumen")
        sim = simulate_archive_plan(cat, [m], mods_dir=mods_dir)
        self.assertEqual(sim.archivable_count, 0)
        self.assertTrue(sim.rows[0].blocked)
        self.assertIn("hardlink", sim.rows[0].block_reason.lower())

    def test_transfer_plan_other_volume_sim(self):
        from app.core.archive_plan import plan_transfer_to_archive_dir

        a = self.dl / "dup-1.zip"
        b = self.dl / "other.zip"
        _write_zip(a, {"x.pak": b"x"})
        _write_zip(b, {"y.pak": b"y"})
        dest = self.base / "archive_vol"
        dest.mkdir()
        # simular duplicado ya en destino
        (dest / "dup-1.zip").write_bytes(a.read_bytes())
        plan = plan_transfer_to_archive_dir([str(a), str(b)], dest)
        self.assertFalse(plan.executable)
        self.assertIn("dup-1.zip", plan.duplicates)
        self.assertEqual(len(plan.sources), 2)
        self.assertTrue(any("vortex" in w.lower() for w in plan.warnings))

    def test_uninstalled_game_catalog_ok(self):
        # staging existe, mods_dir vacío / juego ausente — catálogo sigue
        m = _mod("OrphanGame-88-1", self.stage, {"o.pak": b"o"})
        _write_zip(self.dl / "OrphanGame-88-1.zip", {"o.pak": b"o"})
        cat = build_catalog(
            game_id="uninstalled",
            mods=[m],
            downloads_dir=self.dl,
            stage_dir=self.stage,
        )
        self.assertEqual(len(cat.mods), 1)
        self.assertTrue(cat.mods[0].archive_path)


if __name__ == "__main__":
    unittest.main()
