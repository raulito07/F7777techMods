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

S21/S22 — panel Acerca de (identidad, GPL v3, enlaces oficiales).
"""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from ...branding import (
    AUTHOR_NAME,
    COMPANY_NAME,
    COPYRIGHT_LINE,
    INDEPENDENT_APP_NOTICE,
    LICENSE_NAME,
    LICENSE_SHORT,
    LICENSE_URL,
    OFFICIAL_GITHUB_URL,
    OFFICIAL_RELEASES_URL,
    PRODUCT_BYLINE,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    configured_links,
)
from ...version import __version__
from ..theme import COLORS


class AboutView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(
            self,
            text="Acerca de",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=8, pady=(8, 4))

        card = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        card.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(
            card,
            text=PRODUCT_NAME,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            card,
            text=PRODUCT_BYLINE,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(
            card,
            text=PRODUCT_TAGLINE,
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(
            card,
            text=f"Versión {__version__} Beta",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=18, pady=(8, 4))

        meta = (
            f"Empresa: {COMPANY_NAME}\n"
            f"Autor: {AUTHOR_NAME}\n"
            f"{COPYRIGHT_LINE}\n"
            f"Licencia: {LICENSE_NAME} ({LICENSE_SHORT})"
        )
        ctk.CTkLabel(
            card, text=meta, justify="left", text_color=COLORS["text"]
        ).pack(anchor="w", padx=18, pady=8)

        ctk.CTkLabel(
            card,
            text=INDEPENDENT_APP_NOTICE,
            wraplength=720,
            justify="left",
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=18, pady=(4, 8))

        lic_row = ctk.CTkFrame(card, fg_color="transparent")
        lic_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            lic_row,
            text=f"Software libre bajo {LICENSE_SHORT}. "
            "Código fuente: ver LICENSE y el repositorio cuando esté publicado.",
            wraplength=700,
            justify="left",
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            lic_row,
            text="Texto GPL v3",
            width=120,
            command=lambda: webbrowser.open(LICENSE_URL),
        ).pack(side="left", padx=4)

        links_fr = ctk.CTkFrame(card, fg_color="transparent")
        links_fr.pack(fill="x", padx=14, pady=(4, 16))
        ctk.CTkLabel(
            links_fr,
            text="Enlaces oficiales",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=4, pady=(0, 6))

        links = configured_links()
        for label, url in links:
            ctk.CTkButton(
                links_fr,
                text=label,
                width=160,
                command=lambda u=url: webbrowser.open(u),
            ).pack(side="left", padx=4, pady=4)
        pending = []
        if not OFFICIAL_GITHUB_URL.strip():
            pending.append("GitHub")
        if not OFFICIAL_RELEASES_URL.strip():
            pending.append("Releases")
        if pending:
            ctk.CTkLabel(
                links_fr,
                text=(
                    " / ".join(pending)
                    + ": pendientes de URL real (no se muestran enlaces ficticios)."
                ),
                text_color=COLORS["text_muted"],
                wraplength=520,
                justify="left",
            ).pack(side="left", padx=8)

    def refresh(self) -> None:
        return
