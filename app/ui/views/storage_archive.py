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

S11–S16 — vista Almacenamiento / Archivo (sin borrado real de staging).
"""

from __future__ import annotations

import customtkinter as ctk

from ..theme import COLORS


class StorageArchiveView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(
            self,
            text="Almacenamiento / Archivo",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(8, 2))
        ctk.CTkLabel(
            self,
            text=(
                "Estados: DESCARGADO (Vortex downloads) · EXTRAÍDO VORTEX (staging) · "
                "ARCHIVADO (ZIP propio) · WORK_LIBRARY (preparado) · INSTALADO (juego). "
                "ARCHIVADO ≠ ESPACIO LIBERADO. "
                "Política: LIBERABLE | BLOQUEADO | PENDIENTE_VORTEX. "
                "Borrado automático de staging Vortex: BLOQUEADO."
            ),
            text_color=COLORS["text_muted"],
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 8))

        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=10)
        bar.pack(fill="x", padx=8, pady=4)
        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        ctk.CTkButton(row, text="Analizar biblioteca", command=app.archive_analyze).pack(
            side="left", padx=3
        )
        ctk.CTkButton(
            row, text="Elegir carpeta archivo", command=app.archive_config_dir
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row, text="Archivar real", command=app.archive_real_start
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row, text="Reanudar archivado", command=app.archive_real_resume
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row, text="Historial", command=app.archive_show_history
        ).pack(side="left", padx=3)

        row2 = ctk.CTkFrame(bar, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkButton(
            row2,
            text="Restaurar a biblioteca trabajo",
            command=app.work_restore_from_archive,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row2,
            text="Preparar instalación desde archivo",
            command=app.work_prepare_install,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row2,
            text="Limpiar biblioteca trabajo",
            command=app.work_cleanup_library,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row2,
            text="Config. carpeta trabajo",
            command=app.work_config_dir,
        ).pack(side="left", padx=3)

        row3 = ctk.CTkFrame(bar, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(
            row3,
            text="Simular liberación staging",
            command=app.archive_simulate_liberation,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row3,
            text="Comprobar independencia",
            command=app.archive_check_independence,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row3,
            text="Investigación Vortex",
            command=app.archive_vortex_research,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row3,
            text="Espacio físico estimado",
            command=app.archive_physical_space,
        ).pack(side="left", padx=3)

        row4 = ctk.CTkFrame(bar, fg_color="transparent")
        row4.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(
            row4,
            text="Estado biblioteca trabajo",
            command=app.work_show_status,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row4,
            text="Cancelar",
            command=app.archive_cancel_job,
            fg_color=COLORS.get("warn", "#a67c00"),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            row4,
            text="Liberar staging",
            command=app.archive_liberate_unavailable,
            state="disabled",
        ).pack(side="left", padx=3)

        self.summary = ctk.CTkLabel(
            self, text="Sin análisis todavía.", justify="left", anchor="w"
        )
        self.summary.pack(anchor="w", padx=12, pady=6)

        self.body = ctk.CTkTextbox(self, wrap="word")
        self.body.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            self,
            text=(
                "ZIP propio = fuente primaria. Biblioteca de trabajo ≠ staging Vortex. "
                "PENDIENTE_VORTEX: recuperable, pero retire primero vía Uninstall en Vortex. "
                "Borrado staging desde el gestor: NO DISPONIBLE."
            ),
            text_color=COLORS["warn"],
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

    def refresh(self) -> None:
        app = self.app
        if not app.session:
            self.summary.configure(text="Sin juego activo.")
            self.body.delete("1.0", "end")
            return
        r = app.session.record
        arch_dir = getattr(r, "archive_dir", "") or ""
        work_cfg = getattr(r, "work_library_dir", "") or ""
        lib_counts = getattr(app, "_liberation_counts", None) or {}
        line = (
            f"Juego: {r.name}\n"
            f"Archivo ZIP: {arch_dir or '(no configurada)'}\n"
            f"Biblioteca trabajo: {work_cfg or '(default data/work_library)'}\n"
            f"Mods memoria: {len(app.mods)} · Liberar staging: NO DISPONIBLE\n"
            f"S16: LIBERABLE={lib_counts.get('LIBERABLE', '—')} · "
            f"PENDIENTE_VORTEX={lib_counts.get('PENDIENTE_VORTEX', '—')} · "
            f"BLOQUEADO={lib_counts.get('BLOQUEADO', '—')}"
        )
        job = getattr(app, "_archive_job", None)
        if job is not None:
            c = job.counts()
            line += (
                f"\nArchivado OK={c.get('ARCHIVADO VERIFICADO', 0)} "
                f"PENDIENTE={c.get('PENDIENTE', 0)}"
            )
        widx = getattr(app, "_work_index", None)
        if widx is not None:
            line += (
                f"\nWork extraídos={len(widx.mods)} "
                f"en_uso={sum(1 for m in widx.mods.values() if m.in_use)}"
            )
        self.summary.configure(text=line)
        text = getattr(app, "_archive_view_text", "") or (
            "Analiza / archiva / restaura a biblioteca de trabajo."
        )
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text)
