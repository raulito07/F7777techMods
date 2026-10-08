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

Pruebas S05 — consolidación, recuperación e integración (solo temporales).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import (  # noqa: E402
    ApplyContext,
    ApplyError,
    plan_apply,
    execute,
    load_manifest,
    recover_incomplete_transactions,
    list_incomplete_backups,
    _write_manifest,
)
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.inventory import ModEntry, scan_staging  # noqa: E402
from app.core.adoption import plan_adoption, execute_adoption  # noqa: E402
from app.core.provenance import scan_destination, Provenance  # noqa: E402
from app.core.operations import (  # noqa: E402
    list_operations,
    plan_restore,
    execute_restore,
)
from app.core.games import (  # noqa: E402
    GameRecord,
    GamesRegistry,
    add_game,
    game_paths_for,
    set_active_game,
)
from app.core.priority_store import save_priorities, save_resolutions  # noqa: E402
from app.core.hash_cache import sha256_file  # noqa: E402
import app.core.apply as apply_mod  # noqa: E402


def _mod(folder: str, stage: Path, pak: str = "a.pak", *, usar: bool = True) -> ModEntry:
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=[pak],
        multi=False,
        on_disk=False,
        stage_path=str(stage),
        usar=usar,
        pak_elegido=pak,
    )


class S05TempCase(unittest.TestCase):
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


class TestRestoreFullManifest(S05TempCase):
    def test_restore_files_and_manifest(self):
        s = self._stage("ModA", {"a.pak": b"A1"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        man1 = load_manifest(self.ctx)
        self.assertIn("a.pak", man1)

        (s / "a.pak").write_bytes(b"A2")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"A2")
        self.assertEqual(load_manifest(self.ctx)["a.pak"]["sha256"], sha256_file(s / "a.pak"))

        ops = list_operations(self.data)
        update_op = next(o for o in ops if o.updated)
        self.assertTrue(update_op.has_pre_manifest)
        self.assertTrue((self.ctx.backups / update_op.backup_id / "pre_manifest.json").is_file())

        plan = plan_restore(self.data, self.ctx, update_op.id, hash_cache_path=self.settings.hash_cache_path)
        self.assertTrue(plan.ok, plan.errors)
        self.assertTrue(plan.will_restore_manifest)
        execute_restore(
            plan, self.ctx, self.data, confirm=True, hash_cache_path=self.settings.hash_cache_path
        )
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"A1")
        man = load_manifest(self.ctx)
        self.assertIn("a.pak", man)
        self.assertEqual(man["a.pak"]["sha256"], man1["a.pak"]["sha256"])

    def test_restore_adoption_manifest_only(self):
        content = b"ADOPT"
        dest = self.mods / "x.pak"
        dest.write_bytes(content)
        st = self._stage("ModX", {"x.pak": content})
        plan = plan_adoption("x.pak", self.ctx)
        self.assertTrue(plan.ok, plan.errors)
        execute_adoption(plan, self.ctx, confirm=True)
        self.assertIn("x.pak", load_manifest(self.ctx))

        ops = list_operations(self.data)
        adopt_op = next(o for o in ops if o.op_type == "adopt")
        rplan = plan_restore(
            self.data, self.ctx, adopt_op.id, hash_cache_path=self.settings.hash_cache_path
        )
        self.assertTrue(rplan.ok, rplan.errors)
        execute_restore(
            rplan, self.ctx, self.data, confirm=True, hash_cache_path=self.settings.hash_cache_path
        )
        self.assertNotIn("x.pak", load_manifest(self.ctx))
        self.assertTrue(dest.exists())  # adopción no toca archivos


