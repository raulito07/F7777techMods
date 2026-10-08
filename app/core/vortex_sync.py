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

Lectura de flags enable/disable de Vortex (solo lectura).

IMPORTANTE:
- Los JSON en temp/state_backups_full (hourly/daily) son BACKUPS HISTÓRICOS.
- El estado vivo de Vortex está en state.v2 (LevelDB); sin lector LevelDB
  no se puede verificar el enablement actual → «no verificado».
- La ausencia de vortex.deployment.json indica que no hay deploy en disco,
  NO demuestra Disabled en la base de datos de Vortex.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .inventory import ModEntry
from .paths import LEGACY_FF7R_VORTEX_ID

# Backups JSON exportados por Vortex (NO son el estado vivo).
# APPDATA del entorno; sin rutas de usuario fijas.
_appdata = (os.environ.get("APPDATA") or "").strip()
DEFAULT_VORTEX_ROAMING = (
    Path(_appdata) / "Vortex" if _appdata else Path()
)
STATE_BACKUP_CANDIDATES = [
    "temp/state_backups_full/hourly.json",
    "temp/state_backups_full/daily.json",
]
LIVE_STATE_DIRNAME = "state.v2"


class VortexReliability(str, Enum):
    """Fiabilidad del mapa enable/disable."""

    CURRENT = "current"  # verificado como estado vivo (hoy no alcanzable sin LevelDB)
    HISTORICAL_BACKUP = "historical_backup"
    UNKNOWN = "unknown"


@dataclass
class VortexEnableSnapshot:
    """Resultado de sondear Vortex (solo lectura; no muta nada)."""

    reliability: VortexReliability
    enabled_map: dict[str, bool] = field(default_factory=dict)
    game_id: str = ""
    profile_name: str = ""
    profile_id: str = ""
    source_path: str | None = None
    source_mtime_iso: str | None = None
    source_kind: str = "none"  # hourly.json | daily.json | other_backup | none
    live_state_dir: str | None = None
    live_state_present: bool = False
    live_state_mtime_iso: str | None = None
    live_state_readable: bool = False
    deployment_on_disk: bool | None = None  # None = no comprobado
    deployment_path: str | None = None
    enabled_count: int = 0
    disabled_count: int = 0
    message: str = ""
    ui_current_label: str = "Estado Vortex actual no verificado"
    ui_historical_label: str = ""

    @property
    def is_current(self) -> bool:
        return self.reliability == VortexReliability.CURRENT

    @property
    def has_historical_map(self) -> bool:
        return bool(self.enabled_map) and self.reliability in (
            VortexReliability.HISTORICAL_BACKUP,
            VortexReliability.CURRENT,
        )


def _iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


def vortex_roaming_root(override: Path | None = None) -> Path:
    return Path(override) if override is not None else DEFAULT_VORTEX_ROAMING


