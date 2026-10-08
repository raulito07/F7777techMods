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

Pruebas S01 — solo carpetas temporales (nunca Steam/Vortex reales).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Raíz del proyecto en sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.apply import (  # noqa: E402
    ApplyContext,
    ApplyError,
    build_desired,
    execute,
    load_manifest,
    plan_apply,
    safe_resolve_under,
    vortex_deploy_present,
)
from app.core.inventory import ModEntry  # noqa: E402


def _mod(
    folder: str,
    stage: Path,
    *,
    usar: bool = True,
    paks: list[str] | None = None,
    pak_elegido: str = "",
    multi: bool = False,
) -> ModEntry:
    paks = paks or []
    return ModEntry(
        folder=folder,
        name=folder,
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=multi or len(paks) > 1,
        on_disk=False,
        stage_path=str(stage),
        usar=usar,
        pak_elegido=pak_elegido or (paks[0] if len(paks) == 1 else ""),
    )


def _ctx(base: Path) -> ApplyContext:
    mods = base / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    return ApplyContext(
        mods=mods,
        deploy=mods / "vortex.deployment.json",
        loadout_marker=mods / "_manual_loadout.json",
        manifest=data / "managed_manifest.json",
        backups=data / "backups",
        stage=base / "stage",
    )


def _stage_mod(base: Path, folder: str, files: dict[str, bytes]) -> Path:
    d = base / "stage" / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return d


class ApplySafetyTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.base = Path(self._td.name)
        self.ctx = _ctx(self.base)

    def tearDown(self):
        self._td.cleanup()

    def test_foreign_file_preserved(self):
        foreign = self.ctx.mods / "foreign_manual.pak"
        foreign.write_bytes(b"FOREIGN")
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        mods = [_mod("ModA", stage, paks=["a.pak"])]
        plan = plan_apply(mods, self.ctx)
        self.assertFalse(plan.errors)
        execute(plan, self.ctx)
        self.assertTrue(foreign.exists())
        self.assertEqual(foreign.read_bytes(), b"FOREIGN")
        self.assertTrue((self.ctx.mods / "a.pak").exists())

    def test_managed_file_removed(self):
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        mods = [_mod("ModA", stage, paks=["a.pak"])]
        execute(plan_apply(mods, self.ctx), self.ctx)
        self.assertTrue((self.ctx.mods / "a.pak").exists())
        # Segundo apply sin el mod → debe quitar a.pak (gestionado)
        plan2 = plan_apply([], self.ctx)
        execute(plan2, self.ctx)
        self.assertFalse((self.ctx.mods / "a.pak").exists())

    def test_name_collision_two_mods(self):
        s1 = _stage_mod(self.base, "ModA", {"same.pak": b"A"})
        s2 = _stage_mod(self.base, "ModB", {"same.pak": b"B"})
        mods = [
            _mod("ModA", s1, paks=["same.pak"]),
            _mod("ModB", s2, paks=["same.pak"]),
        ]
        desired, errors, analysis = build_desired(mods)
        self.assertTrue(errors)
        self.assertTrue(analysis and analysis.unresolved >= 1)
        plan = plan_apply(mods, self.ctx)
        self.assertTrue(plan.errors)
        with self.assertRaises(ApplyError):
            execute(plan, self.ctx)
        self.assertFalse((self.ctx.mods / "same.pak").exists())

    def test_case_collision(self):
        s1 = _stage_mod(self.base, "ModA", {"Cloud.pak": b"A"})
        s2 = _stage_mod(self.base, "ModB", {"cloud.pak": b"B"})
        mods = [
            _mod("ModA", s1, paks=["Cloud.pak"]),
            _mod("ModB", s2, paks=["cloud.pak"]),
        ]
        _, errors, analysis = build_desired(mods)
        if os.name == "nt":
            self.assertTrue(errors)
            self.assertTrue(analysis and analysis.unresolved >= 1)
        else:
            # En FS case-sensitive pueden coexistir; no forzar fallo
            pass

    def test_unknown_overwrite_blocked(self):
        (self.ctx.mods / "taken.pak").write_bytes(b"OLD")
        stage = _stage_mod(self.base, "ModA", {"taken.pak": b"NEW"})
        mods = [_mod("ModA", stage, paks=["taken.pak"])]
        plan = plan_apply(mods, self.ctx)
        self.assertTrue(
            any(("no gestionado" in e) or ("AJENO" in e) for e in plan.errors)
        )
        with self.assertRaises(ApplyError):
            execute(plan, self.ctx)
        self.assertEqual((self.ctx.mods / "taken.pak").read_bytes(), b"OLD")

    def test_copy_failure_restores(self):
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA", "b.pak": b"BBB"})
        # Instalar solo a primero
        m1 = _mod("ModA", stage, paks=["a.pak", "b.pak"], multi=True, pak_elegido="a.pak")
        execute(plan_apply([m1], self.ctx), self.ctx)
        self.assertEqual((self.ctx.mods / "a.pak").read_bytes(), b"AAA")

        # Plan con a (update) + b (add); fallar en segunda copia
        m2 = _mod("ModA", stage, paks=["a.pak", "b.pak"], multi=True, pak_elegido="a.pak")
        # Forzar deseado a+b: single-pak logic only picks chosen; use non-pak helper
        # Rebuild: two files — a.pak chosen and extra.txt
        stage2 = _stage_mod(
            self.base,
            "ModC",
            {"c.pak": b"CCC", "extra.txt": b"EXTRA"},
        )
        # Seed managed c.pak
        execute(
            plan_apply([_mod("ModC", stage2, paks=["c.pak"])], self.ctx),
            self.ctx,
        )
        original_c = (self.ctx.mods / "c.pak").read_bytes()

        # Now update c with larger content and add d — fail mid-way
        stage2.joinpath("c.pak").write_bytes(b"CCCC-UPDATED")
        stage2.joinpath("d.pak").write_bytes(b"DDD")
        # Manually craft plan by choosing both via build — d is second pak need multi
        # Simpler: patch _copy_replace to fail on second call
        mods = [_mod("ModC", stage2, paks=["c.pak"])]
        # Also include ModD
        stage_d = _stage_mod(self.base, "ModD", {"d.pak": b"DDD"})
        mods.append(_mod("ModD", stage_d, paks=["d.pak"]))
        plan = plan_apply(mods, self.ctx)
        self.assertFalse(plan.errors)

        import app.core.apply as apply_mod

        real_copy = apply_mod._copy_replace

        def flaky(src, dst):
            # Fallar al actualizar c.pak desde staging; permitir restore desde backups
            src_s = str(src).replace("\\", "/")
            if dst.name == "c.pak" and "/stage/" in src_s:
                raise OSError("simulated copy failure")
            return real_copy(src, dst)

        with mock.patch.object(apply_mod, "_copy_replace", side_effect=flaky):
            with self.assertRaises(ApplyError) as cm:
                execute(plan, self.ctx)
            self.assertTrue(
                cm.exception.rollback_ok,
                msg=str(cm.exception),
            )

        self.assertEqual((self.ctx.mods / "c.pak").read_bytes(), original_c)
        self.assertFalse((self.ctx.mods / "d.pak").exists())
        # Manifiesto no debe listar d
        man = load_manifest(self.ctx)
        self.assertNotIn("d.pak", man)

    def test_backup_prepare_failure_no_changes(self):
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        mods = [_mod("ModA", stage, paks=["a.pak"])]
        plan = plan_apply(mods, self.ctx)
        import app.core.apply as apply_mod

        with mock.patch.object(
            apply_mod,
            "_prepare_backup",
            side_effect=ApplyError("backup failed"),
        ):
            with self.assertRaises(ApplyError):
                execute(plan, self.ctx)
        self.assertFalse((self.ctx.mods / "a.pak").exists())
        self.assertEqual(load_manifest(self.ctx), {})

    def test_manifest_intact_after_error(self):
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        execute(plan_apply([_mod("ModA", stage, paks=["a.pak"])], self.ctx), self.ctx)
        before = self.ctx.manifest.read_text(encoding="utf-8")

        stage_b = _stage_mod(self.base, "ModB", {"b.pak": b"BBB"})
        plan = plan_apply(
            [
                _mod("ModA", stage, paks=["a.pak"]),
                _mod("ModB", stage_b, paks=["b.pak"]),
            ],
            self.ctx,
        )
        import app.core.apply as apply_mod

        with mock.patch.object(
            apply_mod,
            "_copy_replace",
            side_effect=OSError("fail"),
        ):
            with self.assertRaises(ApplyError):
                execute(plan, self.ctx)
        after = self.ctx.manifest.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_path_escape_blocked(self):
        with self.assertRaises(ApplyError):
            safe_resolve_under(self.ctx.mods, "../outside.pak")
        with self.assertRaises(ApplyError):
            safe_resolve_under(self.ctx.mods, r"C:\Windows\evil.pak")

    def test_symlink_escape_blocked(self):
        if os.name == "nt":
            # Crear junction/symlink requiere privilegios; intentar y skip si no
            outside = self.base / "outside"
            outside.mkdir()
            secret = outside / "secret.pak"
            secret.write_bytes(b"SECRET")
            link = self.ctx.mods / "linked"
            try:
                os.symlink(outside, link, target_is_directory=True)
            except OSError:
                self.skipTest("Sin privilegio para symlinks/junctions en este entorno")
            # Resolver linked/secret.pak debe quedar fuera de mods
            with self.assertRaises(ApplyError):
                safe_resolve_under(self.ctx.mods, "linked/secret.pak")
        else:
            outside = self.base / "outside"
            outside.mkdir()
            secret = outside / "secret.pak"
            secret.write_bytes(b"SECRET")
            link = self.ctx.mods / "linked"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ApplyError):
                safe_resolve_under(self.ctx.mods, "linked/secret.pak")

    def test_vortex_deploy_blocks(self):
        self.ctx.deploy.write_text("{}", encoding="utf-8")
        self.assertTrue(vortex_deploy_present(self.ctx))
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        plan = plan_apply([_mod("ModA", stage, paks=["a.pak"])], self.ctx)
        with self.assertRaises(ApplyError) as cm:
            execute(plan, self.ctx)
        self.assertIn("Vortex", str(cm.exception))
        self.assertFalse((self.ctx.mods / "a.pak").exists())

    def test_normal_install(self):
        stage = _stage_mod(
            self.base,
            "ModA",
            {"a.pak": b"AAA", "readme.txt": b"hi"},
        )
        mods = [_mod("ModA", stage, paks=["a.pak"])]
        plan = plan_apply(mods, self.ctx)
        self.assertFalse(plan.errors)
        execute(plan, self.ctx)
        self.assertEqual((self.ctx.mods / "a.pak").read_bytes(), b"AAA")
        self.assertEqual((self.ctx.mods / "readme.txt").read_bytes(), b"hi")
        man = load_manifest(self.ctx)
        self.assertIn("a.pak", man)
        self.assertIn("readme.txt", man)
        self.assertEqual(man["a.pak"]["mod_folder"], "ModA")
        self.assertTrue(self.ctx.loadout_marker.exists())

    def test_simulate_no_disk_writes(self):
        """plan_apply no escribe; equivalente a simulación."""
        stage = _stage_mod(self.base, "ModA", {"a.pak": b"AAA"})
        before = {p.relative_to(self.base) for p in self.base.rglob("*") if p.is_file()}
        plan = plan_apply([_mod("ModA", stage, paks=["a.pak"])], self.ctx)
        self.assertTrue(plan.to_add)
        after = {p.relative_to(self.base) for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.ctx.manifest.exists())


if __name__ == "__main__":
    unittest.main()
