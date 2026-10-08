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

Pruebas S04 — adopción, integridad y restauración (solo temporales).
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

from app.core.apply import (  # noqa: E402
    ApplyContext,
    plan_apply,
    execute,
    load_manifest,
)
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.adoption import plan_adoption, execute_adoption  # noqa: E402
from app.core.provenance import scan_destination, Provenance, Integrity  # noqa: E402
from app.core.hash_cache import HashCache, sha256_file  # noqa: E402
from app.core.operations import (  # noqa: E402
    list_operations,
    plan_restore,
    execute_restore,
)
from app.core.games import GameRecord, game_paths_for, add_game, GamesRegistry  # noqa: E402


def _mod(folder: str, stage: Path, pak: str = "a.pak") -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=[pak],
        multi=False,
        on_disk=False,
        stage_path=str(stage),
        usar=True,
        pak_elegido=pak,
    )


class S04Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.mods = self.base / "mods"
        self.data = self.base / "data"
        self.stage = self.base / "stage"
        self.mods.mkdir()
        self.data.mkdir()
        self.stage.mkdir()
        self.ctx = ApplyContext(
            mods=self.mods,
            deploy=self.mods / "vortex.deployment.json",
            loadout_marker=self.mods / "_manual_loadout.json",
            manifest=self.data / "managed_manifest.json",
            backups=self.data / "backups",
            stage=self.stage,
            data_dir=self.data,
        )
        self.settings = ConflictSettings(
            hash_cache_path=self.data / "hash_cache.json",
            adapter_id="generic_folder",
        )

    def tearDown(self):
        self._td.cleanup()

    def _stage(self, folder: str, files: dict[str, bytes]) -> Path:
        d = self.stage / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return d

    def test_valid_adoption(self):
        content = b"ADOPT-ME"
        self._stage("ModA", {"x.pak": content})
        (self.mods / "x.pak").write_bytes(content)
        plan = plan_adoption("x.pak", self.ctx, hash_cache_path=self.data / "hash_cache.json")
        self.assertTrue(plan.ok, plan.errors)
        before = list(self.mods.iterdir())
        execute_adoption(plan, self.ctx, confirm=True)
        after = list(self.mods.iterdir())
        self.assertEqual(len(before), len(after))
        man = load_manifest(self.ctx)
        self.assertIn("x.pak", man)
        self.assertEqual(man["x.pak"]["origin"], "adopt")
        self.assertEqual(man["x.pak"]["sha256"], sha256_file(self.mods / "x.pak"))

    def test_ambiguous_adoption_blocked(self):
        content = b"SAME"
        self._stage("ModA", {"x.pak": content})
        self._stage("ModB", {"x.pak": content})
        (self.mods / "x.pak").write_bytes(content)
        plan = plan_adoption("x.pak", self.ctx, hash_cache_path=self.data / "hash_cache.json")
        self.assertFalse(plan.ok)
        self.assertTrue(any("ambigu" in e.lower() for e in plan.errors))

    def test_vortex_adoption_blocked(self):
        content = b"VX"
        self._stage("ModA", {"x.pak": content})
        (self.mods / "x.pak").write_bytes(content)
        self.ctx.deploy.write_text(
            json.dumps({"files": [{"relPath": "x.pak", "source": "vortex/ModA/x.pak"}]}),
            encoding="utf-8",
        )
        plan = plan_adoption("x.pak", self.ctx, hash_cache_path=self.data / "hash_cache.json")
        self.assertFalse(plan.ok)
        self.assertTrue(any("Vortex" in e or "VORTEX" in e for e in plan.errors))

    def test_cancel_adoption_no_changes(self):
        content = b"C"
        self._stage("ModA", {"x.pak": content})
        (self.mods / "x.pak").write_bytes(content)
        plan = plan_adoption("x.pak", self.ctx, hash_cache_path=self.data / "hash_cache.json")
        with self.assertRaises(Exception):
            execute_adoption(plan, self.ctx, confirm=False)
        self.assertEqual(load_manifest(self.ctx), {})

    def test_same_size_different_hash_update(self):
        s = self._stage("ModA", {"a.pak": b"AAAA"})
        execute(plan_apply([_mod("ModA", s, "a.pak")], self.ctx, self.settings), self.ctx, mods=[_mod("ModA", s, "a.pak")])
        # mismo tamaño, distinto contenido
        (s / "a.pak").write_bytes(b"BBBB")
        plan = plan_apply([_mod("ModA", s, "a.pak")], self.ctx, self.settings)
        self.assertIn("a.pak", plan.to_update)

    def test_hash_cache_invalidation(self):
        p = self.mods / "t.bin"
        p.write_bytes(b"ONE")
        cache = HashCache(self.data / "hash_cache.json")
        h1 = cache.get(p)
        cache.save()
        p.write_bytes(b"TWO!")
        cache2 = HashCache(self.data / "hash_cache.json")
        h2 = cache2.get(p)
        self.assertNotEqual(h1, h2)

    def test_managed_external_drift_blocks(self):
        s = self._stage("ModA", {"a.pak": b"ORIG"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        # tercero modifica destino sin tocar staging
        (self.mods / "a.pak").write_bytes(b"HACK")
        (s / "a.pak").write_bytes(b"NEW1")  # staging también distinto
        plan = plan_apply([m], self.ctx, self.settings)
        self.assertTrue(any("MODIFICADO_EXTERNO" in e for e in plan.errors))
        self.assertNotIn("a.pak", plan.to_update)

    def test_shared_deactivate_keeps_needed(self):
        # Dos mods, prioridad B gana x.pak; desactivar A no quita x.pak
        sa = self._stage("A", {"x.pak": b"AAA"})
        sb = self._stage("B", {"x.pak": b"BBB"})
        settings = ConflictSettings(
            priorities={"A": 1, "B": 5},
            hash_cache_path=self.data / "hash_cache.json",
        )
        mods = [_mod("A", sa, "x.pak"), _mod("B", sb, "x.pak")]
        execute(plan_apply(mods, self.ctx, settings), self.ctx, mods=mods)
        self.assertEqual((self.mods / "x.pak").read_bytes(), b"BBB")
        mods[0].usar = False
        plan = plan_apply(mods, self.ctx, settings)
        self.assertNotIn("x.pak", plan.to_remove)
        execute(plan, self.ctx, mods=mods)
        self.assertTrue((self.mods / "x.pak").exists())

    def test_remove_only_managed(self):
        foreign = self.mods / "foreign.pak"
        foreign.write_bytes(b"F")
        s = self._stage("ModA", {"a.pak": b"A"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        m.usar = False
        plan = plan_apply([m], self.ctx, self.settings)
        self.assertIn("a.pak", plan.to_remove)
        self.assertNotIn("foreign.pak", plan.to_remove)
        execute(plan, self.ctx, mods=[m])
        self.assertFalse((self.mods / "a.pak").exists())
        self.assertTrue(foreign.exists())

    def test_restore_operation(self):
        s = self._stage("ModA", {"a.pak": b"A1"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        ops = list_operations(self.data)
        self.assertTrue(ops)
        op0 = ops[0]
        # segunda apply que actualiza
        (s / "a.pak").write_bytes(b"A2")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"A2")
        # restaurar primera operación (backup de la segunda contiene A1 al actualizar)
        # Usar la operación de update (segunda) para volver a A1
        ops2 = list_operations(self.data)
        update_op = next(o for o in ops2 if o.updated or o.added)
        # El backup de la 2ª apply guardó A1 antes de escribir A2
        plan = plan_restore(self.data, self.ctx, update_op.id, hash_cache_path=self.data / "hash_cache.json")
        self.assertTrue(plan.ok, plan.errors)
        execute_restore(
            plan,
            self.ctx,
            self.data,
            confirm=True,
            hash_cache_path=self.data / "hash_cache.json",
        )
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"A1")

    def test_restore_blocked_by_external(self):
        s = self._stage("ModA", {"a.pak": b"A1"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        (s / "a.pak").write_bytes(b"A2")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        ops = list_operations(self.data)
        update_op = next(o for o in ops if "a.pak" in o.updated or o.updated)
        # Simular archivo externo en otra ruta que el restore no toca — en su lugar
        # alterar post-hash: modificar a.pak a algo que no es A2 ni A1 esperado
        (self.mods / "a.pak").write_bytes(b"XX")
        # post_hashes de update_op es A2; actual XX → bloqueo
        plan = plan_restore(self.data, self.ctx, update_op.id, hash_cache_path=self.data / "hash_cache.json")
        self.assertFalse(plan.ok)

    def test_game_isolation(self):
        reg = GamesRegistry()
        app_data = self.base / "appdata"
        app_data.mkdir()
        ma = self.base / "ga" / "mods"
        mb = self.base / "gb" / "mods"
        ma.mkdir(parents=True)
        mb.mkdir(parents=True)
        a = GameRecord(
            id="ga",
            name="GA",
            mods_dir=str(ma),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="ga",
        )
        b = GameRecord(
            id="gb",
            name="GB",
            mods_dir=str(mb),
            stage_dir=str(self.stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="gb",
        )
        add_game(reg, a)
        add_game(reg, b)
        pa = game_paths_for(a, app_data=app_data)
        pb = game_paths_for(b, app_data=app_data)
        self.assertNotEqual(pa.manifest if False else pa.data_dir, pb.data_dir)
        self.assertNotEqual(pa.apply_context().manifest, pb.apply_context().manifest)

    def test_provenance_classification(self):
        (self.mods / "ext.pak").write_bytes(b"E")
        inv = scan_destination(
            self.mods,
            manifest={},
            deploy_path=self.ctx.deploy,
            compute_hashes=False,
        )
        self.assertEqual(inv.files[0].provenance, Provenance.EXTERNO)

    def test_manifest_v1_readable(self):
        self.ctx.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": {
                        "old.pak": {
                            "mod_folder": "X",
                            "mod_name": "X",
                            "source": "s",
                            "installed_at": "t",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        man = load_manifest(self.ctx)
        self.assertIn("old.pak", man)


if __name__ == "__main__":
    unittest.main()