def find_vortex_state_backup(roaming: Path | None = None) -> Path | None:
    """Localiza un JSON de backup (hourly/daily u otro .json en state_backups_full).

    Nunca debe presentarse como estado actual.
    """
    root = vortex_roaming_root(roaming)
    for rel in STATE_BACKUP_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    backup_dir = root / "temp" / "state_backups_full"
    if backup_dir.is_dir():
        existing = sorted(
            backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if existing:
            return existing[0]
    return None


def find_vortex_live_state_dir(roaming: Path | None = None) -> Path | None:
    """Directorio LevelDB state.v2 (estado vivo). No se parsea aquí."""
    p = vortex_roaming_root(roaming) / LIVE_STATE_DIRNAME
    return p if p.is_dir() else None


def _parse_enable_map_from_backup(
    state_path: Path, game_id: str
) -> tuple[dict[str, bool], str, str, str]:
    """Devuelve (map, profile_name, profile_id, error)."""
    try:
        obj = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {}, "", "", f"No se pudo leer backup Vortex: {e}"

    profiles = obj.get("persistent", {}).get("profiles", {})
    matched = [
        (pid, prof)
        for pid, prof in profiles.items()
        if prof.get("gameId") == game_id
    ]
    if not matched:
        return {}, "", "", f"No hay perfil Vortex para gameId «{game_id}» en el backup."

    matched.sort(key=lambda x: x[1].get("lastActivated") or 0, reverse=True)
    pid, prof = matched[0]
    mod_state = prof.get("modState") or {}
    enabled_map: dict[str, bool] = {}
    for folder, st in mod_state.items():
        if isinstance(st, dict):
            enabled_map[folder] = bool(st.get("enabled"))
        else:
            enabled_map[folder] = bool(st)
    return enabled_map, str(prof.get("name") or pid), str(pid), ""


def probe_vortex_enable_state(
    vortex_game_id: str | None = None,
    *,
    roaming: Path | None = None,
    mods_dir: Path | None = None,
) -> VortexEnableSnapshot:
    """Sondea Vortex en solo lectura y clasifica fiabilidad.

    - No lee LevelDB (state.v2) → enablement actual = no verificado.
    - Si hay hourly/daily, rellena mapa histórico etiquetado como backup.
    - Si se pasa mods_dir, comprueba vortex.deployment.json en disco (hecho aparte).
    """
    game_id = vortex_game_id or LEGACY_FF7R_VORTEX_ID
    snap = VortexEnableSnapshot(
        reliability=VortexReliability.UNKNOWN,
        game_id=game_id or "",
        ui_current_label="Estado Vortex actual no verificado",
    )
    if not game_id:
        snap.message = "Este juego no tiene vortex_game_id configurado."
        return snap

    live = find_vortex_live_state_dir(roaming)
    if live:
        snap.live_state_present = True
        snap.live_state_dir = str(live)
        snap.live_state_mtime_iso = _iso_mtime(live)
        snap.live_state_readable = False  # LevelDB sin parser en este producto

    if mods_dir is not None:
        dep = Path(mods_dir) / "vortex.deployment.json"
        snap.deployment_path = str(dep)
        snap.deployment_on_disk = dep.is_file()

    backup = find_vortex_state_backup(roaming)
    lines: list[str] = []
    lines.append("Estado Vortex actual no verificado.")
    if snap.live_state_present:
        lines.append(
            f"Hay directorio vivo state.v2 (LevelDB) "
            f"mtime={snap.live_state_mtime_iso or '?'}, "
            "pero no se puede leer enablement sin un lector LevelDB."
        )
    else:
        lines.append("No se encontró state.v2 (estado vivo Vortex).")

    if snap.deployment_on_disk is True:
        lines.append(
            f"Deploy en disco: SÍ ({snap.deployment_path}). "
            "Eso no equivale al mapa Enabled de la BD Vortex."
        )
    elif snap.deployment_on_disk is False:
        lines.append(
            "Deploy en disco: no (sin vortex.deployment.json). "
            "Esto NO demuestra que todos los mods estén Disabled en Vortex."
        )

    if not backup:
        lines.append("No hay backup JSON histórico (hourly/daily) disponible.")
        snap.message = "\n".join(lines)
        return snap

    enabled_map, pname, pid, err = _parse_enable_map_from_backup(backup, game_id)
    snap.source_path = str(backup)
    snap.source_mtime_iso = _iso_mtime(backup)
    snap.source_kind = backup.name
    if err:
        lines.append(f"Backup histórico {backup.name}: {err}")
        snap.message = "\n".join(lines)
        return snap

    snap.reliability = VortexReliability.HISTORICAL_BACKUP
    snap.enabled_map = enabled_map
    snap.profile_name = pname
    snap.profile_id = pid
    snap.enabled_count = sum(1 for v in enabled_map.values() if v)
    snap.disabled_count = len(enabled_map) - snap.enabled_count
    snap.ui_historical_label = (
        f"Backup histórico {backup.name} "
        f"({snap.source_mtime_iso}): "
        f"Enabled={snap.enabled_count} · Disabled/otros={snap.disabled_count} · "
        f"perfil «{pname}»"
    )
    lines.append(
        "NO usar como estado actual. " + snap.ui_historical_label
    )
    snap.message = "\n".join(lines)
    return snap


def load_vortex_enable_map(
    vortex_game_id: str | None = None,
    *,
    roaming: Path | None = None,
    mods_dir: Path | None = None,
) -> tuple[dict[str, bool], str]:
    """API compat: (mapa, mensaje). El mapa puede ser histórico; el mensaje lo aclara.

    Preferir ``probe_vortex_enable_state`` en código nuevo.
    """
    snap = probe_vortex_enable_state(
        vortex_game_id, roaming=roaming, mods_dir=mods_dir
    )
    return dict(snap.enabled_map), snap.message


def format_vortex_status_report(snap: VortexEnableSnapshot) -> str:
    lines = [
        "=== Estado Vortex (solo lectura) ===",
        f"Fiabilidad enablement: {snap.reliability.value}",
        f"Etiqueta UI: {snap.ui_current_label}",
        "",
        snap.message,
        "",
        "Capas independientes:",
        "  • Plan del gestor (usar SI/NO) — no se modifica aquí.",
        "  • Destino del juego (archivos en ~mods / deploy) — hecho de disco.",
        "  • Backup hourly/daily — histórico, no actual.",
        "  • state.v2 LevelDB — vivo, no leído por este gestor.",
    ]
    if snap.ui_historical_label:
        lines.append("")
        lines.append(snap.ui_historical_label)
    return "\n".join(lines)


def apply_vortex_enablement(
    mods: list[ModEntry],
    vortex_game_id: str | None = None,
    *,
    roaming: Path | None = None,
    mods_dir: Path | None = None,
    allow_historical: bool = False,
) -> tuple[int, int, str]:
    """Aplica flags Vortex al plan del gestor (usar).

    Por defecto NO aplica backups históricos (evitar tratarlos como estado actual).
    Requiere ``allow_historical=True`` y confirmación explícita en UI.
    No toca Vortex ni el juego.
    """
    snap = probe_vortex_enable_state(
        vortex_game_id, roaming=roaming, mods_dir=mods_dir
    )
    if snap.reliability == VortexReliability.UNKNOWN and not snap.enabled_map:
        return 0, 0, snap.message

    if snap.reliability == VortexReliability.HISTORICAL_BACKUP and not allow_historical:
        return (
            0,
            0,
            snap.message
            + "\n\nImportación al plan BLOQUEADA: la fuente es un backup histórico, "
            "no el estado Vortex actual. "
            "Si quieres importar ese snapshot al plan del gestor, confírmalo "
            "explícitamente (no se ha modificado usar).",
        )

    if snap.reliability != VortexReliability.CURRENT and not allow_historical:
        return 0, 0, snap.message + "\n\nPlan del gestor no modificado."

    enabled_map = snap.enabled_map
    on = off = 0
    for m in mods:
        m.usar = bool(enabled_map.get(m.folder, False))
        if m.usar:
            on += 1
        else:
            off += 1
    prefix = (
        "IMPORTADO DESDE BACKUP HISTÓRICO (no verificado como actual).\n"
        if snap.reliability == VortexReliability.HISTORICAL_BACKUP
        else ""
    )
    return on, off, prefix + snap.message


def disable_all(mods: list[ModEntry]) -> None:
    for m in mods:
        m.usar = False
