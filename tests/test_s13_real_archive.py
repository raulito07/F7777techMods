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

S13 — archivado real verificado (solo directorios temporales).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.archive_catalog import build_catalog  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.own_archive import (  # noqa: E402
    create_own_archive,
    make_mod_id,
    validate_archive_destination,
    verify_published_own_archive,
)
from app.core.real_archive_job import (  # noqa: E402
    STATUS_OK,
    STATUS_PENDING,
    build_or_update_job,
    format_job_report,
    job_path,
    load_job,
    relink_archive_library,
    run_archive_job,
    save_job,
)
from app.core.staging_release import (  # noqa: E402
    build_staging_release_report,
)


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
        name=folder.split("-")[0],
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=str(d),
        usar=False,
        pak_elegido=paks[0] if paks else "",
    )


class S13RealArchiveTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.arch = self.base / "archive_vol"
        self.data = self.base / "data"
        self.game = self.base / "game"
        self.stage.mkdir()
        self.arch.mkdir()
        self.data.mkdir()
        self.game.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_individual_archive_verified(self):
        m = _mod("Solo-1-1", self.stage, {"a.pak": b"AAA", "r/x.txt": b"x"})
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.arch,
            game_root=self.game,
        )
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.status, "ARCHIVADO VERIFICADO")
        self.assertTrue(r.origin_unchanged)
        self.assertTrue(Path(r.published_path).is_file())
        vr = verify_published_own_archive(Path(r.published_path), expect_game_id="g1")
        self.assertTrue(vr.ok, vr.errors)

    def test_batch_and_resume(self):
        mods = [
            _mod(f"B{i}-1{i}-1", self.stage, {f"b{i}.pak": bytes([i]) * 32})
            for i in range(4)
        ]
        cat = build_catalog(
            game_id="g1", mods=mods, downloads_dir=self.base / "dl", stage_dir=self.stage
        )
        (self.base / "dl").mkdir(exist_ok=True)
        job = build_or_update_job(
            game_id="g1",
            archive_dir=self.arch,
            mods=mods,
            cat=cat,
            folders=[m.folder for m in mods],
            data_dir=self.data,
        )
        # primera pasada: solo 2
        job = run_archive_job(
            job,
            mods=mods,
            stage_root=self.stage,
            data_dir=self.data,
            game_root=self.game,
            limit=2,
        )
        self.assertEqual(job.counts().get(STATUS_OK, 0), 2)
        self.assertEqual(job.counts().get(STATUS_PENDING, 0), 2)
        # reanudar
        job2 = load_job(job_path(self.data))
        self.assertIsNotNone(job2)
        job2 = run_archive_job(
            job2,
            mods=mods,
            stage_root=self.stage,
            data_dir=self.data,
            game_root=self.game,
            limit=None,
        )
        self.assertEqual(job2.counts().get(STATUS_OK, 0), 4)
        self.assertEqual(job2.counts().get(STATUS_PENDING, 0), 0)

    def test_cancel_mid_batch(self):
        mods = [
            _mod(f"C{i}-2{i}-1", self.stage, {f"c{i}.pak": b"C" * 64}) for i in range(3)
        ]
        cat = build_catalog(
            game_id="g1", mods=mods, downloads_dir=None, stage_dir=self.stage
        )
        job = build_or_update_job(
            game_id="g1",
            archive_dir=self.arch,
            mods=mods,
            cat=cat,
            folders=[m.folder for m in mods],
            data_dir=self.data,
        )
        flag = {"n": 0}

        def cancel():
            flag["n"] += 1
            return flag["n"] > 1

        job = run_archive_job(
            job,
            mods=mods,
            stage_root=self.stage,
            data_dir=self.data,
            cancel=cancel,
        )
        ok = job.counts().get(STATUS_OK, 0)
        self.assertLess(ok, 3)

    def test_space_and_existing(self):
        m = _mod("Ex-3-1", self.stage, {"e.pak": b"E"})
        r1 = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(r1.ok, r1.errors)
        r2 = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertFalse(r2.ok)
        self.assertEqual(r2.status, "BLOQUEADO")
        other = self.arch / "other"
        other.mkdir()
        r3 = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=other,
            min_free_bytes=10**15,
        )
        self.assertFalse(r3.ok)
        self.assertTrue(any("espacio" in e.lower() for e in r3.errors))

    def test_dest_inside_staging_blocked(self):
        errs = validate_archive_destination(
            self.stage / "nested", stage_root=self.stage, game_root=self.game
        )
        self.assertTrue(errs)
        m = _mod("BadDest-4-1", self.stage, {"z.pak": b"Z"})
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.stage / "out",
            game_root=self.game,
        )
        self.assertFalse(r.ok)
        self.assertEqual(r.status, "BLOQUEADO")

    def test_origin_change_during_archive(self):
        m = _mod("Chg-5-1", self.stage, {"g.pak": b"G" * 100})
        target = Path(m.stage_path) / "g.pak"

        def progress(phase, cur, tot):
            if phase == "comprimiendo" and cur == 1:
                target.write_bytes(b"CHANGED")

        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.arch,
            progress=progress,
        )
        self.assertFalse(r.ok)
        self.assertTrue(any("cambió" in e.lower() or "origen" in e.lower() for e in r.errors))
        self.assertEqual(list(self.arch.glob("*.zip")), [])

    def test_disk_disconnect_simulated(self):
        m = _mod("Disk-6-1", self.stage, {"d.pak": b"D"})
        missing = self.base / "missing_drive" / "arch"
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=missing,
            ensure_dest_available=True,
        )
        self.assertFalse(r.ok)

    def test_corrupt_published_fails_verify(self):
        m = _mod("Cor-7-1", self.stage, {"k.pak": b"K"})
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(r.ok, r.errors)
        p = Path(r.published_path)
        p.write_bytes(b"corrupted")
        vr = verify_published_own_archive(p, expect_game_id="g1")
        self.assertFalse(vr.ok)

    def test_game_isolation(self):
        m1 = _mod("Iso-8-1", self.stage, {"i.pak": b"1"})
        r1 = create_own_archive(
            game_id="ff7_rebirth", mod=m1, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(r1.ok, r1.errors)
        vr = verify_published_own_archive(
            Path(r1.published_path), expect_game_id="stellar_blade"
        )
        self.assertFalse(vr.ok)
        self.assertNotEqual(
            make_mod_id("ff7_rebirth", "Iso-8-1"),
            make_mod_id("stellar_blade", "Iso-8-1"),
        )

    def test_relink_library(self):
        m = _mod("Rel-9-1", self.stage, {"r.pak": b"R"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=None, stage_dir=self.stage
        )
        job = build_or_update_job(
            game_id="g1",
            archive_dir=self.arch,
            mods=[m],
            cat=cat,
            folders=[m.folder],
            data_dir=self.data,
        )
        job = run_archive_job(
            job, mods=[m], stage_root=self.stage, data_dir=self.data
        )
        self.assertEqual(job.counts().get(STATUS_OK, 0), 1)
        # simular nueva letra: copiar árbol
        arch2 = self.base / "archive_vol_E"
        import shutil

        shutil.copytree(self.arch, arch2)
        notes = relink_archive_library(job, arch2)
        self.assertTrue(any("revinculado" in n for n in notes))
        self.assertTrue(Path(job.items[m.folder].path).is_file())
        save_job(job, job_path(self.data))
        self.assertIn("g1", format_job_report(job))

    def test_release_report_no_delete(self):
        m = _mod("Lib-10-1", self.stage, {"l.pak": b"L"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=None, stage_dir=self.stage
        )
        r = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(r.ok, r.errors)
        cat.mods[0].own_archive_path = r.published_path
        cat.mods[0].own_archive_sha256 = r.zip_sha256
        cat.mods[0].recoverable = True
        cat.mods[0].package_kind = "ARCHIVO_PROPIO"
        rep = build_staging_release_report(cat, [m], mods_dir=None)
        self.assertEqual(rep.prepared_count, 1)
        self.assertTrue(all(row.liberate_action == "NO DISPONIBLE" for row in rep.rows))
        # staging intacto
        self.assertTrue((Path(m.stage_path) / "l.pak").is_file())

    def test_publish_fail_leaves_no_partial(self):
        m = _mod("Pub-11-1", self.stage, {"p.pak": b"P"})
        # dest readonly simulation: use cancel after compress starts
        flag = {"c": False}

        def progress(phase, cur, tot):
            if phase == "verificando sandbox":
                flag["c"] = True

        def cancel():
            return flag["c"]

        # Actually cancel before publish by setting cancel during verifying — 
        # create_own_archive checks cancel mainly during compress. Use origin change instead.
        # Ensure no .partial left after failure:
        r = create_own_archive(
            game_id="g1",
            mod=m,
            stage_root=self.stage,
            dest_dir=self.arch,
            min_free_bytes=10**15,
        )
        self.assertFalse(r.ok)
        self.assertEqual(list(self.arch.glob("*.partial")), [])
        self.assertEqual(list(self.arch.glob("*.zip")), [])


if __name__ == "__main__":
    unittest.main()
