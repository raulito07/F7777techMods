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

S15 — instalación desde WORK_LIBRARY y ciclo E2E (solo sandbox temporal).
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

from app.core.apply import (  # noqa: E402
    ApplyContext,
    ApplyError,
    execute,
    load_manifest,
    plan_apply,
)
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.mod_source import (  # noqa: E402
    SOURCE_STAGING_VORTEX,
    SOURCE_WORK_LIBRARY,
    validate_mods_for_apply,
)
from app.core.own_archive import create_own_archive  # noqa: E402
from app.core.work_cycle import run_sandbox_install_cycle  # noqa: E402
from app.core.work_library import (  # noqa: E402
    cleanup_work_library,
    load_index,
    restore_archive_to_work,
    work_record_to_mod_entry,
)


def _mod(folder: str, stage: Path, files: dict[str, bytes], **kw) -> ModEntry:
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
        usar=kw.get("usar", True),
        pak_elegido=kw.get("pak_elegido", paks[0] if len(paks) == 1 else ""),
        source_kind=kw.get("source_kind", SOURCE_STAGING_VORTEX),
    )


def _ctx(base: Path) -> ApplyContext:
    mods = base / "mods"
    data = base / "data"
    mods.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    return ApplyContext(
        mods=mods,
        deploy=mods / "vortex.deployment.json",
        loadout_marker=mods / "_manual_loadout.json",
        manifest=data / "managed_manifest.json",
        backups=data / "backups",
        stage=base / "stage",
        data_dir=data,
    )


