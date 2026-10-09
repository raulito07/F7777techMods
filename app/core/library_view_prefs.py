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

S45/S46 — preferencias Biblioteca: paginación, layout y tarjetas.
"""

from __future__ import annotations

import json
from typing import TypeVar

from .paths import UI_SETTINGS_JSON

MODE_PAGINATED = "paginated"
MODE_FULL = "full"

UI_LABEL_PAGINATED = "PAGINADA"
UI_LABEL_FULL = "COMPLETA"

UI_TO_MODE = {
    UI_LABEL_PAGINATED: MODE_PAGINATED,
    UI_LABEL_FULL: MODE_FULL,
}
MODE_TO_UI = {v: k for k, v in UI_TO_MODE.items()}

LARGE_LIST_HINT_THRESHOLD = 500
TREE_INSERT_BATCH = 80
VISUAL_INSERT_BATCH = 48

LAYOUT_TABLE = "table"
LAYOUT_CATALOG = "catalog"
LAYOUT_VISUAL_LIST = "visual_list"

UI_LAYOUT_TABLE = "TABLA"
UI_LAYOUT_CATALOG = "CATÁLOGO"
UI_LAYOUT_VISUAL = "LISTA VISUAL"

UI_TO_LAYOUT = {
    UI_LAYOUT_TABLE: LAYOUT_TABLE,
    UI_LAYOUT_CATALOG: LAYOUT_CATALOG,
    UI_LAYOUT_VISUAL: LAYOUT_VISUAL_LIST,
}
LAYOUT_TO_UI = {v: k for k, v in UI_TO_LAYOUT.items()}

CARD_SMALL = "small"
CARD_MEDIUM = "medium"
CARD_LARGE = "large"

UI_CARD_SMALL = "Pequeña"
UI_CARD_MEDIUM = "Mediana"
UI_CARD_LARGE = "Grande"

UI_TO_CARD = {
    UI_CARD_SMALL: CARD_SMALL,
    UI_CARD_MEDIUM: CARD_MEDIUM,
    UI_CARD_LARGE: CARD_LARGE,
}
CARD_TO_UI = {v: k for k, v in UI_TO_CARD.items()}

CARD_DIMS = {
    CARD_SMALL: (100, 72, 140),
    CARD_MEDIUM: (128, 96, 168),
    CARD_LARGE: (160, 120, 200),
}

T = TypeVar("T")


def load_library_view_mode(game_id: str, *, settings_path=None) -> str:
    path = settings_path or UI_SETTINGS_JSON
    if not path.exists():
        return MODE_PAGINATED
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        by_game = data.get("library_view_by_game") or {}
        if game_id and game_id in by_game:
            m = str(by_game[game_id])
            return m if m in (MODE_PAGINATED, MODE_FULL) else MODE_PAGINATED
        default = str(data.get("library_view_default") or MODE_PAGINATED)
        return default if default in (MODE_PAGINATED, MODE_FULL) else MODE_PAGINATED
    except Exception:
        return MODE_PAGINATED


def _read_settings(path) -> dict:
    payload: dict = {}
    try:
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                payload = old
    except Exception:
        pass
    return payload


def _write_settings(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_library_layout(game_id: str, *, settings_path=None) -> str:
    path = settings_path or UI_SETTINGS_JSON
    data = _read_settings(path)
    by_game = data.get("library_layout_by_game") or {}
    if game_id and game_id in by_game:
        v = str(by_game[game_id])
        if v in (LAYOUT_TABLE, LAYOUT_CATALOG, LAYOUT_VISUAL_LIST):
            return v
    default = str(data.get("library_layout_default") or LAYOUT_TABLE)
    return default if default in (LAYOUT_TABLE, LAYOUT_CATALOG, LAYOUT_VISUAL_LIST) else LAYOUT_TABLE


def save_library_layout(game_id: str, layout: str, *, settings_path=None) -> None:
    if layout not in (LAYOUT_TABLE, LAYOUT_CATALOG, LAYOUT_VISUAL_LIST):
        layout = LAYOUT_TABLE
    path = settings_path or UI_SETTINGS_JSON
    payload = _read_settings(path)
    by_game = dict(payload.get("library_layout_by_game") or {})
    if game_id:
        by_game[game_id] = layout
    payload["library_layout_by_game"] = by_game
    payload.setdefault("library_layout_default", LAYOUT_TABLE)
    _write_settings(path, payload)


def load_library_card_size(game_id: str, *, settings_path=None) -> str:
    path = settings_path or UI_SETTINGS_JSON
    data = _read_settings(path)
    by_game = data.get("library_card_size_by_game") or {}
    if game_id and game_id in by_game:
        v = str(by_game[game_id])
        if v in (CARD_SMALL, CARD_MEDIUM, CARD_LARGE):
            return v
    return CARD_MEDIUM


def save_library_card_size(game_id: str, size: str, *, settings_path=None) -> None:
    if size not in (CARD_SMALL, CARD_MEDIUM, CARD_LARGE):
        size = CARD_MEDIUM
    path = settings_path or UI_SETTINGS_JSON
    payload = _read_settings(path)
    by_game = dict(payload.get("library_card_size_by_game") or {})
    if game_id:
        by_game[game_id] = size
    payload["library_card_size_by_game"] = by_game
    _write_settings(path, payload)


def save_library_view_mode(
    game_id: str,
    mode: str,
    *,
    settings_path=None,
) -> None:
    if mode not in (MODE_PAGINATED, MODE_FULL):
        mode = MODE_PAGINATED
    path = settings_path or UI_SETTINGS_JSON
    payload = _read_settings(path)
    by_game = dict(payload.get("library_view_by_game") or {})
    if game_id:
        by_game[game_id] = mode
    payload["library_view_by_game"] = by_game
    payload.setdefault("library_view_default", MODE_PAGINATED)
    _write_settings(path, payload)


def display_slice(
    filtered: list[T],
    *,
    mode: str,
    page: int,
    page_size: int,
) -> list[T]:
    if mode == MODE_FULL:
        return list(filtered)
    ps = max(1, page_size)
    start = max(0, page) * ps
    return filtered[start : start + ps]


def list_summary_text(
    *,
    mode: str,
    total_filtered: int,
    page: int,
    page_size: int,
    total_in_memory: int,
) -> tuple[str, str, bool]:
    """(count_label, pager_hint, show_large_warning)."""
    mem = f"{total_in_memory} en memoria"
    if mode == MODE_FULL:
        head = f"Mostrando {total_filtered} resultados (vista completa) · {mem}"
        pager = ""
        warn = total_filtered > LARGE_LIST_HINT_THRESHOLD
        return head, pager, warn
    ps = max(1, page_size)
    max_page = max(0, (total_filtered - 1) // ps) if total_filtered else 0
    pg = min(max(0, page), max_page)
    head = (
        f"Página {pg + 1} de {max_page + 1} · {total_filtered} resultados filtrados · {mem}"
    )
    pager = f"{ps} por página"
    return head, pager, False