class TestRecoveryInjected(S05TempCase):
    def test_fail_during_copy_recovers_manifest(self):
        s = self._stage("ModA", {"a.pak": b"AAA"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        man_before = load_manifest(self.ctx)

        (s / "a.pak").write_bytes(b"BBB")
        s2 = self._stage("ModB", {"b.pak": b"NEW"})
        mods = [m, _mod("ModB", s2, "b.pak")]
        plan = plan_apply(mods, self.ctx, self.settings)

        real = apply_mod._copy_replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if dst.name == "b.pak":
                raise OSError("injected copy fail")
            return real(src, dst)

        with mock.patch.object(apply_mod, "_copy_replace", side_effect=flaky):
            with self.assertRaises(ApplyError) as cm:
                execute(plan, self.ctx, mods=mods)
            self.assertTrue(cm.exception.rollback_ok)

        self.assertFalse((self.mods / "b.pak").exists())
        self.assertEqual(load_manifest(self.ctx), man_before)
        self.assertEqual(list_incomplete_backups(self.ctx), [])

    def test_fail_during_manifest_write_recovers(self):
        s = self._stage("ModA", {"a.pak": b"A1"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])
        original = (self.mods / "a.pak").read_bytes()
        man_before = load_manifest(self.ctx)

        (s / "a.pak").write_bytes(b"A2-SAME-LEN!")  # different content
        plan = plan_apply([m], self.ctx, self.settings)

        with mock.patch.object(
            apply_mod, "_write_manifest", side_effect=ApplyError("injected manifest fail")
        ):
            with self.assertRaises(ApplyError) as cm:
                execute(plan, self.ctx, mods=[m])
            self.assertTrue(cm.exception.rollback_ok)

        self.assertEqual((self.mods / "a.pak").read_bytes(), original)
        self.assertEqual(load_manifest(self.ctx)["a.pak"]["sha256"], man_before["a.pak"]["sha256"])

    def test_in_progress_recovery_idempotent(self):
        s = self._stage("ModA", {"a.pak": b"OLD"})
        m = _mod("ModA", s, "a.pak")
        execute(plan_apply([m], self.ctx, self.settings), self.ctx, mods=[m])

        # Simular interrupción: backup con IN_PROGRESS y destino alterado
        backups = list(self.ctx.backups.iterdir())
        self.assertTrue(backups)
        # Crear tx incompleta artificialmente
        (s / "a.pak").write_bytes(b"NEW")
        plan = plan_apply([m], self.ctx, self.settings)
        bdir = apply_mod._prepare_backup(plan, self.ctx)
        (self.mods / "a.pak").write_bytes(b"PARTIAL")
        # Manifiesto ya avanzado (simula fallo tras copia parcial)
        _write_manifest(plan, self.ctx, hash_cache_path=self.settings.hash_cache_path)
        (bdir / "IN_PROGRESS").write_text("applying\n", encoding="utf-8")
        meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
        meta["created_new"] = []
        meta["status"] = "copied"
        (bdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        notes1 = recover_incomplete_transactions(self.ctx)
        self.assertTrue(notes1)
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"OLD")
        self.assertEqual(list_incomplete_backups(self.ctx), [])

        # Segunda pasada: sin cambios
        snap_man = json.dumps(load_manifest(self.ctx), sort_keys=True)
        snap_bytes = (self.mods / "a.pak").read_bytes()
        notes2 = recover_incomplete_transactions(self.ctx)
        self.assertEqual(notes2, [])
        self.assertEqual(json.dumps(load_manifest(self.ctx), sort_keys=True), snap_man)
        self.assertEqual((self.mods / "a.pak").read_bytes(), snap_bytes)

    def test_fail_during_delete_recovers(self):
        s = self._stage("ModA", {"a.pak": b"AAA", "b.pak": b"BBB"})
        # Instalar ambos vía dos mods
        sa = self._stage("ModA", {"a.pak": b"AAA"})
        sb = self._stage("ModB", {"b.pak": b"BBB"})
        ma, mb = _mod("ModA", sa, "a.pak"), _mod("ModB", sb, "b.pak")
        execute(plan_apply([ma, mb], self.ctx, self.settings), self.ctx, mods=[ma, mb])

        mb.usar = False
        plan = plan_apply([ma, mb], self.ctx, self.settings)
        self.assertIn("b.pak", plan.to_remove)

        real_unlink = Path.unlink

        def flaky_unlink(self_path, *a, **kw):
            if self_path.name == "b.pak":
                raise OSError("injected unlink fail")
            return real_unlink(self_path, *a, **kw)

        with mock.patch.object(Path, "unlink", flaky_unlink):
            with self.assertRaises(ApplyError):
                execute(plan, self.ctx, mods=[ma, mb])

        self.assertTrue((self.mods / "b.pak").exists())
        self.assertIn("b.pak", load_manifest(self.ctx))


class TestMultigameIntegration(S05TempCase):
    def test_ff7r_and_generic_isolation_flow(self):
        app_data = self.base / "appdata"
        app_data.mkdir()

        # Escenario FF7R-like
        ff7_mods = self.base / "ff7" / "End" / "Content" / "Paks" / "~mods"
        ff7_stage = self.base / "ff7_stage"
        ff7_mods.mkdir(parents=True)
        ff7_stage.mkdir(parents=True)
        (ff7_stage / "CloudHair").mkdir()
        (ff7_stage / "CloudHair" / "hair.pak").write_bytes(b"HAIR1")

        # Escenario genérico
        gen_mods = self.base / "generic" / "mods"
        gen_stage = self.base / "gen_stage"
        gen_mods.mkdir(parents=True)
        gen_stage.mkdir(parents=True)
        (gen_stage / "ModPack").mkdir()
        (gen_stage / "ModPack" / "mod.pak").write_bytes(b"GEN1")

        reg = GamesRegistry()
        ff7 = GameRecord(
            id="ff7r_tmp",
            name="FF7R Temp",
            mods_dir=str(ff7_mods),
            stage_dir=str(ff7_stage),
            adapter="ue4_paks_mods",
            data_mode="isolated",
            data_dir_name="ff7r_tmp",
            vortex_game_id="finalfantasy7remake",
        )
        gen = GameRecord(
            id="generic_tmp",
            name="Generic Temp",
            mods_dir=str(gen_mods),
            stage_dir=str(gen_stage),
            adapter="generic_folder",
            data_mode="isolated",
            data_dir_name="generic_tmp",
        )
        add_game(reg, ff7)
        add_game(reg, gen)
        set_active_game(reg, "ff7r_tmp")

        p_ff7 = game_paths_for(ff7, app_data=app_data)
        p_gen = game_paths_for(gen, app_data=app_data)
        self.assertNotEqual(p_ff7.data_dir, p_gen.data_dir)

        # Detectar mods staging
        mods_ff7 = scan_staging(p_ff7.stage_dir)
        self.assertTrue(any(m.folder == "CloudHair" for m in mods_ff7))
        for m in mods_ff7:
            if m.folder == "CloudHair":
                m.usar = True
                m.pak_elegido = m.paks[0] if m.paks else ""

        # Conflictos / prioridades
        save_priorities(p_ff7.priorities_json, {"CloudHair": 10})
        save_resolutions(p_ff7.resolutions_json, {})

        ctx_ff7 = p_ff7.apply_context()
        settings_ff7 = p_ff7.conflict_settings()
        active = [m for m in mods_ff7 if m.usar]
        plan = plan_apply(active, ctx_ff7, settings_ff7)
        self.assertFalse(plan.errors, plan.errors)
        # Simulación no escribe
        before = list(ff7_mods.glob("**/*"))
        self.assertFalse(plan.conflicts)
        after_sim = list(ff7_mods.glob("**/*"))
        self.assertEqual(before, after_sim)

        execute(plan, ctx_ff7, mods=active)
        self.assertTrue((ff7_mods / "hair.pak").exists())
        self.assertIn("hair.pak", load_manifest(ctx_ff7))

        # Desactivar
        for m in active:
            m.usar = False
        plan_off = plan_apply(active, ctx_ff7, settings_ff7)
        execute(plan_off, ctx_ff7, mods=active)
        self.assertFalse((ff7_mods / "hair.pak").exists())

        # Restaurar última apply (desactivación) → vuelve hair
        ops = list_operations(p_ff7.data_dir)
        deact = next(o for o in ops if o.op_type == "deactivate" or o.removed)
        rplan = plan_restore(
            p_ff7.data_dir, ctx_ff7, deact.id, hash_cache_path=p_ff7.hash_cache_json
        )
        self.assertTrue(rplan.ok, rplan.errors)
        execute_restore(
            rplan,
            ctx_ff7,
            p_ff7.data_dir,
            confirm=True,
            hash_cache_path=p_ff7.hash_cache_json,
        )
        self.assertTrue((ff7_mods / "hair.pak").exists())
        self.assertIn("hair.pak", load_manifest(ctx_ff7))

        # Juego genérico aislado: instalar sin contaminar FF7
        mods_gen = scan_staging(p_gen.stage_dir)
        for m in mods_gen:
            m.usar = True
            m.pak_elegido = m.paks[0]
        ctx_gen = p_gen.apply_context()
        execute(
            plan_apply(mods_gen, ctx_gen, p_gen.conflict_settings()),
            ctx_gen,
            mods=mods_gen,
        )
        self.assertTrue((gen_mods / "mod.pak").exists())
        self.assertNotIn("mod.pak", load_manifest(ctx_ff7))
        self.assertNotIn("hair.pak", load_manifest(ctx_gen))


class TestVortexSimulated(S05TempCase):
    def test_deploy_blocks_apply_and_adoption(self):
        content = b"VX"
        s = self._stage("VMod", {"v.pak": content})
        # Deploy activo simulando Vortex
        deploy = {
            "files": [
                {
                    "relPath": "v.pak",
                    "source": str(s / "v.pak"),
                }
            ]
        }
        self.ctx.deploy.write_text(json.dumps(deploy), encoding="utf-8")
        (self.mods / "v.pak").write_bytes(content)

        m = _mod("VMod", s, "v.pak")
        plan = plan_apply([m], self.ctx, self.settings)
        with self.assertRaises(ApplyError):
            execute(plan, self.ctx, mods=[m])

        ap = plan_adoption("v.pak", self.ctx)
        self.assertFalse(ap.ok)

    def test_no_deploy_residual_is_externo(self):
        (self.mods / "orphan.pak").write_bytes(b"ORPH")
        inv = scan_destination(
            self.mods,
            manifest={},
            deploy_path=self.ctx.deploy,
            compute_hashes=False,
        )
        by = {f.rel: f for f in inv.files}
        self.assertEqual(by["orphan.pak"].provenance, Provenance.EXTERNO)

    def test_incomplete_vortex_meta_still_scans(self):
        # Staging con meta incompleta no debe romper escaneo
        d = self._stage("BrokenMeta", {"z.pak": b"Z"})
        (d / "meta.json").write_text("{not-json", encoding="utf-8")
        mods = scan_staging(self.stage)
        self.assertTrue(any(m.folder == "BrokenMeta" for m in mods))


class TestSecurityWrites(S05TempCase):
    def test_absolute_path_rejected(self):
        from app.core.apply import safe_resolve_under

        with self.assertRaises(ApplyError):
            safe_resolve_under(self.mods, "C:/Windows/notepad.exe")
        with self.assertRaises(ApplyError):
            safe_resolve_under(self.mods, "../escape.pak")

    def test_simulate_does_not_write(self):
        s = self._stage("ModA", {"a.pak": b"A"})
        m = _mod("ModA", s, "a.pak")
        plan_apply([m], self.ctx, self.settings)
        self.assertFalse((self.mods / "a.pak").exists())
        self.assertFalse(self.ctx.manifest.exists())

    def test_unknown_file_protected(self):
        (self.mods / "foreign.pak").write_bytes(b"F")
        s = self._stage("ModA", {"foreign.pak": b"NEW"})
        m = _mod("ModA", s, "foreign.pak")
        plan = plan_apply([m], self.ctx, self.settings)
        self.assertTrue(plan.errors)
        with self.assertRaises(ApplyError):
            execute(plan, self.ctx, mods=[m])
        self.assertEqual((self.mods / "foreign.pak").read_bytes(), b"F")


class TestUISmoke(unittest.TestCase):
    """Comprobación estructural de GUI (no es validación visual)."""

    def test_gui_module_loads_and_actions_exist(self):
        from app import gui

        self.assertTrue(callable(gui.run))
        required = [
            "simulate",
            "apply_to_game",
            "open_files_panel",
            "open_history_panel",
            "open_conflicts_panel",
            "show_view",
        ]
        for name in required:
            self.assertTrue(hasattr(gui.ModManagerApp, name), msg=name)
            self.assertTrue(callable(getattr(gui.ModManagerApp, name)))

    def test_app_import_main(self):
        import app.__main__ as main_mod  # noqa: F401
        from app.version import __version__

        self.assertEqual(__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
