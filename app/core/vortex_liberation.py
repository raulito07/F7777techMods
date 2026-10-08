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

S16 — observación solo lectura del comportamiento Vortex ante liberación
de staging. No modifica state.v2, LevelDB ni Downloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .vortex_sync import (
    VortexEnableSnapshot,
    VortexReliability,
    probe_vortex_enable_state,
)

# ---------------------------------------------------------------------------
# Hallazgos observados / documentados (solo lectura; sin mutar Vortex)
# ---------------------------------------------------------------------------

VORTEX_BEHAVIOR_FINDINGS: list[str] = [
    "Vortex registra mods instalados en su estado vivo (state.v2 / LevelDB) "
    "y en perfiles (modState: enabled/disabled por carpeta de staging).",
    "Este gestor NO parsea LevelDB: el enablement actual permanece "
    "«no verificado». Los JSON hourly/daily son backups históricos.",
    "La carpeta de staging bajo el stagingPath del juego es el contenido "
    "extraído que Vortex usa para Deploy; borrarla a mano deja el mod "
    "como missing/broken en Vortex sin Uninstall oficial.",
    "Uninstall desde la UI de Vortex retira el mod del perfil y suele "
    "eliminar la carpeta de staging; los archivos en Downloads a menudo "
    "permanecen (reinstalables desde el archivo descargado).",
    "Purge/Deploy actúan sobre el destino del juego, no sustituyen "
    "Uninstall del staging.",
    "El seguimiento de versiones Nexus vive en metadatos Vortex; borrar "
    "staging sin Uninstall puede romper actualizaciones y redeploy.",
    "Juego desinstalado: el staging y el perfil pueden seguir en disco; "
    "el riesgo de inconsistencia Vortex permanece si se borran carpetas "
    "sin el flujo oficial.",
    "Operaciones oficiales para retirar extraídos: Uninstall (mod), "
    "Remove (según UI), Purge (destino). Ninguna está automatizada aquí.",
    "Modificar state.v2 / LevelDB directamente se considera inseguro e "
    "incompatible; queda prohibido en este producto.",
]

STRATEGY_COMPARISON: list[dict[str, str]] = [
    {
        "id": "VORTEX_UI_UNINSTALL",
        "name": "Desinstalación mediante interfaz de Vortex",
        "preserves_vortex": "Sí (vía oficial)",
        "reclaims_staging": "Sí (habitualmente)",
        "keeps_downloads": "Sí (habitualmente)",
        "automatable_here": "No",
        "verdict": "Recomendado cuando el mod sigue gestionado por Vortex.",
    },
    {
        "id": "MANUAL_AFTER_VORTEX",
        "name": "Retirada manual tras Uninstall confirmado",
        "preserves_vortex": "Solo si Uninstall ya quitó el registro",
        "reclaims_staging": "Solo restos huérfanos verificados",
        "keeps_downloads": "N/A",
        "automatable_here": "No en S16 (sin borrado real)",
        "verdict": "Pendiente de autorización futura; nunca sin confirmación.",
    },
    {
        "id": "GESTOR_INDEPENDENT",
        "name": "Biblioteca propia independiente (ARCHIVO_PROPIO + WORK)",
        "preserves_vortex": "Sí (no toca staging ni DB)",
        "reclaims_staging": "No (staging Vortex intacto)",
        "keeps_downloads": "N/A",
        "automatable_here": "Sí (restore/plan/Apply sandbox)",
        "verdict": "Camino seguro del gestor mientras Vortex siga activo.",
    },
    {
        "id": "DIRECT_LEVELDB",
        "name": "Modificación directa LevelDB / state.v2",
        "preserves_vortex": "No (alto riesgo de corrupción)",
        "reclaims_staging": "No por sí sola",
        "keeps_downloads": "N/A",
        "automatable_here": "Prohibido",
        "verdict": "BLOQUEADO permanentemente.",
    },
]


class VortexStagingRisk(str, Enum):
    NONE = "ninguno"
    UNKNOWN = "desconocido"
    REGISTERED_ENABLED = "registrado_enabled"
    REGISTERED_DISABLED = "registrado_disabled"
    STAGING_PRESENT_UNTRACKED = "staging_presente_sin_mapa"
    LIVE_STATE_UNREADABLE = "state_v2_no_legible"
    GAME_UNINSTALLED_STAGING_LEFT = "juego_desinstalado_staging_resta"


@dataclass
class VortexLiberationAssessment:
    folder: str
    risk: VortexStagingRisk
    staging_exists: bool
    in_historical_map: bool | None  # None = sin mapa
    historically_enabled: bool | None
    live_state_present: bool
    reliability: str
    recommended_method: str
    instructions: str
    notes: list[str] = field(default_factory=list)


