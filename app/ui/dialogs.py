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

S06 — diálogos con scroll y progreso (sin messagebox interminables).
"""

from __future__ import annotations

import customtkinter as ctk

from .theme import COLORS


def show_scroll_text(
    parent,
    *,
    title: str,
    body: str,
    kind: str = "info",
) -> None:
    """Muestra texto largo con scroll (info/error)."""
    win = ctk.CTkToplevel(parent)
    win.title(title)
    win.geometry("720x520")
    win.minsize(480, 320)
    win.grab_set()
    accent = COLORS["danger"] if kind == "error" else COLORS["accent"]
    ctk.CTkLabel(
        win,
        text=title,
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=accent,
    ).pack(anchor="w", padx=16, pady=(14, 6))
    box = ctk.CTkTextbox(win, wrap="word")
    box.pack(fill="both", expand=True, padx=16, pady=8)
    box.insert("1.0", body)
    box.configure(state="disabled")
    ctk.CTkButton(win, text="Cerrar", width=120, command=win.destroy).pack(pady=12)


def ask_scroll_confirm(
    parent,
    *,
    title: str,
    body: str,
    confirm_label: str = "Confirmar",
    cancel_label: str = "Cancelar",
) -> bool:
    """Confirmación con cuerpo desplazable. Bloqueante hasta respuesta."""
    result = {"ok": False}
    win = ctk.CTkToplevel(parent)
    win.title(title)
    win.geometry("760x560")
    win.minsize(520, 360)
    win.grab_set()
    ctk.CTkLabel(
        win,
        text=title,
        font=ctk.CTkFont(size=16, weight="bold"),
    ).pack(anchor="w", padx=16, pady=(14, 6))
    box = ctk.CTkTextbox(win, wrap="word")
    box.pack(fill="both", expand=True, padx=16, pady=8)
    box.insert("1.0", body)
    box.configure(state="disabled")
    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill="x", padx=16, pady=12)

    def accept():
        result["ok"] = True
        win.destroy()

    def cancel():
        result["ok"] = False
        win.destroy()

    ctk.CTkButton(
        foot,
        text=confirm_label,
        fg_color=COLORS["btn_apply"],
        command=accept,
        width=140,
    ).pack(side="right", padx=4)
    ctk.CTkButton(
        foot,
        text=cancel_label,
        fg_color=COLORS["btn_secondary"],
        command=cancel,
        width=120,
    ).pack(side="right", padx=4)
    win.protocol("WM_DELETE_WINDOW", cancel)
    parent.wait_window(win)
    return bool(result["ok"])


class ProgressBarHost:
    """Barra de progreso; modo determinado solo si total > 0."""

    def __init__(self, parent_frame):
        self.frame = ctk.CTkFrame(parent_frame, fg_color=COLORS["bg_muted"], height=36)
        self.label = ctk.CTkLabel(self.frame, text="", text_color=COLORS["text_muted"])
        self.label.pack(side="left", padx=12)
        self.bar = ctk.CTkProgressBar(self.frame, width=280)
        self.bar.pack(side="right", padx=12, pady=8)
        self.bar.set(0)
        self._visible = False
        self._determinate = False

    def pack_hide(self) -> None:
        self.frame.pack_forget()
        self._visible = False

    def show(self, text: str = "", *, determinate: bool = False) -> None:
        if not self._visible:
            self.frame.pack(fill="x", padx=0, pady=0)
            self._visible = True
        self.label.configure(text=text)
        self._determinate = determinate
        if determinate:
            try:
                self.bar.stop()
            except Exception:
                pass
            self.bar.configure(mode="determinate")
            self.bar.set(0)
        else:
            self.bar.configure(mode="indeterminate")
            self.bar.start()

    def update(self, phase: str, current: int, total: int) -> None:
        if total and total > 0:
            if not self._determinate:
                try:
                    self.bar.stop()
                except Exception:
                    pass
                self.bar.configure(mode="determinate")
                self._determinate = True
            self.bar.set(max(0.0, min(1.0, current / total)))
            self.label.configure(text=f"{phase}: {current}/{total}")
        else:
            if self._determinate:
                self.bar.configure(mode="indeterminate")
                self.bar.start()
                self._determinate = False
            self.label.configure(text=phase)

    def hide(self) -> None:
        try:
            self.bar.stop()
        except Exception:
            pass
        self.bar.set(0)
        self.pack_hide()
