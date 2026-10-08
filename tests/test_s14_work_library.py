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

S14 — biblioteca de trabajo y simulación liberación (solo temporales).
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
from app.core.archive_catalog import build_catalog  # noqa: E402
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.liberation_plan import (  # noqa: E402
    estimate_physical_bytes,
    simulate_staging_liberation,
)
from app.core.own_archive import create_own_archive  # noqa: E402
from app.core.work_install import prepare_install_from_work  # noqa: E402
from app.core.work_library import (  # noqa: E402
    PRESENCE_ARCHIVED,
    PRESENCE_VORTEX,
    PRESENCE_WORK,
    cleanup_work_library,
    classify_presence,
    load_index,
    mark_in_use,
    pin_mod,
    resolve_work_root,
    restore_archive_to_work,
    restore_many_to_work,
    work_record_to_mod_entry,
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
        pak_elegido=paks[0] if len(paks) == 1 else "",
    )


class S14WorkLibraryTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "vortex_stage"
        self.arch = self.base / "archive"
        self.data = self.base / "data"
        self.mods_dst = self.base / "game_mods"
        self.stage.mkdir()
        self.arch.mkdir()
        self.data.mkdir()
        self.mods_dst.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def _archive_mod(self, folder: str, files: dict[str, bytes], *, game_id="g1"):
        m = _mod(folder, self.stage, files)
        r = create_own_archive(
            game_id=game_id, mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(r.ok, r.errors)
        return m, r

    def test_restore_individual_and_not_vortex(self):
        m, r = self._archive_mod("A-1-1", {"a.pak": b"A", "n.txt": b"n"})
        work = resolve_work_root(self.data, stage_dir=self.stage)
        idx = load_index(work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(r.published_path),
            work_root=work,
            idx=idx,
        )
        self.assertTrue(rr.ok, rr.errors)
        self.assertTrue(Path(rr.work_path).is_dir())
        # no escribió en staging Vortex nuevo
        self.assertNotEqual(Path(rr.work_path).resolve(), Path(m.stage_path).resolve())
        self.assertTrue((Path(rr.work_path) / "a.pak").is_file())

    def test_restore_batch_and_variants(self):
        mods_r = []
        paths = []
        for i, pak in enumerate(["X.pak", "Y.pak"]):
            folder = f"Var-{10+i}-1"
            m = _mod(folder, self.stage, {pak: b"V", "Z.pak": b"Z"})
            m.pak_elegido = pak
            r = create_own_archive(
                game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
            )
            self.assertTrue(r.ok, r.errors)
            paths.append(Path(r.published_path))
            mods_r.append(m)
        work = self.data / "work_library"
        results, idx = restore_many_to_work(
            game_id="g1", archives=paths, work_root=work
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(x.ok for x in results))
        for rec in idx.mods.values():
            self.assertTrue(rec.pak_elegido)
            self.assertGreaterEqual(len(rec.variants), 1)

    def test_install_plan_from_work(self):
        m, r = self._archive_mod("Inst-2-1", {"i.pak": b"II"})
        work = self.data / "work_library"
        idx = load_index(work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(r.published_path),
            work_root=work,
            idx=idx,
        )
        self.assertTrue(rr.ok, rr.errors)
        idx = load_index(work, game_id="g1")
        ctx = ApplyContext(
            mods=self.mods_dst,
            deploy=self.mods_dst / "vortex.deployment.json",
            loadout_marker=self.mods_dst / "_manual_loadout.json",
            manifest=self.data / "managed_manifest.json",
            backups=self.data / "backups",
            stage=work,
            data_dir=self.data,
        )
        settings = ConflictSettings(adapter_id="ue4_paks_mods", stage_root=work)
        prep = prepare_install_from_work(
            idx, mod_ids=None, ctx=ctx, settings=settings
        )
        self.assertEqual(prep.mod_count, 1)
        self.assertEqual(prep.blockers, 0)
        # plan_apply directo
        ent = work_record_to_mod_entry(list(idx.mods.values())[0], usar=True)
        plan = plan_apply([ent], ctx=ctx, settings=settings)
        self.assertEqual(plan.conflicts, 0)
        self.assertTrue(plan.to_add)

    def test_cleanup_keeps_in_use(self):
        _, r1 = self._archive_mod("C1-3-1", {"c1.pak": b"1"})
        _, r2 = self._archive_mod("C2-3-2", {"c2.pak": b"2"})
        work = self.data / "work_library"
        results, idx = restore_many_to_work(
            game_id="g1",
            archives=[Path(r1.published_path), Path(r2.published_path)],
            work_root=work,
        )
        self.assertTrue(all(x.ok for x in results))
        mid = list(idx.mods.keys())[0]
        mark_in_use(idx, [mid], in_use=True)
        removed, notes = cleanup_work_library(idx, only_unused=True)
        self.assertEqual(removed, 1)
        self.assertEqual(len(idx.mods), 1)
        self.assertIn(mid, idx.mods)

    def test_pin_blocks_cleanup(self):
        _, r = self._archive_mod("Pin-4-1", {"p.pak": b"P"})
        work = self.data / "work_library"
        idx = load_index(work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(r.published_path),
            work_root=work,
            idx=idx,
        )
        self.assertTrue(rr.ok)
        idx = load_index(work, game_id="g1")
        pin_mod(idx, rr.mod_id, pinned=True)
        removed, _ = cleanup_work_library(idx, only_unused=True)
        self.assertEqual(removed, 0)

    def test_integrity_fail_on_tampered_zip(self):
        _, r = self._archive_mod("Tam-5-1", {"t.pak": b"T"})
        p = Path(r.published_path)
        p.write_bytes(b"not-zip-anymore")
        work = self.data / "work_library"
        idx = load_index(work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1", archive_path=p, work_root=work, idx=idx
        )
        self.assertFalse(rr.ok)
        self.assertFalse(list(work.glob("sgm_*")))

    def test_work_not_inside_staging(self):
        root = resolve_work_root(
            self.data,
            configured=str(self.stage / "nested_work"),
            stage_dir=self.stage,
        )
        self.assertEqual(root, self.data / "work_library")

    def test_game_isolation(self):
        _, r = self._archive_mod("Iso-6-1", {"i.pak": b"I"}, game_id="rebirth")
        work_a = self.data / "games" / "a" / "work_library"
        work_b = self.data / "games" / "b" / "work_library"
        idx_a = load_index(work_a, game_id="rebirth")
        ok = restore_archive_to_work(
            game_id="rebirth",
            archive_path=Path(r.published_path),
            work_root=work_a,
            idx=idx_a,
        )
        self.assertTrue(ok.ok)
        # wrong game_id
        idx_b = load_index(work_b, game_id="stellar")
        bad = restore_archive_to_work(
            game_id="stellar",
            archive_path=Path(r.published_path),
            work_root=work_b,
            idx=idx_b,
        )
        self.assertFalse(bad.ok)

    def test_liberation_sim_blocked_with_vortex_staging(self):
        m, r = self._archive_mod("Lib-7-1", {"l.pak": b"L"})
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=None, stage_dir=self.stage
        )
        cat.mods[0].own_archive_path = r.published_path
        cat.mods[0].recoverable = True
        cat.mods[0].package_kind = "ARCHIVO_PROPIO"
        sim = simulate_staging_liberation(cat, [m], mods_dir=self.mods_dst)
        self.assertTrue(all(row.blocked for row in sim.rows))
        self.assertTrue(
            any("NO DISPONIBLE" in n or "no autoriz" in n.lower() for n in sim.notes)
            or all(
                row.liberate_action
                in ("BLOQUEADO", "NO DISPONIBLE", "PENDIENTE_VORTEX")
                for row in sim.rows
            )
        )
        self.assertTrue(all(not row.execution_available for row in sim.rows))
        # staging intacto
        self.assertTrue((Path(m.stage_path) / "l.pak").is_file())

    def test_presence_tags(self):
        tags = classify_presence(
            has_own_archive=True,
            vortex_stage_exists=True,
            work_extracted=True,
            installed_in_game=False,
        )
        self.assertIn(PRESENCE_ARCHIVED, tags)
        self.assertIn(PRESENCE_VORTEX, tags)
        self.assertIn(PRESENCE_WORK, tags)

    def test_physical_estimate_hardlink(self):
        m = _mod("HL-8-1", self.stage, {"h.pak": b"HHHH"})
        src = Path(m.stage_path) / "h.pak"
        dst = self.mods_dst / "h.pak"
        try:
            import os

            os.link(src, dst)
        except OSError:
            self.skipTest("hardlink no soportado")
        phys, logical, shared = estimate_physical_bytes(Path(m.stage_path))
        self.assertIsNotNone(phys)
        self.assertGreaterEqual(shared, 1)
        self.assertEqual(phys, 0)

    def test_cancel_restore_batch(self):
        paths = []
        for i in range(3):
            _, r = self._archive_mod(f"K{i}-9-1", {f"k{i}.pak": b"K"})
            paths.append(Path(r.published_path))
        flag = {"n": 0}

        def cancel():
            flag["n"] += 1
            return flag["n"] > 1

        work = self.data / "work_library"
        results, idx = restore_many_to_work(
            game_id="g1", archives=paths, work_root=work, cancel=cancel
        )
        self.assertLess(sum(1 for r in results if r.ok), 3)


if __name__ == "__main__":
    unittest.main()
