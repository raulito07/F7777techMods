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

Rutas globales de la aplicación (no del juego activo).

Las rutas de cada juego se resuelven vía app.core.games.GamePaths / ApplyContext.
LEGACY_FF7R_* se descubren por entorno / rutas estándar — sin rutas de usuario fijas.

Datos persistentes (S22):
- Desarrollo: <repo>/data  (salvo SGM_DATA_DIR / SGM_USE_APPDATA)
- Empaquetado (frozen): %LOCALAPPDATA%\\FourSevenTech\\F7777techMods\\
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


ROOT = _app_root()
LEGACY = ROOT / "legacy"


def default_user_data_dir() -> Path:
    """Ubicación Windows estándar para datos del usuario (no dentro del exe)."""
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "FourSevenTech" / "F7777techMods"
    return Path.home() / "AppData" / "Local" / "FourSevenTech" / "F7777techMods"


def resolve_data_dir() -> Path:
    env = (os.environ.get("SGM_DATA_DIR") or "").strip()
    if env:
        return Path(env)
    flag = (os.environ.get("SGM_USE_APPDATA") or "").strip().lower()
    if is_frozen() or flag in ("1", "true", "yes", "on"):
        return default_user_data_dir()
    return ROOT / "data"


DATA = resolve_data_dir()

GAMES_REGISTRY = DATA / "games.json"
GAMES_DATA_ROOT = DATA / "games"
UI_SETTINGS_JSON = DATA / "ui_settings.json"


def _env_path(key: str) -> Path:
    v = (os.environ.get(key) or "").strip()
    return Path(v) if v else Path()


def path_configured(p: Path | None) -> bool:
    """True si hay ruta real. Path() vacío → str=='.' (no usar truthiness de str)."""
    if p is None:
        return False
    return bool(p.parts)


def as_path_str(p: Path | None) -> str:
    return str(p) if path_configured(p) else ""


def discover_steam_common() -> Path:
    for base in (
        Path(r"C:\Program Files (x86)\Steam\steamapps\common"),
        Path(r"C:\Program Files\Steam\steamapps\common"),
    ):
        if base.is_dir():
            return base
    return Path()


def discover_steam_game(*parts: str) -> Path:
    """Ruta del juego si existe en Steam común; Path() vacío si no."""
    override = _env_path("SGM_STEAM_COMMON")
    roots = [override] if path_configured(override) else []
    common = discover_steam_common()
    if path_configured(common):
        roots.append(common)
    for root in roots:
        cand = root.joinpath(*parts)
        if cand.is_dir():
            return cand
    return Path()


def suggest_vortex_mods(vortex_game_id: str) -> Path:
    """Ruta candidata de staging Vortex (puede no existir aún)."""
    override = _env_path(f"SGM_VORTEX_MODS_{vortex_game_id.upper()}")
    if path_configured(override):
        return override
    appdata = (os.environ.get("APPDATA") or "").strip()
    if not appdata or not vortex_game_id:
        return Path()
    return Path(appdata) / "Vortex" / vortex_game_id / "mods"


def suggest_vortex_downloads(vortex_game_id: str) -> Path:
    """Ruta candidata de downloads Vortex (puede no existir aún)."""
    override = _env_path(f"SGM_VORTEX_DL_{vortex_game_id.upper()}")
    if path_configured(override):
        return override
    appdata = (os.environ.get("APPDATA") or "").strip()
    if not appdata or not vortex_game_id:
        return Path()
    return Path(appdata) / "Vortex" / "downloads" / vortex_game_id


def discover_vortex_mods(vortex_game_id: str) -> Path:
    """Staging Vortex si la carpeta existe (sin hardcodear usuario)."""
    cand = suggest_vortex_mods(vortex_game_id)
    return cand if path_configured(cand) and cand.is_dir() else Path()


def discover_vortex_downloads(vortex_game_id: str) -> Path:
    cand = suggest_vortex_downloads(vortex_game_id)
    return cand if path_configured(cand) and cand.is_dir() else Path()


# --- FF7 Remake: IDs estables (no son rutas) + descubrimiento local ---
LEGACY_FF7R_VORTEX_ID = "finalfantasy7remake"
LEGACY_FF7R_GAME_ID = "ff7r_remake"
LEGACY_FF7R_GAME_ROOT = discover_steam_game("FINAL FANTASY VII REMAKE")
_env_ff7r_root = _env_path("SGM_LEGACY_FF7R_GAME_ROOT")
if path_configured(_env_ff7r_root):
    LEGACY_FF7R_GAME_ROOT = _env_ff7r_root
LEGACY_FF7R_MODS = (
    LEGACY_FF7R_GAME_ROOT / "End" / "Content" / "Paks" / "~mods"
    if path_configured(LEGACY_FF7R_GAME_ROOT)
    else Path()
)
LEGACY_FF7R_STAGE = discover_vortex_mods(LEGACY_FF7R_VORTEX_ID)
_env_ff7r_stage = _env_path("SGM_LEGACY_FF7R_STAGE")
if path_configured(_env_ff7r_stage):
    LEGACY_FF7R_STAGE = _env_ff7r_stage

# Compatibilidad imports antiguos (pueden ser Path vacíos en instalación limpia)
STAGE = LEGACY_FF7R_STAGE
PAKS_ROOT = (
    LEGACY_FF7R_GAME_ROOT / "End" / "Content" / "Paks"
    if path_configured(LEGACY_FF7R_GAME_ROOT)
    else Path()
)
MODS = LEGACY_FF7R_MODS
DEPLOY = (
    MODS / "vortex.deployment.json"
    if path_configured(MODS)
    else Path("vortex.deployment.json")
)
LOADOUT_JSON = DATA / "loadout.json"
DESC_OVERRIDE = DATA / "descriptions_override.json"
LOADOUT_MARKER = (
    MODS / "_manual_loadout.json"
    if path_configured(MODS)
    else Path("_manual_loadout.json")
)
MANAGED_MANIFEST = DATA / "managed_manifest.json"
BACKUPS_DIR = DATA / "backups"
