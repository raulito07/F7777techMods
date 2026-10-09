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
"""

from __future__ import annotations

import json
from pathlib import Path

from .inventory import ModEntry
from .paths import LOADOUT_JSON, DATA


def load_loadout(path: Path | None = None) -> dict[str, dict]:
    p = path if path is not None else LOADOUT_JSON
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_loadout(mods: list[ModEntry], path: Path | None = None) -> None:
    p = path if path is not None else LOADOUT_JSON
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for m in mods:
        entry = {
            "usar": m.usar,
            "pak_elegido": m.pak_elegido,
            "paks_elegidos": list(getattr(m, "paks_elegidos", None) or []),
            "selection_mode": str(getattr(m, "selection_mode", "") or ""),
        }
        data[m.folder] = entry
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_loadout(mods: list[ModEntry], path: Path | None = None) -> None:
    saved = load_loadout(path)
    from .package_identity import migrate_package_loadout

    # Primero migración S37 carpeta→componentes S38, luego claves directas
    migrate_package_loadout(mods, saved)
    for m in mods:
        if m.folder in saved:
            m.usar = bool(saved[m.folder].get("usar", m.usar))
            many = saved[m.folder].get("paks_elegidos")
            if isinstance(many, list) and many:
                from .component_selection import set_selected_paks

                set_selected_paks(m, [str(x) for x in many])
            else:
                pak = saved[m.folder].get("pak_elegido") or ""
                if pak:
                    m.pak_elegido = pak
                    m.paks_elegidos = [pak] if pak in m.paks or any(
                        p.lower() == pak.lower() for p in m.paks
                    ) else ([pak] if pak else [])
                elif not m.multi and m.paks:
                    m.pak_elegido = m.paks[0]
                    m.paks_elegidos = [m.paks[0]]
            mode = saved[m.folder].get("selection_mode") or ""
            if mode:
                m.selection_mode = str(mode)
