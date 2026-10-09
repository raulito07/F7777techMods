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

Pruebas S03 — conflictos de archivos y prioridades (solo temporales).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import ApplyContext, plan_apply, execute, load_manifest  # noqa: E402
from app.core.conflict_engine import (  # noqa: E402
    ConflictKind,
    ConflictSettings,
    analyze_file_conflicts,
    semantic_enabled,
)
from app.core.conflicts import evaluate  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.priority_store import (  # noqa: E402
    save_priorities,
    load_priorities,
    save_resolutions,
    load_resolutions,
    set_resolution,
)
from app.core.games import GameRecord, game_paths_for, add_game, GamesRegistry  # noqa: E402


def _mod(folder: str, stage: Path, pak: str, *, usar=True, multi=False, chosen="") -> ModEntry:
    paks = [pak] if not multi else [pak, "other.pak"]
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=multi,
        on_disk=False,
        stage_path=str(stage),
        usar=usar,
        pak_elegido=chosen or (pak if not multi else ""),
    )


def _stage(base: Path, folder: str, files: dict[str, bytes]) -> Path:
    d = base / "stage" / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return d


class ConflictsS03Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.mods = self.base / "mods"
        self.data = self.base / "data"
        self.mods.mkdir()
        self.data.mkdir()
        self.ctx = ApplyContext(
            mods=self.mods,
            deploy=self.mods / "vortex.deployment.json",
            loadout_marker=self.mods / "_manual_loadout.json",
            manifest=self.data / "managed_manifest.json",
            backups=self.data / "backups",
            stage=self.base / "stage",
        )
        self.settings = ConflictSettings(
            hash_cache_path=self.data / "hash_cache.json",
            adapter_id="generic_folder",
        )

    def tearDown(self):
        self._td.cleanup()

    def test_identical_duplicate_resolves(self):
        s1 = _stage(self.base, "A", {"x.pak": b"SAME"})
        s2 = _stage(self.base, "B", {"x.pak": b"SAME"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        plan = plan_apply(mods, self.ctx, self.settings)
        self.assertEqual(plan.file_unresolved, 0)
        self.assertFalse(plan.errors)
        execute(plan, self.ctx, mods=mods)
        self.assertEqual((self.mods / "x.pak").read_bytes(), b"SAME")

    def test_different_files_block_without_priority(self):
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        plan = plan_apply(mods, self.ctx, self.settings)
        self.assertGreaterEqual(plan.file_unresolved, 1)
        self.assertTrue(any("CONFLICTO DE ARCHIVOS" in e for e in plan.errors))
        with self.assertRaises(Exception):
            execute(plan, self.ctx, mods=mods)

    def test_same_name_different_paths_ok(self):
        s1 = _stage(self.base, "A", {"sub/a.txt": b"1", "a.pak": b"P"})
        s2 = _stage(self.base, "B", {"other/a.txt": b"2", "b.pak": b"Q"})
        mods = [_mod("A", s1, "a.pak"), _mod("B", s2, "b.pak")]
        plan = plan_apply(mods, self.ctx, self.settings)
        self.assertEqual(plan.file_unresolved, 0)
        execute(plan, self.ctx, mods=mods)
        self.assertTrue((self.mods / "sub" / "a.txt").exists())
        self.assertTrue((self.mods / "other" / "a.txt").exists())

    def test_case_collision_windows(self):
        if os.name != "nt":
            self.skipTest("Solo Windows")
        s1 = _stage(self.base, "A", {"Cloud.pak": b"A"})
        s2 = _stage(self.base, "B", {"cloud.pak": b"B"})
        mods = [_mod("A", s1, "Cloud.pak"), _mod("B", s2, "cloud.pak")]
        plan = plan_apply(mods, self.ctx, self.settings)
        self.assertGreaterEqual(plan.file_unresolved, 1)

    def test_higher_priority_wins(self):
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        settings = ConflictSettings(
            priorities={"A": 1, "B": 10},
            hash_cache_path=self.data / "hash_cache.json",
            adapter_id="generic_folder",
        )
        plan = plan_apply(mods, self.ctx, settings)
        self.assertEqual(plan.file_unresolved, 0)
        self.assertEqual(plan.desired_meta["x.pak"].mod_folder, "B")
        execute(plan, self.ctx, mods=mods)
        self.assertEqual((self.mods / "x.pak").read_bytes(), b"BBB")

    def test_equal_priority_blocks(self):
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        settings = ConflictSettings(
            priorities={"A": 5, "B": 5},
            hash_cache_path=self.data / "hash_cache.json",
        )
        plan = plan_apply(mods, self.ctx, settings)
        self.assertGreaterEqual(plan.file_unresolved, 1)

    def test_missing_priority_blocks(self):
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        settings = ConflictSettings(
            priorities={"A": 5},  # B sin prioridad
            hash_cache_path=self.data / "hash_cache.json",
        )
        plan = plan_apply(mods, self.ctx, settings)
        self.assertGreaterEqual(plan.file_unresolved, 1)

    def test_foreign_blocks_even_with_priority(self):
        (self.mods / "x.pak").write_bytes(b"FOREIGN")
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        mods = [_mod("A", s1, "x.pak")]
        settings = ConflictSettings(
            priorities={"A": 99},
            hash_cache_path=self.data / "hash_cache.json",
        )
        plan = plan_apply(mods, self.ctx, settings)
        self.assertTrue(any("AJENO" in e for e in plan.errors))
        with self.assertRaises(Exception):
            execute(plan, self.ctx, mods=mods)
        self.assertEqual((self.mods / "x.pak").read_bytes(), b"FOREIGN")

    def test_variant_blocks(self):
        s1 = _stage(self.base, "A", {"a.pak": b"A", "b.pak": b"B"})
        mods = [_mod("A", s1, "a.pak", multi=True, chosen="")]
        plan = plan_apply(mods, self.ctx, self.settings)
        self.assertTrue(
            any(
                ("variante" in e.lower() or "componente" in e.lower())
                for e in plan.errors
            )
        )

    def test_resolution_persists(self):
        path = self.data / "conflict_resolutions.json"
        res = {}
        set_resolution(res, "x.pak", "B", mode="manual")
        save_resolutions(path, res)
        loaded = load_resolutions(path)
        self.assertEqual(loaded["x.pak"]["winner_folder"], "B")

        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        settings = ConflictSettings(
            resolutions=loaded,
            hash_cache_path=self.data / "hash_cache.json",
        )
        plan = plan_apply(mods, self.ctx, settings)
        self.assertEqual(plan.file_unresolved, 0)
        self.assertEqual(plan.desired_meta["x.pak"].mod_folder, "B")

    def test_game_isolation_priorities(self):
        reg = GamesRegistry()
        app_data = self.base / "appdata"
        app_data.mkdir()
        mods_a = self.base / "ga" / "mods"
        mods_b = self.base / "gb" / "mods"
        mods_a.mkdir(parents=True)
        mods_b.mkdir(parents=True)
        a = GameRecord(
            id="ga",
            name="GA",
            mods_dir=str(mods_a),
            stage_dir=str(self.base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="ga",
        )
        b = GameRecord(
            id="gb",
            name="GB",
            mods_dir=str(mods_b),
            stage_dir=str(self.base / "stage"),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="gb",
        )
        add_game(reg, a)
        add_game(reg, b)
        pa = game_paths_for(a, app_data=app_data)
        pb = game_paths_for(b, app_data=app_data)
        pa.data_dir.mkdir(parents=True)
        pb.data_dir.mkdir(parents=True)
        save_priorities(pa.priorities_json, {"ModX": 9})
        save_priorities(pb.priorities_json, {"ModX": 1})
        self.assertEqual(load_priorities(pa.priorities_json)["ModX"], 9)
        self.assertEqual(load_priorities(pb.priorities_json)["ModX"], 1)
        self.assertNotEqual(pa.priorities_json, pb.priorities_json)

    def test_generic_no_semantic_slots(self):
        self.assertFalse(semantic_enabled("generic_folder"))
        self.assertTrue(semantic_enabled("ue4_paks_mods"))
        # Tifa-like names must not conflict on generic
        s1 = _stage(self.base, "tifa undressed-1", {"a.pak": b"A"})
        s2 = _stage(self.base, "tifa hyper hd-2", {"b.pak": b"B"})
        mods = [
            _mod("tifa undressed-1", s1, "a.pak"),
            _mod("tifa hyper hd-2", s2, "b.pak"),
        ]
        _, n = evaluate(mods, semantic=False)
        self.assertEqual(n, 0)
        for m in mods:
            self.assertEqual(m.slots, [])

    def test_packaged_external_note(self):
        s1 = _stage(self.base, "A", {"x.pak": b"AAA"})
        s2 = _stage(self.base, "B", {"x.pak": b"BBB"})
        mods = [_mod("A", s1, "x.pak"), _mod("B", s2, "x.pak")]
        analysis = analyze_file_conflicts(mods, self.settings)
        fc = next(c for c in analysis.file_conflicts if not c.resolved)
        self.assertTrue(any(o.packaged_external for o in fc.offers))
        self.assertIn("no se analizó", fc.note.lower())

    def test_s01_foreign_still_protected(self):
        foreign = self.mods / "keep.pak"
        foreign.write_bytes(b"KEEP")
        s1 = _stage(self.base, "A", {"a.pak": b"A"})
        plan = plan_apply([_mod("A", s1, "a.pak")], self.ctx, self.settings)
        execute(plan, self.ctx, mods=[_mod("A", s1, "a.pak")])
        self.assertEqual(foreign.read_bytes(), b"KEEP")

    def test_hash_cache_avoids_recompute(self):
        s1 = _stage(self.base, "A", {"x.pak": b"DATA" * 1000})
        mods = [_mod("A", s1, "x.pak"), _mod("B", _stage(self.base, "B", {"x.pak": b"DATA" * 1000}), "x.pak")]
        t0 = time.perf_counter()
        plan_apply(mods, self.ctx, self.settings)
        t1 = time.perf_counter()
        plan_apply(mods, self.ctx, self.settings)
        t2 = time.perf_counter()
        # Segunda pasada no debe ser mucho más lenta; solo medimos que termina
        self.assertLess(t2 - t1, 5.0)
        self.assertTrue((self.data / "hash_cache.json").exists())
        # Reportar tiempos (observación)
        self._perf = (t1 - t0, t2 - t1)


if __name__ == "__main__":
    unittest.main()
