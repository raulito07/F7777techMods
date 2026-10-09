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

S30 — compatibilidad Windows (identidad, subprocesos sin consola, logs).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# CREATE_NO_WINDOW: evita ventanas de consola en hijos (7z, etc.)
CREATE_NO_WINDOW = 0x08000000

APP_USER_MODEL_ID = "FourSevenTech.F7777techMods.0.1.0"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def subprocess_creationflags() -> int:
    """Flags seguros para subprocess en Windows (sin consola)."""
    if not is_windows():
        return 0
    return CREATE_NO_WINDOW


def prepare_windows_app() -> None:
    """Identidad de proceso + log de arranque. Llamar ANTES de crear ventanas."""
    if not is_windows():
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as e:
        log_startup(f"AppUserModelID: {e}")
    # Asegurar que el modo diario no hereda sandbox de otra sesión
    if (os.environ.get("SGM_TEST_SANDBOX") or "").strip() and getattr(
        sys, "frozen", False
    ):
        # EXE diario nunca debe arrancar en sandbox salvo flag explícita SGM_ALLOW_TEST_IN_FROZEN=1
        if (os.environ.get("SGM_ALLOW_TEST_IN_FROZEN") or "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            os.environ.pop("SGM_TEST_SANDBOX", None)
            os.environ.pop("SGM_DATA_DIR", None)
            log_startup("SGM_TEST_SANDBOX ignorado en EXE congelado (modo diario)")


def _append_user_log(filename: str, message: str) -> None:
    try:
        from .paths import default_user_data_dir

        log_dir = default_user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / filename
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def log_startup(message: str) -> None:
    """Log local en datos de usuario (no consola)."""
    _append_user_log("startup.log", message)


def log_ui(message: str) -> None:
    """Eventos UI / miniaturas (errores de carga, reintentos)."""
    _append_user_log("ui.log", message)


def resolve_app_icon_paths() -> list[Path]:
    """Candidatos .ico / .png junto al EXE, instalación runtime o packaging."""
    out: list[Path] = []
    install = (os.environ.get("F7777TECHMODS_INSTALL_DIR") or "").strip()
    if install:
        base = Path(install)
        out.extend([base / "f7777techmods.ico", base / "resources" / "f7777techmods.ico",
                    base / "f7777techmods.png", base / "resources" / "f7777techmods.png"])
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        out.extend(
            [
                base / "f7777techmods.ico",
                base / "f7777techmods.png",
                base / "_internal" / "f7777techmods.ico",
            ]
        )
    else:
        # cwd del launcher diario + fuentes de desarrollo
        cwd = Path.cwd()
        out.extend([cwd / "f7777techmods.ico", cwd / "resources" / "f7777techmods.ico",
                    cwd / "f7777techmods.png", cwd / "resources" / "f7777techmods.png"])
        root = Path(__file__).resolve().parents[2]
        assets = root / "packaging" / "assets"
        out.extend(
            [
                assets / "f7777techmods.ico",
                assets / "f7777techmods.png",
            ]
        )
    return out
