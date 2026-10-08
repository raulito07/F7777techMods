# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S30 — win_compat y flags de subproceso.
"""

from __future__ import annotations

import sys
import unittest

from app.core.win_compat import (
    APP_USER_MODEL_ID,
    CREATE_NO_WINDOW,
    prepare_windows_app,
    subprocess_creationflags,
)


class S30WinCompatTests(unittest.TestCase):
    def test_creationflags_windows(self):
        flags = subprocess_creationflags()
        if sys.platform.startswith("win"):
            self.assertEqual(flags, CREATE_NO_WINDOW)
        else:
            self.assertEqual(flags, 0)

    def test_app_id_stable(self):
        self.assertIn("FourSevenTech", APP_USER_MODEL_ID)
        self.assertIn("F7777techMods", APP_USER_MODEL_ID)

    def test_prepare_safe(self):
        prepare_windows_app()  # no debe lanzar


if __name__ == "__main__":
    unittest.main()
