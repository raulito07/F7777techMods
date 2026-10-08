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

S06 — panel Conflictos y prioridades (integrado).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from ...core.conflict_engine import ConflictKind
from ...core.priority_store import (
    save_priorities,
    save_resolutions,
    set_resolution,
    clear_resolution,
)
from ..theme import COLORS


class ConflictsView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._priorities: dict = {}
        self._resolutions: dict = {}

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(
            head, text="Conflictos y prioridades", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(head, text="Recalcular", width=110, command=self.reload).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            head, text="Simular", width=100, fg_color=COLORS["btn_secondary"], command=app.simulate
        ).pack(side="right", padx=4)

        self.status = ctk.CTkLabel(self, text="", text_color=COLORS["text_muted"])
        self.status.pack(anchor="w", padx=8, pady=4)

        legend = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8)
        legend.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            legend,
            text=(
                "Leyenda de estados:  "
                "PENDIENTE (rojo/ámbar en biblioteca) = bloquea Aplicar  ·  "
                "RESUELTO = prioridad o ganador manual  ·  "
                "Variante pendiente = falta elegir .pak  ·  "
                "Plan SI ≠ instalado en destino"
            ),
            wraplength=920,
            justify="left",
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=12, pady=8)

        warn = ctk.CTkLabel(
            self,
            text=(
                "Advertencia: los conflictos por slots semánticos son heurísticos. "
                "El contenido interno de paquetes .pak no se analiza. "
                "Mayor prioridad gana; sin prioridad o empate → bloquea. "
                "«Gana: …» fija resolución manual (sin editar JSON)."
            ),
            wraplength=900,
            justify="left",
            text_color=COLORS["warn"],
        )
        warn.pack(anchor="w", padx=8, pady=(0, 8))

        self.body = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_card"])
        self.body.pack(fill="both", expand=True, padx=4, pady=4)

    def reload(self) -> None:
        self.app.analyze_conflicts(on_done=self.refresh)

    def refresh(self) -> None:
        app = self.app
        for w in self.body.winfo_children():
            w.destroy()
        if not app.session:
            self.status.configure(text="Sin juego activo.")
            return

        settings = app._settings()
        self._priorities = dict(settings.priorities)
        self._resolutions = dict(settings.resolutions)
        plan = app._last_plan
        if plan is None:
            self.status.configure(text="Calculando… pulsa Recalcular si no aparece.")
            app.analyze_conflicts(on_done=self.refresh)
            return

        pending = []
        resolved = []
        if plan.analysis:
            for fc in list(plan.analysis.file_conflicts) + list(plan.analysis.variant_issues):
                (resolved if fc.resolved else pending).append(fc)

        self.status.configure(
            text=(
                f"Pendientes: {len(pending)}  ·  Resueltos: {len(resolved)}  ·  "
                f"Errores plan: {len(plan.errors)}  ·  Adaptador: {app.session.adapter_id}"
            )
        )

        # Prioridades
        prio_fr = ctk.CTkFrame(self.body, fg_color="transparent")
        prio_fr.pack(fill="x", pady=(4, 12))
        ctk.CTkLabel(
            prio_fr, text="Prioridades de mods activos (mayor número gana)", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=8, pady=4)
        for m in sorted((x for x in app.mods if x.usar), key=lambda x: x.name.lower()):
            row = ctk.CTkFrame(prio_fr, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(row, text=m.name[:48], width=360, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self._priorities.get(m.folder, "")))

            def make_save(folder=m.folder, v=var):
                def _s():
                    raw = v.get().strip()
                    if raw == "":
                        self._priorities.pop(folder, None)
                    else:
                        try:
                            self._priorities[folder] = int(raw)
                        except ValueError:
                            messagebox.showerror("Prioridad", "Debe ser un entero.", parent=app)
                            return
                    save_priorities(app.session.priorities_json, self._priorities)
                    app.analyze_conflicts(on_done=self.refresh)

                return _s

            ctk.CTkEntry(row, textvariable=var, width=70).pack(side="left", padx=6)
            ctk.CTkButton(row, text="OK", width=40, command=make_save()).pack(side="left")

        def section(title: str, items: list):
            ctk.CTkLabel(
                self.body, text=title, font=ctk.CTkFont(size=15, weight="bold")
            ).pack(anchor="w", padx=8, pady=(10, 4))
            if not items:
                ctk.CTkLabel(self.body, text="(ninguno)", text_color=COLORS["text_muted"]).pack(
                    anchor="w", padx=16
                )
            for fc in items:
                self._render_conflict(fc)

        section("Pendientes", pending)
        section("Resueltos", resolved)

    def _render_conflict(self, fc) -> None:
        app = self.app
        box = ctk.CTkFrame(self.body, fg_color=COLORS["bg_muted"])
        box.pack(fill="x", pady=6, padx=4)
        state = "RESUELTO" if fc.resolved else "PENDIENTE"
        ctk.CTkLabel(
            box,
            text=f"[{state}] {fc.kind.value} — destino: {fc.dest_rel}",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 2))
        if fc.note:
            ctk.CTkLabel(box, text=f"Motivo: {fc.note}", wraplength=860, anchor="w", justify="left").pack(
                fill="x", padx=8
            )
        if fc.winner_folder:
            ctk.CTkLabel(
                box,
                text=f"Ganador: {fc.winner_folder}  |  Desplazados: {', '.join(fc.displaced_folders) or '—'}",
                anchor="w",
            ).pack(fill="x", padx=8)
        for o in fc.offers:
            h = (fc.hashes.get(o.mod_folder) or o.sha256 or "")[:16]
            hdisp = f"sha256={h}…" if h else "sha256=(n/d)"
            ctk.CTkLabel(
                box,
                text=f"· {o.mod_name}  prio={o.priority}  {hdisp}",
                anchor="w",
            ).pack(fill="x", padx=16)

        if fc.kind in (ConflictKind.FILE_CONFLICT, ConflictKind.DUPLICATE_IDENTICAL) and fc.offers:
            btn_row = ctk.CTkFrame(box, fg_color="transparent")
            btn_row.pack(fill="x", padx=8, pady=6)
            for o in fc.offers:

                def make_winner(folder=o.mod_folder, key=fc.dest_key):
                    def _w():
                        set_resolution(self._resolutions, key, folder, mode="manual")
                        save_resolutions(app.session.resolutions_json, self._resolutions)
                        app.analyze_conflicts(on_done=self.refresh)

                    return _w

                ctk.CTkButton(
                    btn_row,
                    text=f"Gana: {o.mod_name[:28]}",
                    width=160,
                    command=make_winner(),
                ).pack(side="left", padx=3)

            def make_clear(key=fc.dest_key):
                def _c():
                    clear_resolution(self._resolutions, key)
                    save_resolutions(app.session.resolutions_json, self._resolutions)
                    app.analyze_conflicts(on_done=self.refresh)

                return _c

            ctk.CTkButton(
                btn_row,
                text="Pendiente",
                width=90,
                fg_color="#6c757d",
                command=make_clear(),
            ).pack(side="left", padx=6)
