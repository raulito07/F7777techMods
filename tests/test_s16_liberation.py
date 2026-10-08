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

S16 — liberación controlada (solo sandbox; sin borrado de staging real).
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

from app.core.apply import ApplyContext  # noqa: E402
from app.core.archive_catalog import build_catalog  # noqa: E402
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.liberation_independence import (  # noqa: E402
    verify_independence_from_archive,
)
from app.core.liberation_plan import (  # noqa: E402
    CAT_BLOQUEADO,
    CAT_LIBERABLE,
    CAT_PENDIENTE_VORTEX,
    simulate_staging_liberation,
)
from app.core.own_archive import create_own_archive  # noqa: E402
from app.core.vortex_liberation import (  # noqa: E402
    STRATEGY_COMPARISON,
    VortexStagingRisk,
    assess_vortex_for_mod,
    format_vortex_research_summary,
)
from app.core.vortex_sync import (  # noqa: E402
    VortexEnableSnapshot,
    VortexReliability,
)
from app.core.work_library import load_index, restore_archive_to_work  # noqa: E402


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
        on_disk=kw.get("on_disk", False),
        stage_path=str(d),
        usar=kw.get("usar", False),
        pak_elegido=kw.get("pak_elegido", paks[0] if len(paks) == 1 else ""),
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


