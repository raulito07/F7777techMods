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

Prioridades y resoluciones manuales por juego (persistentes).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_priorities(path: Path | None) -> dict[str, int]:
    if not path or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        files = raw.get("priorities") if isinstance(raw, dict) else raw
        if not isinstance(files, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in files.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


def save_priorities(path: Path, priorities: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "priorities": {k: int(v) for k, v in priorities.items()}}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_resolutions(path: Path | None) -> dict[str, dict]:
    """dest_key → {winner_folder, mode}."""
    if not path or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("resolutions") if isinstance(raw, dict) else {}
        if not isinstance(items, dict):
            return {}
        out: dict[str, dict] = {}
        for k, v in items.items():
            if isinstance(v, dict) and v.get("winner_folder"):
                out[str(k)] = {
                    "winner_folder": str(v["winner_folder"]),
                    "mode": str(v.get("mode") or "manual"),
                }
            elif isinstance(v, str):
                out[str(k)] = {"winner_folder": v, "mode": "manual"}
        return out
    except Exception:
        return {}


def save_resolutions(path: Path, resolutions: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "resolutions": resolutions}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def set_resolution(
    resolutions: dict[str, dict],
    dest_key: str,
    winner_folder: str,
    *,
    mode: str = "manual",
) -> None:
    resolutions[dest_key] = {"winner_folder": winner_folder, "mode": mode}


def clear_resolution(resolutions: dict[str, dict], dest_key: str) -> None:
    resolutions.pop(dest_key, None)
