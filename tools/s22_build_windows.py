# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S22/S22.1 — wrapper: distribución pública = PORTABLE.
Delega en s22_1_build_portable.py (no genera Setup).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path(__file__).resolve().parent / "s22_1_build_portable.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("s22_1_build_portable", TARGET)
    if spec is None or spec.loader is None:
        print("No se pudo cargar", TARGET, file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())
