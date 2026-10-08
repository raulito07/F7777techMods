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

S06 — panel Archivos instalados.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from ...core.apply import load_manifest
from ...core.provenance import scan_destination, Provenance
from ...core.adoption import plan_adoption, execute_adoption
from ...core.hash_cache import HashCache
from ..theme import COLORS
from ..dialogs import ask_scroll_confirm, show_scroll_text


class InstalledView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._inv = None
        self._gen = 0

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(
            head, text="Archivos instalados", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        self.filt = tk.StringVar(value="TODOS")
        ctk.CTkOptionMenu(
            head,
            variable=self.filt,
            values=["TODOS", "GESTIONADO", "VORTEX", "EXTERNO", "DESCONOCIDO", "DRIFT"],
            width=180,
            command=lambda _=None: self.render(),
        ).pack(side="right", padx=4)
        ctk.CTkButton(head, text="Actualizar", width=100, command=self.reload).pack(
            side="right", padx=4
        )

        self.status = ctk.CTkLabel(self, text="", text_color=COLORS["text_muted"])
        self.status.pack(anchor="w", padx=8)
        ctk.CTkLabel(
            self,
            text="GESTIONADO = manifiesto · VORTEX = deploy verificable · EXTERNO = no atribuido · DRIFT = hash distinto",
            text_color=COLORS["text_muted"],
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=8, pady=4)

        self.body = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_card"])
        self.body.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh(self) -> None:
        self.reload()

    def reload(self) -> None:
        app = self.app
        if not app.session:
            self.status.configure(text="Sin juego activo.")
            return
        if app.is_busy():
            self.status.configure(text="Operación en curso; espera a que termine.")
            return
        self._gen += 1
        gen = self._gen
        game_id = app.registry.active_game_id
        self.status.configure(text="Analizando destino (hashes en segundo plano)…")

        def worker():
            ctx = app._ctx()
            cache = HashCache(app.session.hash_cache_json)
            inv = scan_destination(
                ctx.mods,
                manifest=load_manifest(ctx),
                deploy_path=ctx.deploy,
                hash_cache=cache,
                compute_hashes=True,
            )

            def done():
                if gen != self._gen or game_id != app.registry.active_game_id:
                    return
                self._inv = inv
                self.render()

            app.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def render(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        inv = self._inv
        if inv is None:
            return
        want = self.filt.get()
        shown = 0
        for info in inv.files:
            if want == "DRIFT" and info.integrity.value != "MODIFICADO_EXTERNO":
                continue
            if want not in ("TODOS", "DRIFT") and info.provenance.value != want:
                continue
            shown += 1
            fr = ctk.CTkFrame(self.body, fg_color=COLORS["bg_muted"])
            fr.pack(fill="x", pady=3, padx=4)
            sha = (info.sha256[:16] + "…") if info.sha256 else "(sin hash)"
            txt = (
                f"[{info.provenance.value}] {info.rel}\n"
                f"integ={info.integrity.value}  size={info.size}  "
                f"mod={info.mod_folder or '—'}  {sha}"
            )
            ctk.CTkLabel(fr, text=txt, justify="left", anchor="w").pack(
                side="left", fill="x", expand=True, padx=8, pady=4
            )
            if info.provenance == Provenance.EXTERNO:
                ctk.CTkButton(
                    fr, text="Adoptar…", width=90, command=self._make_adopt(info.rel)
                ).pack(side="right", padx=6)
        self.status.configure(
            text=(
                f"{len(inv.files)} archivos · mostrando {shown} · "
                f"deploy Vortex={'SÍ' if inv.vortex_deploy_active else 'no'}"
            )
        )

    def _make_adopt(self, rel: str):
        app = self.app

        def _a():
            if app.is_busy():
                messagebox.showinfo("Ocupado", "Espera a que termine la operación actual.")
                return
            ctx = app._ctx()
            plan = plan_adoption(rel, ctx, hash_cache_path=app.session.hash_cache_json)
            if not plan.ok or not plan.candidate:
                show_scroll_text(
                    app, title="Adopción bloqueada", body="\n".join(plan.errors), kind="error"
                )
                return
            c = plan.candidate
            msg = (
                f"SIMULACIÓN — adoptar (no copia ni borra archivos del juego):\n\n"
                f"Destino: {c.dest_rel}\n"
                f"Tamaño: {c.size}\n"
                f"SHA-256: {c.sha256}\n"
                f"Mod staging: {c.mod_folder}\n"
                f"Origen: {c.stage_file}\n"
            )
            if not ask_scroll_confirm(
                app, title="Adoptar archivo", body=msg, confirm_label="Adoptar"
            ):
                return
            try:
                execute_adoption(plan, ctx, confirm=True)
                messagebox.showinfo("Adoptado", f"«{c.dest_rel}» añadido al manifiesto.")
                self.reload()
            except Exception as e:
                show_scroll_text(app, title="Error", body=str(e), kind="error")

        return _a
