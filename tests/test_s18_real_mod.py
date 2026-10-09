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

S18 — validación mod real FF7R (requiere staging local; se omite si ausente).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.games import ensure_registry  # noqa: E402
from app.core.hash_cache import sha256_file  # noqa: E402
from tools.s18_real_mod_validation import (  # noqa: E402
    CANDIDATE_FOLDER,
    Report,
    run_sandbox_cycle,
    select_candidate,
    simulate_real_ff7r,
)


class S18RealModTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reg = ensure_registry()
        rec = reg.games.get("ff7r_remake")
        cls.stage = Path(rec.stage_dir) if rec else None
        cls.available = bool(
            cls.stage
            and cls.stage.is_dir()
            and (cls.stage / CANDIDATE_FOLDER).is_dir()
        )

    def test_select_and_simulate_no_apply(self):
        if not self.available:
            self.skipTest("Staging FF7R / FOV70 no disponible en este entorno")
        folder, meta = select_candidate(self.stage)
        self.assertEqual(folder, CANDIDATE_FOLDER)
        self.assertEqual(meta["pak"], "FOV70.pak")
        before = sha256_file(self.stage / folder / "FOV70.pak")
        rep = Report(candidate=meta)
        simulate_real_ff7r(folder, rep)
        self.assertTrue(rep.real_sim.get("apply_executed") is False)
        # Tras S19, FOV70 puede ya estar en ~mods: conflictos 0 o 1 según destino.
        self.assertIn(rep.real_sim.get("conflicts"), (0, 1))
        # Tras S19, FOV70 puede ya estar en ~mods: plan sin add o con add.
        add = rep.real_sim.get("to_add") or []
        self.assertTrue(
            add == ["FOV70.pak"] or add == [],
            msg=f"to_add inesperado: {add}",
        )
        # Simulación aislada de 1 candidato: el motor puede listar RETIRAR de
        # otros archivos ya GESTIONADOS no incluidos en este plan (no es Apply).
        rem = rep.real_sim.get("to_remove") or []
        self.assertIsInstance(rem, list)
        if add == ["FOV70.pak"]:
            self.assertNotIn("FOV70.pak", rem)
        after = sha256_file(self.stage / folder / "FOV70.pak")
        self.assertEqual(before, after)

    def test_sandbox_cycle_preserves_staging(self):
        if not self.available:
            self.skipTest("Staging FF7R / FOV70 no disponible en este entorno")
        folder, meta = select_candidate(self.stage)
        before = sha256_file(self.stage / folder / "FOV70.pak")
        rep = Report(candidate=meta)
        run_sandbox_cycle(folder, self.stage, rep)
        after = sha256_file(self.stage / folder / "FOV70.pak")
        self.assertEqual(before, after)
        fails = [s for s in rep.steps if not s.ok]
        self.assertFalse(fails, msg="; ".join(f"{s.name}:{s.detail}" for s in fails))


if __name__ == "__main__":
    unittest.main()
