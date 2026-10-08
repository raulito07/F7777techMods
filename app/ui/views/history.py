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

S06 — panel Historial y restauración.
"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core.operations import list_operations, plan_restore, execute_restore
from ..theme import COLORS
from ..dialogs import ask_scroll_confirm, show_scroll_text


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(
            head, text="Historial y restauración", font=ctk.CTkFont(size=20, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(head, text="Actualizar", width=100, command=self.refresh).pack(
            side="right", padx=4
        )

        self.body = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg_card"])
        self.body.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        app = self.app
        if not app.session:
            ctk.CTkLabel(self.body, text="Sin juego activo.").pack(pady=20)
            return
        ops = list_operations(app.session.data_dir)
        if not ops:
            ctk.CTkLabel(self.body, text="Sin operaciones registradas todavía.").pack(pady=20)
            return
        backups = app.session.data_dir / "backups"
        ctk.CTkLabel(
            self.body,
            text=f"Backups en: {backups}",
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=8, pady=6)

        for op in ops:
            fr = ctk.CTkFrame(self.body, fg_color=COLORS["bg_muted"])
            fr.pack(fill="x", pady=4, padx=4)
            summary = (
                f"{op.at}  [{op.status}]  {op.op_type}\n"
                f"+{len(op.added)} ~{len(op.updated)} -{len(op.removed)} "
                f"adopt={len(op.adopted)}  backup={op.backup_id or '—'}\n"
                f"{op.note}"
            )
            if op.errors:
                summary += "\nErrores: " + "; ".join(op.errors[:3])
            ctk.CTkLabel(fr, text=summary, justify="left", anchor="w").pack(
                side="left", fill="x", expand=True, padx=8, pady=6
            )
            if op.backup_id and op.op_type in ("apply", "deactivate", "adopt", "restore"):
                ctk.CTkButton(
                    fr, text="Restaurar…", width=100, command=self._make_restore(op.id)
                ).pack(side="right", padx=6)

    def _make_restore(self, oid: str):
        app = self.app

        def _r():
            if app.is_busy():
                messagebox.showinfo("Ocupado", "Espera a que termine la operación actual.")
                return
            ctx = app._ctx()
            plan = plan_restore(
                app.session.data_dir,
                ctx,
                oid,
                hash_cache_path=app.session.hash_cache_json,
            )
            sim = (
                f"SIMULACIÓN restauración {oid}\n\n"
                f"OK={plan.ok}\n"
                f"Restaurar archivos: {len(plan.to_restore)}\n"
                f"Restaurar manifiesto: "
                f"{'sí' if plan.will_restore_manifest else 'no'} "
                f"({plan.pre_manifest_files} entradas)\n"
                f"Eliminar (creados entonces): {len(plan.to_delete)}\n"
            )
            if plan.to_restore:
                sim += "\nArchivos a restaurar:\n"
                for rel in plan.to_restore[:20]:
                    sim += f"  • {rel}\n"
                if len(plan.to_restore) > 20:
                    sim += f"  • … y {len(plan.to_restore) - 20} más\n"
            if plan.errors:
                sim += "\nBloqueos:\n" + "\n".join(plan.errors[:20])
                show_scroll_text(app, title="Restauración bloqueada", body=sim, kind="error")
                return
            if not ask_scroll_confirm(
                app, title="Confirmar restauración", body=sim + "\n¿Restaurar?", confirm_label="Restaurar"
            ):
                return
            try:
                execute_restore(
                    plan,
                    ctx,
                    app.session.data_dir,
                    confirm=True,
                    hash_cache_path=app.session.hash_cache_json,
                )
                messagebox.showinfo("Restaurado", "Operación completada.")
                self.refresh()
                app.refresh()
            except Exception as e:
                show_scroll_text(app, title="Error", body=str(e), kind="error")

        return _r
