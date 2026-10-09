# -*- coding: utf-8 -*-
"""
F7777techMods — S42 EMOV multidestino (sandbox).
Versión: 0.1.0 — Four Seven Tech / GPL-3.0-or-later
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import ApplyPlan  # noqa: E402
from app.core.emov_apply import (  # noqa: E402
    EmovApplyContext,
    execute_emov_plan,
    load_emov_manifest,
    prepare_emov_backup,
    restore_original_emov,
    rollback_emov_backup,
    OP_RESTAURAR_ORIGINAL,
)
from app.core.emov_plan import (  # noqa: E402
    coordinated_apply_blocked,
    plan_ff7r_emov_replace,
)
from app.core.hash_cache import sha256_file  # noqa: E402
from app.core.inventory import ModEntry  # noqa: E402
from app.core.multi_destination import (  # noqa: E402
    resolve_ff7r_emov,
    validate_ff7r_movie_staging_rel,
)


def _mod(stage: Path, folder="m1") -> ModEntry:
    return ModEntry(
        folder=folder,
        name="test",
        characters=["OTROS"],
        character_main="OTROS",
        paks=[],
        multi=False,
        on_disk=False,
        stage_path=str(stage),
        usar=True,
    )


def _sandbox_layout(base: Path) -> tuple[Path, Path, Path]:
    game = base / "game"
    movie = game / "End/Content/GameContents/Movie/010-MAKO1/MV_MAKO1_0220"
    movie.mkdir(parents=True)
    vanilla = movie / "MV_MAKO1_0220_US.emov"
    vanilla.write_bytes(b"VANILLA-CONTENT-1234567890")
    stage = base / "stage"
    srel = "010-MAKO1/MV_MAKO1_0220/MV_MAKO1_0220_US.emov"
    src = stage / srel
    src.parent.mkdir(parents=True)
    src.write_bytes(b"MOD-REPLACEMENT-CONTENT")
    data = base / "data"
    data.mkdir()
    return game, stage, data


class S42EmovTests(unittest.TestCase):
    def test_validate_movie_rel(self):
        ok, _ = validate_ff7r_movie_staging_rel(
            "010-MAKO1/MV_MAKO1_0220/MV_MAKO1_0220_US.emov"
        )
        self.assertTrue(ok)
        self.assertIsNone(resolve_ff7r_emov("../evil.emov"))
        ok2, _ = validate_ff7r_movie_staging_rel("bad/name.emov")
        self.assertFalse(ok2)

    def test_plan_requires_vanilla(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game = base / "game"
        stage = base / "stage"
        srel = "010-MAKO1/MV_MAKO1_0220/MV_MAKO1_0220_US.emov"
        (stage / srel).parent.mkdir(parents=True)
        (stage / srel).write_bytes(b"x")
        plan = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        self.assertFalse(plan.to_replace)
        self.assertTrue(plan.errors)

    def test_replace_backup_execute_restore(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        m = _mod(stage)
        plan = plan_ff7r_emov_replace([m], game_root=game, adapter_id="ue4_paks_mods")
        self.assertEqual(len(plan.to_replace), 1)
        ctx = EmovApplyContext(
            game_root=game, data_dir=data, backups=data / "backups"
        )
        bdir = prepare_emov_backup(plan, ctx)
        self.assertTrue(bdir.is_dir())
        bid = execute_emov_plan(plan, ctx, user_confirmed_overwrite=True)
        self.assertTrue(bid)
        self.assertTrue((ctx.backups / bid).is_dir())
        dst = plan.to_replace[0].destination
        self.assertEqual(sha256_file(dst), sha256_file(plan.to_replace[0].source))
        rel = plan.to_replace[0].game_rel
        restore_original_emov([rel], ctx, op_type=OP_RESTAURAR_ORIGINAL)
        self.assertEqual(sha256_file(dst), plan.to_replace[0].vanilla_sha256)
        self.assertNotIn(rel, load_emov_manifest(ctx))

    def test_conflict_two_mods_same_clip(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage1, _ = _sandbox_layout(base)
        stage2 = base / "stage2"
        srel = "010-MAKO1/MV_MAKO1_0220/MV_MAKO1_0220_US.emov"
        p = stage2 / srel
        p.parent.mkdir(parents=True)
        p.write_bytes(b"other")
        plan = plan_ff7r_emov_replace(
            [_mod(stage1, "a"), _mod(stage2, "b")],
            game_root=game,
            adapter_id="ue4_paks_mods",
        )
        self.assertTrue(plan.conflicts)

    def test_external_change_blocks_execute(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        plan = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        ctx = EmovApplyContext(
            game_root=game, data_dir=data, backups=data / "backups"
        )
        plan.to_replace[0].destination.write_bytes(b"TAMPERED")
        with self.assertRaises(Exception):
            execute_emov_plan(plan, ctx, user_confirmed_overwrite=True)

    def test_rollback_after_failed_mid(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        plan = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        ctx = EmovApplyContext(
            game_root=game, data_dir=data, backups=data / "backups"
        )
        bdir = prepare_emov_backup(plan, ctx)
        vanilla_hash = plan.to_replace[0].vanilla_sha256
        dst = plan.to_replace[0].destination
        from app.core.apply import _copy_replace

        _copy_replace(plan.to_replace[0].source, dst)
        rollback_emov_backup(bdir, ctx)
        self.assertEqual(sha256_file(dst), vanilla_hash)

    def test_mixed_pak_emov_blocked(self):
        pak = ApplyPlan(
            to_add=["a.pak"],
            to_update=[],
            to_remove=[],
            desired={},
            desired_meta={},
            errors=[],
            conflicts=0,
        )
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        emov = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        blocked, msgs = coordinated_apply_blocked(pak, emov)
        self.assertTrue(blocked)
        self.assertTrue(msgs)

    def test_invalid_scene_blocked(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        bad = stage / "INVALID/MV_X/MV_X.emov"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"x")
        plan = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        self.assertEqual(len(plan.to_replace), 1)
        self.assertTrue(plan.errors)

    def test_no_confirm_blocks(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        game, stage, data = _sandbox_layout(base)
        plan = plan_ff7r_emov_replace(
            [_mod(stage)], game_root=game, adapter_id="ue4_paks_mods"
        )
        ctx = EmovApplyContext(
            game_root=game, data_dir=data, backups=data / "backups"
        )
        from app.core.apply import ApplyError

        with self.assertRaises(ApplyError):
            execute_emov_plan(plan, ctx, user_confirmed_overwrite=False)


if __name__ == "__main__":
    unittest.main()
