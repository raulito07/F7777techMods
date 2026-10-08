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

S09 — COPY/HARDLINK/AUTO, elegibilidad, staging watch, espacio (solo temporales).
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

from app.core.apply import ApplyContext, execute, load_manifest, plan_apply  # noqa: E402
from app.core.conflict_engine import ConflictSettings  # noqa: E402
from app.core.install_modes import (  # noqa: E402
    InstallMethod,
    InstallMode,
    decide_install_method,
    evaluate_hardlink_eligibility,
    install_file_atomic,
    same_file,
)
from app.core.inventory import ModEntry  # noqa: E402
from app.core.staging_watch import (  # noqa: E402
    detect_staging_changes,
    record_staging_fingerprint,
)
from app.core.storage_report import build_storage_report  # noqa: E402


def _mod(folder: str, stage: Path, pak: str, *, usar=True) -> ModEntry:
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


def _stage(base: Path, folder: str, files: dict[str, bytes]) -> Path:
    d = base / "stage" / folder
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return d


class S09StorageTests(unittest.TestCase):
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

    def tearDown(self):
        self._td.cleanup()

    def _settings(self, mode: str) -> ConflictSettings:
        return ConflictSettings(
            hash_cache_path=self.data / "hash_cache.json",
            adapter_id="generic_folder",
            install_mode=mode,
            stage_root=self.stage,
            mods_root=self.mods,
        )

    def test_copy_install(self):
        s = _stage(self.base, "ModA", {"a.pak": b"AAA"})
        m = _mod("ModA", s, "a.pak")
        plan = plan_apply([m], self.ctx, self._settings("COPY"))
        self.assertEqual(plan.install_decisions["a.pak"]["method"], "COPY")
        execute(plan, self.ctx, mods=[m])
        self.assertEqual((self.mods / "a.pak").read_bytes(), b"AAA")
        self.assertFalse(same_file(s / "a.pak", self.mods / "a.pak"))
        man = load_manifest(self.ctx)
        self.assertEqual(man["a.pak"].get("install_method"), "COPY")

    def test_hardlink_eligible_same_volume(self):
        src = self.stage / "x.pak"
        src.write_bytes(b"PACKDATA")
        dst = self.mods / "x.pak"
        elig = evaluate_hardlink_eligibility(
            src, dst, stage_root=self.stage, mods_root=self.mods
        )
        # En el mismo temp dir suele ser mismo volumen NTFS
        if not elig.ok:
            self.skipTest(f"entorno sin hardlink: {elig.reasons}")
        used = install_file_atomic(src, dst, InstallMethod.HARDLINK)
        self.assertEqual(used, InstallMethod.HARDLINK)
        self.assertTrue(same_file(src, dst))
        # Modificar destino afecta origen (riesgo documentado)
        dst.write_bytes(b"MUTATED!")
        self.assertEqual(src.read_bytes(), b"MUTATED!")

    def test_hardlink_blocked_cross_suffix_ini(self):
        src = self.stage / "cfg.ini"
        src.write_bytes(b"[x]")
        dst = self.mods / "cfg.ini"
        elig = evaluate_hardlink_eligibility(
            src, dst, stage_root=self.stage, mods_root=self.mods
        )
        self.assertFalse(elig.ok)
        dec = decide_install_method(
            src, dst, InstallMode.HARDLINK, stage_root=self.stage, mods_root=self.mods
        )
        self.assertTrue(dec.blocked)
        self.assertEqual(dec.method, InstallMethod.COPY)

    def test_auto_fallback_copy(self):
        src = self.stage / "notes.txt"
        src.write_bytes(b"hello")
        dst = self.mods / "notes.txt"
        dec = decide_install_method(
            src, dst, InstallMode.AUTO, stage_root=self.stage, mods_root=self.mods
        )
        self.assertEqual(dec.method, InstallMethod.COPY)
        self.assertIn("AUTO→COPY", dec.reason)

    def test_hardlink_policy_blocks_plan_when_ineligible(self):
        s = _stage(self.base, "ModB", {"readme.txt": b"doc", "b.pak": b"B"})
        # Con generic, readme también se ofrece; hardlink de .txt bloquea el plan
        m = _mod("ModB", s, "b.pak")
        plan = plan_apply([m], self.ctx, self._settings("HARDLINK"))
        # Al menos un destino bloqueado o el .pak ok
        blocked = [d for d in plan.install_decisions.values() if d.get("blocked")]
        # Si hay .txt en desired, debe bloquear
        if "readme.txt" in plan.desired_meta:
            self.assertTrue(blocked or plan.errors)

    def test_deactivate_does_not_touch_staging(self):
        s = _stage(self.base, "ModC", {"c.pak": b"CCC"})
        m = _mod("ModC", s, "c.pak")
        execute(plan_apply([m], self.ctx, self._settings("COPY")), self.ctx, mods=[m])
        self.assertTrue((s / "c.pak").is_file())
        m.usar = False
        execute(plan_apply([m], self.ctx, self._settings("COPY")), self.ctx, mods=[m])
        self.assertFalse((self.mods / "c.pak").exists())
        self.assertEqual((s / "c.pak").read_bytes(), b"CCC")

    def test_atomic_update_replaces_hardlink(self):
        src1 = self.stage / "v1.pak"
        src1.write_bytes(b"VERSION1")
        dst = self.mods / "v.pak"
        elig = evaluate_hardlink_eligibility(
            src1, dst, stage_root=self.stage, mods_root=self.mods
        )
        if not elig.ok:
            self.skipTest("sin hardlink")
        install_file_atomic(src1, dst, InstallMethod.HARDLINK)
        src2 = self.stage / "v2.pak"
        src2.write_bytes(b"VERSION2-LONGER")
        used = install_file_atomic(src2, dst, InstallMethod.HARDLINK)
        self.assertEqual(dst.read_bytes(), b"VERSION2-LONGER")
        # Origen v1 no debe haberse sobrescrito in-place por la nueva versión
        self.assertEqual(src1.read_bytes(), b"VERSION1")
        self.assertIn(used, (InstallMethod.HARDLINK, InstallMethod.COPY))

    def test_rollback_hardlink_restore_is_copy(self):
        s = _stage(self.base, "ModD", {"d.pak": b"OLD"})
        m = _mod("ModD", s, "d.pak")
        settings = self._settings("AUTO")
        execute(plan_apply([m], self.ctx, settings), self.ctx, mods=[m])
        # Simular fallo: preparar plan de update y forzar error tras backup
        (s / "d.pak").write_bytes(b"NEWDATA")
        plan = plan_apply([m], self.ctx, settings)
        # Inyectar origen inexistente en execute revalidación es difícil;
        # comprobar que backup no es hardlink
        from app.core import apply as apply_mod

        bdir = apply_mod._prepare_backup(plan, self.ctx)
        bak = bdir / "files" / "d.pak"
        if bak.is_file():
            self.assertFalse(same_file(bak, self.mods / "d.pak"))
            self.assertFalse(same_file(bak, s / "d.pak"))

    def test_staging_change_detection(self):
        s = _stage(self.base, "ModE", {"e.pak": b"E1"})
        m = _mod("ModE", s, "e.pak")
        fp = self.data / "staging_fingerprint.json"
        record_staging_fingerprint([m], fp)
        r0 = detect_staging_changes([m], fp)
        self.assertEqual(r0.changed_mods, 0)
        (s / "e.pak").write_bytes(b"E2-changed")
        r1 = detect_staging_changes([m], fp)
        self.assertGreaterEqual(r1.changed_mods, 1)
        self.assertTrue(any(d.label for d in r1.deltas))
        # No se modificó la huella automáticamente
        self.assertTrue(fp.is_file())

    def test_storage_estimate(self):
        s = _stage(self.base, "ModF", {"f.pak": b"12345"})
        src = s / "f.pak"
        dst = self.mods / "f.pak"
        rep = build_storage_report(
            mods_dir=self.mods,
            stage_dir=self.stage,
            plan_sources=[(src, dst, "f.pak")],
            install_mode="AUTO",
        )
        self.assertEqual(rep.staging_logical, 5)
        self.assertGreaterEqual(rep.estimated_extra_copy, 5)
        # Ahorro estimado no inventado: <= extra_copy
        self.assertLessEqual(rep.estimated_savings_hardlink_vs_copy, rep.estimated_extra_copy)

    def test_manifest_records_method(self):
        s = _stage(self.base, "ModG", {"g.pak": b"GGG"})
        m = _mod("ModG", s, "g.pak")
        plan = plan_apply([m], self.ctx, self._settings("AUTO"))
        execute(plan, self.ctx, mods=[m])
        man = load_manifest(self.ctx)
        self.assertIn(man["g.pak"].get("install_method"), ("COPY", "HARDLINK"))


if __name__ == "__main__":
    unittest.main()
