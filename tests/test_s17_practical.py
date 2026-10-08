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

S17 — validación práctica (motor obligatorio; UI si el entorno lo permite).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.s17_practical_validation import (  # noqa: E402
    run_full_validation,
    run_motor_cycle,
)


class S17PracticalTests(unittest.TestCase):
    def test_motor_cycle_temp(self):
        rep = run_motor_cycle()
        failed = [s for s in rep.steps if not s.ok]
        self.assertTrue(
            rep.ok,
            msg="Fallos: " + "; ".join(f"{s.name}:{s.detail}" for s in failed),
        )
        self.assertTrue(rep.safety.get("only_temp_profile"))
        self.assertFalse(rep.safety.get("steam_written"))
        self.assertFalse(rep.safety.get("vortex_modified"))

    def test_full_validation_includes_ui_attempt(self):
        rep = run_full_validation(keep_temp=False)
        self.assertTrue(
            any(s.name == "ui_ventana_real" for s in rep.steps),
            msg="Debe intentar abrir ventana real CustomTkinter",
        )
        # Motor debe haber pasado
        motor_fails = [
            s
            for s in rep.steps
            if not s.ok and s.name != "ui_ventana_real"
        ]
        self.assertFalse(
            motor_fails,
            msg="; ".join(f"{s.name}:{s.detail}" for s in motor_fails),
        )


if __name__ == "__main__":
    unittest.main()