def assess_vortex_for_mod(
    folder: str,
    *,
    staging_exists: bool,
    snap: VortexEnableSnapshot | None,
    game_installed: bool = True,
) -> VortexLiberationAssessment:
    """Clasifica dependencia Vortex de un mod (solo lectura)."""
    notes: list[str] = []
    reliability = (
        snap.reliability.value if snap else VortexReliability.UNKNOWN.value
    )
    live = bool(snap and snap.live_state_present)
    in_map: bool | None = None
    hist_en: bool | None = None
    if snap and snap.enabled_map:
        in_map = folder in snap.enabled_map
        if in_map:
            hist_en = bool(snap.enabled_map[folder])

    if not staging_exists:
        return VortexLiberationAssessment(
            folder=folder,
            risk=VortexStagingRisk.NONE,
            staging_exists=False,
            in_historical_map=in_map,
            historically_enabled=hist_en,
            live_state_present=live,
            reliability=reliability,
            recommended_method="GESTOR_INDEPENDENT",
            instructions=(
                "No hay carpeta de staging. Espacio de staging ya liberado "
                "o nunca extraído. Usar ARCHIVO_PROPIO + WORK_LIBRARY."
            ),
            notes=notes,
        )

    if not game_installed:
        notes.append(
            "Juego marcado como desinstalado; staging puede quedar en disco."
        )
        risk = VortexStagingRisk.GAME_UNINSTALLED_STAGING_LEFT
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Aunque el juego no esté instalado, retire el mod desde Vortex "
            "(Uninstall) antes de cualquier limpieza manual de restos."
        )
        return VortexLiberationAssessment(
            folder=folder,
            risk=risk,
            staging_exists=True,
            in_historical_map=in_map,
            historically_enabled=hist_en,
            live_state_present=live,
            reliability=reliability,
            recommended_method=method,
            instructions=instr,
            notes=notes,
        )

    if live:
        notes.append("state.v2 presente pero no legible por este gestor.")

    if in_map is True and hist_en is True:
        risk = VortexStagingRisk.REGISTERED_ENABLED
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Backup histórico: mod Enabled. Desinstale desde Vortex. "
            "No borrar staging desde el gestor."
        )
    elif in_map is True and hist_en is False:
        risk = VortexStagingRisk.REGISTERED_DISABLED
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Backup histórico: mod Disabled pero staging presente. "
            "Use Uninstall en Vortex para retirar el registro y el staging; "
            "no elimine carpetas a mano."
        )
    elif in_map is False:
        risk = VortexStagingRisk.STAGING_PRESENT_UNTRACKED
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Staging en disco sin entrada en el backup histórico disponible. "
            "Tratar como dependencia Vortex posible → no liberable por gestor."
        )
    elif live:
        risk = VortexStagingRisk.LIVE_STATE_UNREADABLE
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Estado Vortex actual no verificado (LevelDB). "
            "Asuma dependencia hasta Uninstall confirmado en la UI de Vortex."
        )
    else:
        risk = VortexStagingRisk.UNKNOWN
        method = "VORTEX_UI_UNINSTALL"
        instr = (
            "Estado Vortex desconocido y staging presente. "
            "Bloquear borrado; preferir Uninstall oficial o biblioteca propia."
        )

    return VortexLiberationAssessment(
        folder=folder,
        risk=risk,
        staging_exists=True,
        in_historical_map=in_map,
        historically_enabled=hist_en,
        live_state_present=live,
        reliability=reliability,
        recommended_method=method,
        instructions=instr,
        notes=notes,
    )


def probe_for_liberation(
    vortex_game_id: str | None,
    *,
    roaming: Path | None = None,
    mods_dir: Path | None = None,
) -> VortexEnableSnapshot:
    """Sondeo solo lectura reutilizando S08."""
    return probe_vortex_enable_state(
        vortex_game_id, roaming=roaming, mods_dir=mods_dir
    )


def format_vortex_research_summary() -> str:
    lines = [
        "=== Comportamiento Vortex (investigación solo lectura) ===",
        "",
    ]
    for i, f in enumerate(VORTEX_BEHAVIOR_FINDINGS, 1):
        lines.append(f"{i}. {f}")
    lines.append("")
    lines.append("=== Estrategias de retirada (comparación) ===")
    for s in STRATEGY_COMPARISON:
        lines.append(f"— {s['name']} [{s['id']}]")
        lines.append(f"    Consistencia Vortex: {s['preserves_vortex']}")
        lines.append(f"    Recupera staging: {s['reclaims_staging']}")
        lines.append(f"    Automatizable aquí: {s['automatable_here']}")
        lines.append(f"    Veredicto: {s['verdict']}")
    lines.append("")
    lines.append(
        "Conclusión S16: no hay método automatizado seguro de borrado de "
        "staging mientras Vortex pueda depender de él. Ejecución de "
        "eliminación: NO DISPONIBLE."
    )
    return "\n".join(lines)
