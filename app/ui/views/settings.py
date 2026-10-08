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

S06 — panel Juegos y ajustes.
"""

from __future__ import annotations

import customtkinter as ctk

from ...branding import PRODUCT_NAME
from ...version import __version__, __company__
from ..theme import COLORS


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(
            self, text="Juegos y ajustes", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(anchor="w", padx=8, pady=8)

        games = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        games.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(games, text="Gestión de juegos", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        row = ctk.CTkFrame(games, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=6)
        ctk.CTkButton(row, text="Añadir juego", command=app.add_game_dialog).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text="Editar carpetas", command=app.edit_game_dialog).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            row, text="Quitar del registro", fg_color="#6c757d", command=app.remove_game_dialog
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            row,
            text="Migración FF7R…",
            fg_color=COLORS["btn_secondary"],
            command=app.migration_dialog,
        ).pack(side="left", padx=4)

        self.profile = ctk.CTkTextbox(games, height=120, wrap="word")
        self.profile.pack(fill="x", padx=14, pady=(4, 14))

        storage = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        storage.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(
            storage, text="Almacenamiento S09 (COPY / HARDLINK / AUTO)", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            storage,
            text=(
                "Vortex conserva downloads/staging. El gestor instala al destino.\n"
                "Hardlinks comparten datos físicos con staging — integridad Vortex > ahorro.\n"
                "No se usan symlinks. Backups siempre en copia independiente."
            ),
            text_color=COLORS["text_muted"],
            justify="left",
            wraplength=900,
        ).pack(anchor="w", padx=14, pady=(0, 6))
        self.install_mode_label = ctk.CTkLabel(storage, text="Modo: COPY")
        self.install_mode_label.pack(anchor="w", padx=14, pady=2)
        srow = ctk.CTkFrame(storage, fg_color="transparent")
        srow.pack(fill="x", padx=14, pady=(4, 14))
        ctk.CTkButton(srow, text="COPY", width=80, command=lambda: app.set_install_mode("COPY")).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            srow, text="HARDLINK", width=90, command=lambda: app.set_install_mode("HARDLINK")
        ).pack(side="left", padx=2)
        ctk.CTkButton(srow, text="AUTO", width=80, command=lambda: app.set_install_mode("AUTO")).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            srow, text="Informe almacenamiento", command=app.show_storage_report
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            srow, text="Revisar cambios staging", command=app.review_staging_changes
        ).pack(side="left", padx=4)

        src = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        src.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(
            src,
            text="Fuente predeterminada de mods (S15)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            src,
            text=(
                "STAGING_VORTEX = carpeta Vortex · WORK_LIBRARY = biblioteca propia.\n"
                "No se mezclan rutas silenciosamente. Plan ≠ instalado."
            ),
            text_color=COLORS["text_muted"],
            justify="left",
            wraplength=900,
        ).pack(anchor="w", padx=14, pady=(0, 6))
        self.default_source_label = ctk.CTkLabel(src, text="Fuente: STAGING_VORTEX")
        self.default_source_label.pack(anchor="w", padx=14, pady=2)
        srow2 = ctk.CTkFrame(src, fg_color="transparent")
        srow2.pack(fill="x", padx=14, pady=(4, 14))
        ctk.CTkButton(
            srow2,
            text="Vortex staging",
            width=120,
            command=lambda: app.set_default_mod_source("STAGING_VORTEX"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            srow2,
            text="WORK_LIBRARY",
            width=120,
            command=lambda: app.set_default_mod_source("WORK_LIBRARY"),
        ).pack(side="left", padx=2)

        visual = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        visual.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(visual, text="Ajustes visuales", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        zrow = ctk.CTkFrame(visual, fg_color="transparent")
        zrow.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(zrow, text="Zoom").pack(side="left", padx=(0, 8))
        ctk.CTkButton(zrow, text="A−", width=44, command=app.zoom_out).pack(side="left", padx=2)
        self.zoom_label = ctk.CTkLabel(zrow, text=f"{app.zoom}%", width=54)
        self.zoom_label.pack(side="left", padx=4)
        ctk.CTkButton(zrow, text="A+", width=44, command=app.zoom_in).pack(side="left", padx=2)
        ctk.CTkButton(zrow, text="Reset", width=60, command=app.zoom_reset).pack(side="left", padx=2)

        trow = ctk.CTkFrame(visual, fg_color="transparent")
        trow.pack(fill="x", padx=14, pady=(4, 14))
        ctk.CTkLabel(trow, text="Tema").pack(side="left", padx=(0, 8))
        ctk.CTkButton(trow, text="Oscuro", width=80, command=lambda: app.set_appearance("dark")).pack(
            side="left", padx=2
        )
        ctk.CTkButton(trow, text="Claro", width=80, command=lambda: app.set_appearance("light")).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            trow, text="Sistema", width=80, command=lambda: app.set_appearance("system")
        ).pack(side="left", padx=2)

        ops = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        ops.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(ops, text="Operaciones del plan", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        orow = ctk.CTkFrame(ops, fg_color="transparent")
        orow.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(
            orow, text="Consultar Vortex", command=app.sync_from_vortex
        ).pack(side="left", padx=4)
        ctk.CTkButton(orow, text="Desactivar todo", fg_color="#6c757d", command=app.disable_all_mods).pack(
            side="left", padx=4
        )
        ctk.CTkButton(orow, text="Guardar plan", command=app.save_plan).pack(side="left", padx=4)
        ctk.CTkButton(
            orow, text="Ir a Historial / backups", command=lambda: app.show_view("history")
        ).pack(side="left", padx=4)

        about = ctk.CTkLabel(
            self,
            text=(
                f"{__company__} — {PRODUCT_NAME} v{__version__}\n"
                "Identidad y enlaces: panel «Acerca de».\n"
                "Las rutas no se pueden editar durante una instalación en curso.\n"
                "Ctrl + rueda / Ctrl+/- / Ctrl+0 = zoom."
            ),
            text_color=COLORS["text_muted"],
            justify="left",
        )
        about.pack(anchor="w", padx=12, pady=12)

    def refresh(self) -> None:
        app = self.app
        self.zoom_label.configure(text=f"{app.zoom}%")
        mode = "COPY"
        if app.session:
            mode = str(getattr(app.session.record, "install_mode", None) or "COPY")
        self.install_mode_label.configure(
            text=(
                f"Modo actual: {mode}  ·  "
                "Vortex enablement: no verificado como estado actual"
            )
        )
        src = "STAGING_VORTEX"
        if app.session:
            src = str(
                getattr(app.session.record, "default_mod_source", None)
                or "STAGING_VORTEX"
            )
        if hasattr(self, "default_source_label"):
            self.default_source_label.configure(text=f"Fuente: {src}")
        self.profile.configure(state="normal")
        self.profile.delete("1.0", "end")
        if not app.session:
            self.profile.insert("1.0", "Sin juego activo.")
        else:
            r = app.session.record
            self.profile.insert(
                "1.0",
                (
                    f"Nombre: {r.name}\n"
                    f"Id: {r.id}\n"
                    f"Adaptador: {r.adapter}\n"
                    f"Instalación S09: {getattr(r, 'install_mode', 'COPY') or 'COPY'}\n"
                    f"Fuente mods S15: {src}\n"
                    f"Staging: {app.session.stage_dir}\n"
                    f"Destino: {app.session.mods_dir}\n"
                    f"Downloads: {r.downloads_dir or '(no configurado)'}\n"
                    f"Datos: {app.session.data_dir}\n"
                    f"Vortex gameId: {r.vortex_game_id or '(ninguno)'}\n"
                    f"Migración: {r.migration_status}"
                ),
            )
        self.profile.configure(state="disabled")
