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

S06 — panel Resumen.
"""

from __future__ import annotations

import customtkinter as ctk

from ...branding import COMPANY_NAME, PRODUCT_BYLINE, PRODUCT_NAME
from ...version import __version__
from ..theme import COLORS


class SummaryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.title = ctk.CTkLabel(
            self,
            text="Resumen",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
        )
        self.title.pack(anchor="w", padx=8, pady=(8, 4))
        self.brand = ctk.CTkLabel(
            self,
            text=f"{PRODUCT_NAME}  ·  {PRODUCT_BYLINE}  ·  v{__version__} Beta",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent"],
        )
        self.brand.pack(anchor="w", padx=8, pady=(0, 2))
        self.subtitle = ctk.CTkLabel(
            self,
            text=(
                "Estado del juego activo. "
                "Flujo: Actualizar → plan (Biblioteca) → Simular cambios → Aplicar cambios."
            ),
            text_color=COLORS["text_muted"],
        )
        self.subtitle.pack(anchor="w", padx=8, pady=(0, 12))

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=8, pady=4)
        self.card_game = self._card(cards, "Juego activo", "—")
        self.card_mods = self._card(cards, "Mods disponibles", "0")
        self.card_on = self._card(cards, "Activos en plan", "0")
        self.card_conf = self._card(cards, "Conflictos", "0")
        self.card_inst = self._card(cards, "En destino (disco)", "0")

        for i, c in enumerate(
            (self.card_game, self.card_mods, self.card_on, self.card_conf, self.card_inst)
        ):
            c.grid(row=0, column=i, padx=6, pady=6, sticky="nsew")
            cards.grid_columnconfigure(i, weight=1)

        self.body = ctk.CTkTextbox(self, wrap="word", height=280)
        self.body.pack(fill="both", expand=True, padx=8, pady=12)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            actions, text="Ir a Biblioteca", command=lambda: app.show_view("library")
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Ir a Conflictos",
            fg_color=COLORS["btn_warn"],
            command=lambda: app.show_view("conflicts"),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Simular cambios",
            fg_color=COLORS["btn_secondary"],
            command=app.simulate,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Subconjunto seguro",
            fg_color=COLORS["btn_secondary"],
            command=app.show_safe_subset,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Guía prueba Remake",
            fg_color=COLORS["btn_secondary"],
            command=app.show_remake_trial_guide,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions,
            text="Aplicar cambios",
            fg_color=COLORS["btn_apply"],
            command=app.apply_to_game,
        ).pack(side="left", padx=4)

    def _card(self, parent, label: str, value: str):
        fr = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        ctk.CTkLabel(fr, text=label, text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=14, pady=(12, 2)
        )
        val = ctk.CTkLabel(
            fr, text=value, font=ctk.CTkFont(size=22, weight="bold"), text_color=COLORS["text"]
        )
        val.pack(anchor="w", padx=14, pady=(0, 12))
        fr.value_label = val  # type: ignore[attr-defined]
        return fr

    def refresh(self) -> None:
        app = self.app
        if not app.session:
            self.card_game.value_label.configure(text="(sin juego)")
            for c in (self.card_mods, self.card_on, self.card_conf, self.card_inst):
                c.value_label.configure(text="—")
            self.body.delete("1.0", "end")
            self.body.insert("1.0", "Añade o selecciona un juego en «Juegos y ajustes».")
            return

        r = app.session.record
        on = sum(1 for m in app.mods if m.usar)
        on_disk = sum(1 for m in app.mods if m.on_disk)
        plan = app._last_plan
        conf = 0
        if plan:
            conf = int(plan.conflicts or 0)
        else:
            conf = sum(1 for m in app.mods if m.usar and m.conflicto)

        self.card_game.value_label.configure(text=r.name[:28])
        self.card_mods.value_label.configure(text=str(len(app.mods)))
        self.card_on.value_label.configure(text=str(on))
        self.card_conf.value_label.configure(text=str(conf))
        self.card_inst.value_label.configure(text=str(on_disk))

        # Vortex: nunca presentar backup histórico como estado actual
        vortex_line = "Vortex: Estado Vortex actual no verificado"
        vortex_hist = ""
        try:
            from ...core.vortex_sync import probe_vortex_enable_state

            snap = probe_vortex_enable_state(
                r.vortex_game_id or None,
                mods_dir=app.session.mods_dir if r.mods_dir.strip() else None,
            )
            vortex_line = f"Vortex: {snap.ui_current_label}"
            if snap.deployment_on_disk is True:
                vortex_line += " · deploy en disco: SÍ"
            elif snap.deployment_on_disk is False:
                vortex_line += " · deploy en disco: no"
            if snap.ui_historical_label:
                vortex_hist = snap.ui_historical_label
        except Exception:
            pass

        from ...core.game_status import profile_status

        pst = profile_status(app.session)
        lines = [
            f"Adaptador: {r.adapter}  ·  Plataforma: {r.platform}",
            f"Instalación S09: {getattr(r, 'install_mode', 'COPY') or 'COPY'}",
            f"Downloads: {r.downloads_dir or '(no)'} "
            f"({'OK ' + str(pst.downloads_count) + ' arch.' if pst.downloads_ok else 'no'})",
            (
                f"Staging: {app.session.stage_dir} ({pst.staging_mods} mods)"
                if pst.staging_ok
                else "Staging: (no)"
            ),
            f"Destino: {pst.destination_path}",
            f"Verificación destino: "
            f"{'SÍ — Apply posible si plan OK' if pst.destination_verified else 'NO — Apply bloqueado'}",
            f"Estado ruta: {pst.path_status}",
            f"Datos del perfil: {app.session.data_dir}",
            vortex_line,
        ]
        if vortex_hist:
            lines.append(f"(histórico, no actual) {vortex_hist}")
        lines += [
            "",
            "Estados mod: DESCARGADO / PREPARADO / SELECCIONADO / INSTALADO",
            "Nota: «Activo» = plan del gestor (independiente de Vortex).",
            "Aplicar escribe solo con destino verificado + simulación OK.",
        ]
        if r.migration_status == "pending":
            lines += ["", "Migración FF7R pendiente (acción manual en Ajustes)."]
        self.body.delete("1.0", "end")
        self.body.insert("1.0", "\n".join(lines))