class S16LiberationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.stage = self.base / "stage"
        self.arch = self.base / "arch"
        self.work = self.base / "work"
        self.roaming = self.base / "vortex_roaming"
        self.stage.mkdir()
        self.arch.mkdir()
        self.work.mkdir()
        self.roaming.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def _own(self, folder: str, files: dict[str, bytes], **kw):
        m = _mod(folder, self.stage, files, **kw)
        cr = create_own_archive(
            game_id="g1", mod=m, stage_root=self.stage, dest_dir=self.arch
        )
        self.assertTrue(cr.ok, cr.errors)
        cat = build_catalog(
            game_id="g1", mods=[m], downloads_dir=None, stage_dir=self.stage
        )
        cat.mods[0].own_archive_path = cr.published_path
        cat.mods[0].recoverable = True
        cat.mods[0].package_kind = "ARCHIVO_PROPIO"
        return m, cr, cat

    def test_recoverable_archived_pending_vortex(self):
        m, _, cat = self._own("Rec-1-1", {"a.pak": b"A"})
        sim = simulate_staging_liberation(cat, [m], mods_dir=self.base / "gmods")
        self.assertEqual(sim.rows[0].category, CAT_PENDIENTE_VORTEX)
        self.assertFalse(sim.rows[0].execution_available)
        self.assertTrue(sim.rows[0].blocked)
        self.assertTrue((Path(m.stage_path) / "a.pak").is_file())

    def test_corrupt_own_archive_blocked(self):
        m, cr, cat = self._own("Bad-2-1", {"b.pak": b"B"})
        Path(cr.published_path).write_bytes(b"not-a-zip")
        sim = simulate_staging_liberation(cat, [m])
        self.assertEqual(sim.rows[0].category, CAT_BLOQUEADO)
        self.assertFalse(sim.rows[0].archived_verified)

    def test_missing_zip_blocked(self):
        m, cr, cat = self._own("Miss-3-1", {"c.pak": b"C"})
        Path(cr.published_path).unlink()
        sim = simulate_staging_liberation(cat, [m])
        self.assertEqual(sim.rows[0].category, CAT_BLOQUEADO)

    def test_hardlink_blocks(self):
        m, _, cat = self._own("HL-4-1", {"h.pak": b"HHHH"})
        mods_dst = self.base / "gmods"
        mods_dst.mkdir()
        src = Path(m.stage_path) / "h.pak"
        try:
            import os

            os.link(src, mods_dst / "h.pak")
        except OSError:
            self.skipTest("hardlink no soportado")
        sim = simulate_staging_liberation(cat, [m], mods_dir=mods_dst)
        self.assertEqual(sim.rows[0].category, CAT_BLOQUEADO)
        self.assertGreater(sim.rows[0].hardlinks_to_game, 0)

    def test_vortex_known_enabled(self):
        m, _, cat = self._own("Vz-5-1", {"v.pak": b"V"})
        snap = VortexEnableSnapshot(
            reliability=VortexReliability.HISTORICAL_BACKUP,
            enabled_map={m.folder: True},
            live_state_present=True,
        )
        a = assess_vortex_for_mod(m.folder, staging_exists=True, snap=snap)
        self.assertEqual(a.risk, VortexStagingRisk.REGISTERED_ENABLED)
        sim = simulate_staging_liberation(cat, [m], vortex_snap=snap)
        self.assertEqual(sim.rows[0].category, CAT_PENDIENTE_VORTEX)
        self.assertEqual(sim.rows[0].recommended_method, "VORTEX_UI_UNINSTALL")

    def test_vortex_unknown(self):
        m, _, cat = self._own("Unk-6-1", {"u.pak": b"U"})
        snap = VortexEnableSnapshot(
            reliability=VortexReliability.UNKNOWN,
            enabled_map={},
            live_state_present=False,
        )
        sim = simulate_staging_liberation(cat, [m], vortex_snap=snap)
        self.assertEqual(sim.rows[0].category, CAT_PENDIENTE_VORTEX)

    def test_game_uninstalled_still_pending(self):
        m, _, cat = self._own("Gui-7-1", {"g.pak": b"G"})
        sim = simulate_staging_liberation(cat, [m], game_installed=False)
        self.assertEqual(sim.rows[0].category, CAT_PENDIENTE_VORTEX)
        self.assertIn("juego", sim.rows[0].vortex_risk)

    def test_mod_still_needed_blocked(self):
        m, _, cat = self._own("Need-8-1", {"n.pak": b"N"}, usar=True)
        sim = simulate_staging_liberation(cat, [m])
        self.assertEqual(sim.rows[0].category, CAT_BLOQUEADO)
        self.assertTrue(any("activo" in r for r in sim.rows[0].block_reasons))

    def test_liberation_execution_always_blocked(self):
        m, _, cat = self._own("Exe-9-1", {"e.pak": b"E"})
        sim = simulate_staging_liberation(cat, [m])
        self.assertFalse(sim.execution_authorized)
        self.assertTrue(all(not r.execution_available for r in sim.rows))
        self.assertTrue(all(r.blocked for r in sim.rows))

    def test_independence_without_vortex_staging(self):
        m, cr, _ = self._own("Ind-10-1", {"i.pak": b"I"})
        ctx = _ctx(self.base / "indep")
        settings = ConflictSettings(
            adapter_id="ue4_paks_mods",
            game_id="g1",
            work_root=self.work,
            destination_verified=True,
            install_mode="COPY",
        )
        r = verify_independence_from_archive(
            game_id="g1",
            archive_path=Path(cr.published_path),
            work_root=self.work,
            ctx=ctx,
            settings=settings,
            stage_root=self.stage,
        )
        self.assertTrue(r.ok, r.errors)
        self.assertTrue(r.restore_ok)
        self.assertTrue(r.plan_ok)
        self.assertFalse(r.uses_vortex_staging)
        # staging Vortex intacto
        self.assertTrue((Path(m.stage_path) / "i.pak").is_file())

    def test_space_freed_when_no_staging(self):
        m, cr, cat = self._own("Free-11-1", {"f.pak": b"F"})
        # quitar staging (simula Uninstall Vortex ya hecho)
        import shutil

        shutil.rmtree(Path(m.stage_path))
        m.stage_path = str(self.stage / m.folder)  # ruta ausente
        cat.mods[0].staging_logical_size = 0
        sim = simulate_staging_liberation(
            cat, [m], independence_by_folder={m.folder: True}
        )
        self.assertEqual(sim.rows[0].category, CAT_LIBERABLE)
        self.assertTrue(sim.rows[0].space_freed)
        self.assertFalse(sim.rows[0].execution_available)

    def test_zip_alone_not_liberable_with_staging(self):
        m, _, cat = self._own("OnlyZip-12-1", {"z.pak": b"Z"})
        sim = simulate_staging_liberation(
            cat, [m], independence_by_folder={m.folder: True}
        )
        # ZIP + independencia OK pero staging Vortex → PENDIENTE, no LIBERABLE
        self.assertEqual(sim.rows[0].category, CAT_PENDIENTE_VORTEX)
        self.assertNotEqual(sim.rows[0].category, CAT_LIBERABLE)

    def test_research_and_strategies(self):
        text = format_vortex_research_summary()
        self.assertIn("state.v2", text)
        self.assertTrue(any(s["id"] == "DIRECT_LEVELDB" for s in STRATEGY_COMPARISON))
        self.assertIn("Prohibido", STRATEGY_COMPARISON[-1]["automatable_here"])

    def test_sim_to_dict_no_execute(self):
        m, _, cat = self._own("Json-13-1", {"j.pak": b"J"})
        sim = simulate_staging_liberation(cat, [m])
        d = sim.to_dict()
        self.assertEqual(d["liberate_staging"], "NO DISPONIBLE")
        self.assertFalse(d["execution_authorized"])
        json.dumps(d)  # serializable


if __name__ == "__main__":
    unittest.main()