class S15WorkInstallTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.arch = self.base / "arch"
        self.work = self.base / "work"
        self.stage.mkdir()
        self.arch.mkdir()
        self.work.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def test_e2e_full_cycle(self):
        m = _mod("E2E-1-1", self.stage, {"e.pak": b"E2EDATA", "readme.txt": b"r"})
        ctx = _ctx(self.base)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="g1",
            work_root=self.work,
            stage_root=self.stage,
            destination_verified=True,
            install_mode="COPY",
        )
        result = run_sandbox_install_cycle(
            game_id="g1",
            stage_mod=m,
            stage_root=self.stage,
            archive_dir=self.arch,
            work_root=self.work,
            ctx=ctx,
            settings=settings,
        )
        self.assertTrue(result.ok, result.errors)
        names = [s.name for s in result.steps if s.ok]
        for need in (
            "zip_propio",
            "restore_work",
            "apply",
            "deactivate",
            "reinstall",
        ):
            self.assertIn(need, names)
        # staging Vortex intacto
        self.assertTrue((Path(m.stage_path) / "e.pak").is_file())
        # instalado en sandbox mods
        self.assertTrue((ctx.mods / "e.pak").is_file())

    def test_variant_plan(self):
        m = _mod(
            "Var-2-1",
            self.stage,
            {"A.pak": b"A", "B.pak": b"B"},
            pak_elegido="B.pak",
            multi=True,
        )
        cr = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(cr.ok, cr.errors)
        idx = load_index(self.work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            idx=idx,
        )
        self.assertTrue(rr.ok)
        idx = load_index(self.work, game_id="g1")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
        wm.pak_elegido = "B.pak"
        ctx = _ctx(self.base)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="g1",
            work_root=self.work,
            destination_verified=True,
        )
        plan = plan_apply([wm], ctx=ctx, settings=settings)
        self.assertEqual(plan.conflicts, 0)
        execute(plan, ctx, mods=[wm])
        self.assertTrue((ctx.mods / "B.pak").is_file())
        self.assertFalse((ctx.mods / "A.pak").is_file())

    def test_zip_modified_blocks(self):
        m = _mod("Zmod-3-1", self.stage, {"z.pak": b"Z"})
        cr = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        idx = load_index(self.work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            idx=idx,
        )
        self.assertTrue(rr.ok)
        idx = load_index(self.work, game_id="g1")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
        # alterar ZIP
        Path(cr.published_path).write_bytes(b"tampered-zip-content!!!!")
        v = validate_mods_for_apply(
            [wm], game_id="g1", stage_root=self.stage, work_root=self.work
        )
        self.assertFalse(v.ok)
        self.assertTrue(
            any(
                "modificado" in e.lower() or "inválido" in e.lower() or "invalido" in e.lower()
                for e in v.errors
            )
        )

    def test_mixed_source_path_blocked(self):
        m = _mod("Mix-4-1", self.stage, {"m.pak": b"M"})
        m.source_kind = SOURCE_WORK_LIBRARY
        m.archive_path = str(self.arch / "missing.zip")
        v = validate_mods_for_apply(
            [m], game_id="g1", stage_root=self.stage, work_root=self.work
        )
        self.assertFalse(v.ok)

    def test_hardlink_cleanup_retains(self):
        m = _mod("HL-5-1", self.stage, {"h.pak": b"HHHH"})
        cr = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        idx = load_index(self.work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            idx=idx,
        )
        self.assertTrue(rr.ok)
        idx = load_index(self.work, game_id="g1")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
        ctx = _ctx(self.base)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="g1",
            work_root=self.work,
            destination_verified=True,
            install_mode="HARDLINK",
        )
        plan = plan_apply([wm], ctx=ctx, settings=settings)
        # puede caer a COPY si no elegible; forzar hardlink manual
        src = Path(wm.stage_path) / "h.pak"
        dst = ctx.mods / "h.pak"
        try:
            os.link(src, dst)
        except OSError:
            self.skipTest("hardlink no disponible")
        removed, notes = cleanup_work_library(
            idx, only_unused=True, mods_dir=ctx.mods
        )
        self.assertEqual(removed, 0)
        self.assertTrue(any("hardlink" in n.lower() for n in notes))

    def test_game_isolation_work_install(self):
        m = _mod("Iso-6-1", self.stage, {"i.pak": b"I"})
        cr = create_own_archive(
            game_id="rebirth", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        idx = load_index(self.work, game_id="rebirth")
        rr = restore_archive_to_work(
            game_id="rebirth",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            idx=idx,
        )
        self.assertTrue(rr.ok)
        idx = load_index(self.work, game_id="rebirth")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
        v = validate_mods_for_apply(
            [wm], game_id="stellar", stage_root=self.stage, work_root=self.work
        )
        self.assertFalse(v.ok)

    def test_rollback_on_copy_fail(self):
        m = _mod(
            "Rb-7-1",
            self.stage,
            {"r.pak": b"R", "extra.bin": b"X" * 8},
            pak_elegido="r.pak",
        )
        cr = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        idx = load_index(self.work, game_id="g1")
        rr = restore_archive_to_work(
            game_id="g1",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            idx=idx,
        )
        idx = load_index(self.work, game_id="g1")
        wm = work_record_to_mod_entry(idx.mods[rr.mod_id], usar=True)
        wm.pak_elegido = "r.pak"
        ctx = _ctx(self.base)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="g1",
            work_root=self.work,
            destination_verified=True,
            install_mode="COPY",
        )
        plan = plan_apply([wm], ctx=ctx, settings=settings)
        self.assertTrue(plan.to_add, plan.errors)
        # romper origen del pak tras plan
        (Path(wm.stage_path) / "r.pak").unlink()
        with self.assertRaises(ApplyError):
            execute(plan, ctx, mods=[wm])
        man = load_manifest(ctx)
        self.assertTrue(isinstance(man, dict))
        self.assertFalse((ctx.mods / "r.pak").is_file())

    def test_staging_vortex_still_works(self):
        """Regresión: staging Vortex sin game_id en settings sigue Apply OK."""
        m = _mod("Stg-8-1", self.stage, {"t.pak": b"T"})
        ctx = _ctx(self.base)
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            destination_verified=True,
            install_mode="COPY",
        )
        plan = plan_apply([m], ctx=ctx, settings=settings)
        execute(plan, ctx, mods=[m])
        self.assertTrue((ctx.mods / "t.pak").is_file())


if __name__ == "__main__":
    unittest.main()
