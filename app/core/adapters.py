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

Perfiles/adaptadores oficiales por tipo de juego.

S50: aportaciones comunitarias van en JSON (`community_adapters/`) vía
`community_adapter_*`. Este registro oficial no se sustituye por JSON
y sigue siendo el único que alimenta flags del motor Apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameAdapter:
    id: str
    label: str
    """Subruta sugerida bajo game_root para mods (puede ser vacía)."""
    suggest_mods_subdir: str
    """Si True, el inventario prioriza .pak (comportamiento FF7R)."""
    pak_centric: bool = False
    """Heurísticas semánticas por nombre (slots FF7R). No heredar en genéricos."""
    semantic_slots: bool = False
    """UE5 IoStore: instalar .pak + .utoc + .ucas del mismo stem."""
    iostore_sidecars: bool = False
    notes: str = ""


ADAPTERS: dict[str, GameAdapter] = {
    "generic_folder": GameAdapter(
        id="generic_folder",
        label="Carpeta libre (cualquier destino)",
        suggest_mods_subdir="",
        pak_centric=False,
        semantic_slots=False,
        iostore_sidecars=False,
        notes="El usuario elige el directorio exacto de instalación de mods.",
    ),
    "ue4_paks_mods": GameAdapter(
        id="ue4_paks_mods",
        label="Unreal Engine 4 — Paks/~mods (FF7 Remake)",
        suggest_mods_subdir="End/Content/Paks/~mods",
        pak_centric=True,
        semantic_slots=True,
        iostore_sidecars=False,
        notes=(
            "FF7 Remake: solo .pak → ~mods. "
            "Slots semánticos FF7R. Docs/desconocidos no se copian (S08)."
        ),
    ),
    "ue5_iostore_mods": GameAdapter(
        id="ue5_iostore_mods",
        label="Unreal Engine 5 — IoStore Paks/~mods",
        suggest_mods_subdir="End/Content/Paks/~mods",
        pak_centric=True,
        semantic_slots=False,
        iostore_sidecars=True,
        notes=(
            "UE5 (FF7 Rebirth / similares): .pak + .utoc + .ucas → ~mods. "
            "Sin slots semánticos de Remake. No analiza interior de paquetes."
        ),
    ),
}

KNOWN_ADAPTER_IDS = frozenset(ADAPTERS.keys())

DEFAULT_ADAPTER_ID = "generic_folder"


def get_adapter(adapter_id: str) -> GameAdapter:
    return ADAPTERS.get(adapter_id) or ADAPTERS[DEFAULT_ADAPTER_ID]


def suggest_mods_dir(game_root: Path, adapter_id: str) -> Path:
    ad = get_adapter(adapter_id)
    if not ad.suggest_mods_subdir:
        return game_root
    return game_root.joinpath(*Path(ad.suggest_mods_subdir).parts)


def adapter_choices() -> list[str]:
    return [f"{a.id} — {a.label}" for a in ADAPTERS.values()]


def adapter_id_from_choice(choice: str) -> str:
    return (choice.split(" — ", 1)[0] or DEFAULT_ADAPTER_ID).strip()
