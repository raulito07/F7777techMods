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

S06 — tokens de color y tipografía (tema claro/oscuro).
"""

from __future__ import annotations

# Pares (light, dark) para CustomTkinter
COLORS = {
    "bg_app": ("#eef1f6", "#0f1419"),
    "bg_sidebar": ("#e2e8f0", "#121a24"),
    "bg_header": ("#d8dee9", "#1a2332"),
    "bg_card": ("#ffffff", "#1a222d"),
    "bg_muted": ("#f1f5f9", "#15202b"),
    "text": ("#0f172a", "#e8eef7"),
    "text_muted": ("#475569", "#9aa8b8"),
    "accent": ("#1d4ed8", "#3b82f6"),
    "nav_active": ("#bfdbfe", "#1e3a5f"),
    "ok": ("#166534", "#4ade80"),
    "warn": ("#a16207", "#fbbf24"),
    "danger": ("#b91c1c", "#f87171"),
    "active": ("#15803d", "#22c55e"),
    "inactive": ("#64748b", "#64748b"),
    "installed": ("#0369a1", "#38bdf8"),
    "btn_apply": ("#166534", "#2d6a4f"),
    "btn_secondary": ("#334155", "#3d405b"),
    "btn_warn": ("#9a3412", "#7f5539"),
}

NAV_ITEMS = [
    ("summary", "Resumen"),
    ("library", "Biblioteca"),
    ("conflicts", "Conflictos"),
    ("installed", "Instalados"),
    ("storage", "Almacenamiento"),
    ("history", "Historial"),
    ("settings", "Juegos y ajustes"),
    ("about", "Acerca de"),
]

# Biblioteca: filas por página (virtualización ligera)
LIBRARY_PAGE_SIZE = 80
