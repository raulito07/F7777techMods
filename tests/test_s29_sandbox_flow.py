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

S29 — flujo sandbox (subprocess aislado).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "s29_ui_test_mode.py"


class S29SandboxFlowTests(unittest.TestCase):
    def test_headless_e2e_subprocess(self):
        td = tempfile.mkdtemp(prefix="s29_test_")
        env = os.environ.copy()
        env["SGM_TEST_SANDBOX"] = "1"
        env["SGM_TEST_SANDBOX_ROOT"] = td
        # No heredar perfil local
        env.pop("SGM_DATA_DIR", None)
        env.pop("SGM_USE_APPDATA", None)
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--reset", "--root", td, "--e2e"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            self.fail(
                f"e2e rc={proc.returncode}\nSTDOUT:\n{proc.stdout[-2000:]}\n"
                f"STDERR:\n{proc.stderr[-2000:]}"
            )
        self.assertIn("[OK] s28_simple", proc.stdout)
        self.assertIn("[OK] aplicar_sandbox", proc.stdout)
        self.assertIn("[OK] archivar_zip", proc.stdout)

    def test_ensure_registry_skips_real_profiles(self):
        td = Path(tempfile.mkdtemp(prefix="s29_reg_"))
        (td / "app_data").mkdir()
        env = os.environ.copy()
        env["SGM_TEST_SANDBOX"] = "1"
        env["SGM_DATA_DIR"] = str(td / "app_data")
        code = (
            "import os,json;"
            "from pathlib import Path;"
            "from app.core.games import ensure_registry, save_registry, GamesRegistry;"
            "reg=ensure_registry();"
            "assert 'ff7_rebirth' not in reg.games;"
            "assert 'stellar_blade' not in reg.games;"
            "assert not reg.games;"
            "print('ok')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
