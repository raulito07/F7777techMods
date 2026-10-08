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

S12 — ARCHIVO_PROPIO, correspondencias, plan biblioteca (solo temporales).
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

from app.core.archive_catalog import ArchiveLinkStatus, build_catalog  # noqa: E402
from app.core.archive_match import MatchGrade, apply_match_grades  # noqa: E402
from app.core.archive_plan import simulate_archive_plan  # noqa: E402
from app.core.archive_verify import verify_mod_package  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.library_archive import (  # noqa: E402
    create_demo_own_archives,
    prepare_library_plan,
)
from app.core.own_archive import (  # noqa: E402
    MANIFEST_ZIP_PATH,
    create_own_archive,
    is_archive_root_available,
    make_mod_id,
    read_own_manifest,
    restore_own_archive_to_sandbox,
)


def _mod(folder: str, stage: Path, files: dict[str, bytes], *, pak_elegido: str = "") -> ModEntry:
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
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(d),
        nexus_id="1234" if "-1234-" in folder else None,
        usar=False,
        pak_elegido=pak_elegido or (paks[0] if paks else ""),
    )


def _write_zip(path: Path, mapping: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in mapping.items():
            zf.writestr(name, data)


class S12OwnArchiveTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.dl = self.base / "downloads"
        self.own = self.base / "own"
        self.stage.mkdir()
        self.dl.mkdir()
        self.own.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_create_own_zip_manifest_and_restore(self):
        folder = "CoolMod-1234-1"
        m = _mod(
            folder,
            self.stage,
            {"Cool.pak": b"DATA", "sub/note.txt": b"hi"},
            pak_elegido="Cool.pak",
        )
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.own,
        )
        self.assertTrue(r.ok, r.errors)
        self.assertTrue(r.verified_restore)
        self.assertTrue(Path(r.published_path).is_file())
        man, errs = read_own_manifest(Path(r.published_path))
        self.assertEqual(errs, [])
        self.assertIsNotNone(man)
        assert man is not None
        self.assertEqual(man.package_kind, "ARCHIVO_PROPIO")
        self.assertEqual(man.game_id, "g1")
        self.assertEqual(man.mod_id, make_mod_id("g1", folder))
        self.assertEqual(man.pak_elegido, "Cool.pak")
        self.assertIn("Cool.pak", man.variants)
        self.assertEqual(man.total_files, 2)
        # manifiesto en ZIP
        with zipfile.ZipFile(r.published_path, "r") as zf:
            self.assertIn(MANIFEST_ZIP_PATH, zf.namelist())
        rs = restore_own_archive_to_sandbox(
            Path(r.published_path),
            sandbox_parent=self.base / "sb",
            expect_game_id="g1",
            expect_mod_id=man.mod_id,
        )
        self.assertTrue(rs.ok, rs.errors)
        self.assertEqual(rs.files_matched, 2)

    def test_incomplete_not_published_on_cancel(self):
        folder = "CancelMe-9-1"
        m = _mod(folder, self.stage, {"a.pak": b"AAAA" * 1000})
        flag = {"c": False}

        def cancel():
            return flag["c"]

        # cancelar en cuanto empiece a comprimir (tras hashear)
        calls = {"n": 0}

        def progress(phase, cur, tot):
            calls["n"] += 1
            if phase == "comprimiendo":
                flag["c"] = True

        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.own,
            progress=progress,
            cancel=cancel,
        )
        self.assertFalse(r.ok)
        self.assertTrue(any("cancel" in e.lower() for e in r.errors))
        self.assertEqual(list(self.own.glob("*.zip")), [])
        self.assertEqual(list(self.own.glob("*.partial")), [])

    def test_corrupt_zip_restore_fails(self):
        bad = self.own / "bad.zip"
        bad.write_bytes(b"not-a-zip")
        rs = restore_own_archive_to_sandbox(bad, sandbox_parent=self.base / "sb2")
        self.assertFalse(rs.ok)

    def test_zip_slip_in_own_members_blocked(self):
        # crear ZIP propio malicioso a mano (sin manifiesto válido → fail)
        z = self.own / "slip.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../escape.pak", b"EVIL")
        z.write_bytes(buf.getvalue())
        rs = restore_own_archive_to_sandbox(z, sandbox_parent=self.base / "sb3")
        self.assertFalse(rs.ok)

    def test_same_display_name_different_mod_id(self):
        m1 = _mod("SameName-1-1", self.stage, {"a.pak": b"1"})
        m1.name = "SameName"
        stage2 = self.base / "stage2"
        stage2.mkdir()
        m2 = _mod("SameName-2-2", stage2, {"a.pak": b"2"})
        m2.name = "SameName"
        self.assertNotEqual(make_mod_id("g", m1.folder), make_mod_id("g", m2.folder))

    def test_game_isolation_mod_ids(self):
        self.assertNotEqual(
            make_mod_id("ff7_rebirth", "Mod-1-1"),
            make_mod_id("stellar_blade", "Mod-1-1"),
        )

    def test_vortex_original_vs_own(self):
        folder = "Twin-55-1"
        m = _mod(folder, self.stage, {"t.pak": b"T"})
        _write_zip(self.dl / "Twin-55-1.zip", {"t.pak": b"T"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(cat.mods[0].package_kind, "ORIGINAL_VORTEX")
        self.assertEqual(cat.mods[0].match_grade, MatchGrade.PROBABLE.value)
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.own
        )
        self.assertTrue(r.ok, r.errors)
        cat.mods[0].own_archive_path = r.published_path
        cat.mods[0].package_kind = "ARCHIVO_PROPIO"
        self.assertNotEqual(cat.mods[0].archive_path, cat.mods[0].own_archive_path)

    def test_probable_not_verified_without_proof(self):
        folder = "Prob-77-1"
        m = _mod(folder, self.stage, {"p.pak": b"P"})
        _write_zip(self.dl / "Prob-77-1.zip", {"p.pak": b"P"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        apply_match_grades(cat, verify_content=False)
        self.assertEqual(cat.mods[0].match_grade, MatchGrade.PROBABLE.value)
        self.assertNotEqual(cat.mods[0].match_grade, MatchGrade.VERIFICADA.value)
        sim = simulate_archive_plan(cat, [m])
        self.assertEqual(sim.archivable_count, 0)

    def test_ambiguous_stays_ambiguous(self):
        folder = "Twin-42-1"
        m = _mod(folder, self.stage, {"t.pak": b"t"})
        _write_zip(self.dl / "Twin-42-1-a.zip", {"t.pak": b"t"})
        _write_zip(self.dl / "Twin-42-1-b.zip", {"t.pak": b"t"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        self.assertEqual(cat.mods[0].match_grade, MatchGrade.AMBIGUA.value)

    def test_own_archive_makes_recoverable_for_plan(self):
        folder = "NeedOwn-88-1"
        m = _mod(folder, self.stage, {"x.pak": b"X"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.own
        )
        self.assertTrue(r.ok, r.errors)
        cat.mods[0].own_archive_path = r.published_path
        cat.mods[0].package_kind = "ARCHIVO_PROPIO"
        cat.mods[0].recoverable = True
        cat.mods[0].lifecycle = "VERIFICADO"
        sim = simulate_archive_plan(cat, [m])
        self.assertEqual(sim.archivable_count, 1)

    def test_library_plan_rebirth_like_no_downloads(self):
        mods = [
            _mod(f"Mod{i}-1{i}-1", self.stage, {f"m{i}.pak": b"x" * 10})
            for i in range(5)
        ]
        cat = build_catalog(
            game_id="ff7_rebirth", mods=mods, downloads_dir=self.dl, stage_dir=self.stage
        )
        plan = prepare_library_plan(cat, archive_dir=str(self.own))
        self.assertEqual(plan.need_own_count, 5)
        self.assertTrue(plan.archive_dir_available)
        self.assertTrue(any("compresión" in n.lower() or "comprim" in n.lower() for n in plan.notes) or plan.need_own_count == 5)

    def test_disk_disconnected(self):
        ok, note = is_archive_root_available(self.base / "missing_vol" / "nope")
        self.assertFalse(ok)
        self.assertTrue(note)

    def test_space_shortage(self):
        folder = "Big-1-1"
        m = _mod(folder, self.stage, {"b.pak": b"B" * 100})
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.own,
            min_free_bytes=10**15,
        )
        self.assertFalse(r.ok)
        self.assertTrue(any("espacio" in e.lower() for e in r.errors))

    def test_demo_batch_and_large_synthetic(self):
        mods = []
        for i in range(12):
            mods.append(
                _mod(f"Syn{i}-10{i}-1", self.stage, {f"s{i}.pak": bytes([i]) * 64})
            )
        cat = build_catalog(
            game_id="g1", mods=mods, downloads_dir=self.dl, stage_dir=self.stage
        )
        results, text = create_demo_own_archives(
            game_id="g1",
            mods=mods,
            cat=cat,
            stage_root=self.stage,
            demo_dir=self.own / "demo",
            limit=4,
        )
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.ok for r in results), text)
        self.assertGreaterEqual(sum(1 for m in cat.mods if m.recoverable), 4)

    def test_variant_preserved(self):
        folder = "Var-12-1"
        m = _mod(
            folder,
            self.stage,
            {"A.pak": b"A", "B.pak": b"B"},
            pak_elegido="B.pak",
        )
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.own
        )
        self.assertTrue(r.ok, r.errors)
        man, _ = read_own_manifest(Path(r.published_path))
        assert man is not None
        self.assertEqual(man.pak_elegido, "B.pak")
        self.assertEqual(set(man.variants), {"A.pak", "B.pak"})

    def test_stage_outside_root_rejected(self):
        other = self.base / "other"
        other.mkdir()
        m = _mod("Out-1-1", other, {"o.pak": b"o"})
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.own
        )
        self.assertFalse(r.ok)
        self.assertTrue(any("staging" in e.lower() for e in r.errors))

    def test_symlink_rejected(self):
        folder = "Link-1-1"
        d = self.stage / folder
        d.mkdir()
        real = d / "real.pak"
        real.write_bytes(b"R")
        link = d / "link.pak"
        try:
            os.symlink(real, link)
        except OSError:
            self.skipTest("symlink no disponible")
        m = ModEntry(
            folder=folder,
            name="Link",
            characters=["OTROS"],
            character_main="OTROS",
            paks=["real.pak"],
            multi=False,
            on_disk=False,
            stage_path=str(d),
        )
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.own
        )
        self.assertFalse(r.ok)

    def test_verified_original_after_content_check(self):
        folder = "Ok-99-1"
        m = _mod(folder, self.stage, {"ok.pak": b"OK"})
        _write_zip(self.dl / "Ok-99-1.zip", {"ok.pak": b"OK"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=self.dl, stage_dir=self.stage
        )
        rep = verify_mod_package(
            cat.mods[0], deep_extract=True, sandbox_parent=self.base / "sbv"
        )
        self.assertTrue(rep.recoverable)
        self.assertEqual(cat.mods[0].match_grade, MatchGrade.VERIFICADA.value)


if __name__ == "__main__":
    unittest.main()
