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

S06/S06.1/S20/S27 — Biblioteca multijuego: filtros por dimensiones, plan masivo seguro.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from ...core.library_status import (
    FILTER_ALL,
    archive_candidates,
    compute_mod_status,
    filter_mods,
    status_badges_text,
    work_restore_candidates,
)
from ..theme import COLORS, LIBRARY_PAGE_SIZE

_STATE_FILTER_VALUES = [
    FILTER_ALL,
    "Activo en plan",
    "Desactivados",
    "Instalado real",
    "Pendiente Apply",
    "Con conflictos",
    "Variante pendiente",
    "Archivado ZIP",
    "En WORK",
    "Staging Vortex",
    "Pendiente Vortex",
    "No disponible",
    # Compatibilidad etiquetas S20
    "Activos",
    "Conflictos",
    "En destino",
    "No instalados",
    "Archivados ZIP",
]


class LibraryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.page = 0
        self._sort_key = "mod"
        self._sort_rev = False
        self._filter_debounce = None
        self._filtered_cache: list = []
        self._col_base = {
            "usar": 64,
            "fuente": 72,
            "mod": 280,
            "estado": 150,
            "variante": 150,
            "prio": 56,
            "destino": 88,
        }

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=2, pady=(2, 4))
        ctk.CTkLabel(
            head, text="Biblioteca de mods", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")
        self.count_label = ctk.CTkLabel(
            head, text="0 resultados", text_color=COLORS["text_muted"]
        )
        self.count_label.pack(side="right", padx=4)
        ctk.CTkLabel(
            head,
            text="Flujo: SELECCIONAR → PREPARAR (plan) → SIMULAR → APLICAR",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=12)

        # Filtros con etiquetas
        filters = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8)
        filters.pack(fill="x", padx=2, pady=2)

        self.search_var = tk.StringVar(value="")
        self.state_var = tk.StringVar(value="TODOS")
        self.char_var = tk.StringVar(value="TODOS")
        self.source_var = tk.StringVar(value="TODAS")
        self.sort_var = tk.StringVar(value="Nombre")
        self.page_size_var = tk.StringVar(value=str(LIBRARY_PAGE_SIZE))

        def _labeled(parent, text, widget_factory):
            cell = ctk.CTkFrame(parent, fg_color="transparent")
            cell.pack(side="left", padx=(8, 4), pady=6)
            ctk.CTkLabel(
                cell, text=text, text_color=COLORS["text_muted"], font=ctk.CTkFont(size=11)
            ).pack(anchor="w")
            w = widget_factory(cell)
            return w

        def make_search(cell):
            e = ctk.CTkEntry(
                cell,
                textvariable=self.search_var,
                placeholder_text="Buscar mods...",
                width=220,
            )
            e.pack(anchor="w")
            return e

        def make_state(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.state_var,
                values=_STATE_FILTER_VALUES,
                width=168,
                command=lambda _=None: self._on_filter_change(),
            )
            m.pack(anchor="w")
            return m

        def make_char(cell):
            self.char_menu = ctk.CTkOptionMenu(
                cell,
                variable=self.char_var,
                values=["TODOS"],
                width=120,
                command=lambda _=None: self._on_filter_change(),
            )
            self.char_menu.pack(anchor="w")
            return self.char_menu

        def make_source(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.source_var,
                values=["TODAS", "VORTEX", "WORK"],
                width=100,
                command=lambda _=None: self._on_filter_change(),
            )
            m.pack(anchor="w")
            return m

        def make_sort(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.sort_var,
                values=["Nombre", "Estado", "Prioridad", "En destino", "Fuente"],
                width=120,
                command=lambda _=None: self._on_filter_change(),
            )
            m.pack(anchor="w")
            return m

        def make_page_size(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.page_size_var,
                values=["40", "80", "120", "200"],
                width=80,
                command=lambda _=None: self._on_filter_change(),
            )
            m.pack(anchor="w")
            return m

        _labeled(filters, "Buscar", make_search)
        self.search_var.trace_add("write", lambda *_: self._debounce_redraw())
        _labeled(filters, "Dimensión / estado", make_state)
        _labeled(filters, "Personaje", make_char)
        _labeled(filters, "Fuente", make_source)
        _labeled(filters, "Orden", make_sort)
        _labeled(filters, "Pág.", make_page_size)

        ctk.CTkButton(
            filters, text="Limpiar filtros", width=120, command=self.clear_filters
        ).pack(side="right", padx=6, pady=14)
        ctk.CTkButton(filters, text="Actualizar", width=100, command=app.refresh).pack(
            side="right", padx=6, pady=14
        )

        legend = ctk.CTkLabel(
            self,
            text=(
                "Dimensiones independientes: Plan ≠ Destino ≠ ZIP ≠ WORK ≠ Staging. "
                "Rojo=conflicto · Ámbar=variante. Multi-sel.: Ctrl/Shift. "
                "Acciones de PLAN no escriben en el juego; ZIP/WORK solo seleccionan candidatos."
            ),
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        legend.pack(fill="x", padx=6, pady=(2, 2))

        bulk = ctk.CTkFrame(self, fg_color=COLORS["bg_muted"], corner_radius=8)
        bulk.pack(fill="x", padx=2, pady=(0, 4))
        ctk.CTkLabel(
            bulk, text="Plan (masivo)", text_color=COLORS["text_muted"]
        ).pack(side="left", padx=8, pady=6)
        ctk.CTkButton(
            bulk, text="Activar en plan", width=120, command=app.bulk_plan_activate
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Desactivar en plan", width=130, command=app.bulk_plan_deactivate
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Sel. página", width=90, command=self.select_page
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Sel. filtrados", width=110, command=self.select_filtered
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Candidatos ZIP", width=110, command=self.select_archive_candidates
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Candidatos WORK", width=120, command=self.select_work_candidates
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk, text="Limpiar sel.", width=90, command=self.clear_selection
        ).pack(side="left", padx=3, pady=6)
        ctk.CTkButton(
            bulk,
            text="Simular selección",
            width=130,
            fg_color=COLORS["btn_secondary"],
            command=app.simulate_selection_plan,
        ).pack(side="left", padx=3, pady=6)
        self.sel_count = ctk.CTkLabel(bulk, text="0 sel.", text_color=COLORS["text_muted"])
        self.sel_count.pack(side="right", padx=10)

        # Paned: tabla | detalle redimensionable
        self.paned = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            bg="#15202b",
            bd=0,
        )
        self.paned.pack(fill="both", expand=True, padx=2, pady=2)

        left = ctk.CTkFrame(self.paned, fg_color=COLORS["bg_card"])
        right = ctk.CTkFrame(self.paned, fg_color=COLORS["bg_card"], width=320)
        self.paned.add(left, stretch="always", minsize=420)
        self.paned.add(right, stretch="never", minsize=260)
        self._detail_frame = right

        style = ttk.Style(app)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.map("Lib.Treeview", background=[("selected", "#3a5a80")])

        # Paginación abajo; la tabla ocupa el resto (orden de pack importante)
        pager = ctk.CTkFrame(left, fg_color="transparent")
        pager.pack(side="bottom", fill="x", padx=6, pady=4)
        ctk.CTkButton(pager, text="« Anterior", width=100, command=self.prev_page).pack(
            side="left"
        )
        self.page_label = ctk.CTkLabel(pager, text="Página 1")
        self.page_label.pack(side="left", padx=12)
        ctk.CTkButton(pager, text="Siguiente »", width=100, command=self.next_page).pack(
            side="left"
        )
        self.page_count = ctk.CTkLabel(pager, text="", text_color=COLORS["text_muted"])
        self.page_count.pack(side="right", padx=8)

        tree_wrap = tk.Frame(left, bg="#1a222d", highlightthickness=0)
        tree_wrap.pack(side="top", fill="both", expand=True, padx=2, pady=2)

        cols = ("usar", "mod", "estado", "fuente", "variante", "prio", "destino")
        self.tree = ttk.Treeview(
            tree_wrap,
            columns=cols,
            show="headings",
            style="Lib.Treeview",
            selectmode="extended",
        )
        headings = {
            "usar": "Plan",
            "mod": "Mod",
            "estado": "Estado",
            "fuente": "Fuente",
            "variante": "Variante",
            "prio": "Prio",
            "destino": "Destino",
        }
        for k, title in headings.items():
            self.tree.heading(k, text=title, command=lambda c=k: self._sort_by(c))
            self.tree.column(k, width=self._col_base[k], stretch=(k == "mod"), minwidth=40)

        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda e: app.toggle_selected())
        # Estados: no usar rojo salvo conflicto real
        self.tree.tag_configure("off", background="#2a2a32", foreground="#a0a8b4")
        self.tree.tag_configure("active", background="#14352a", foreground="#e8eef7")
        self.tree.tag_configure("installed", background="#1a2e3d", foreground="#e8eef7")
        self.tree.tag_configure("active_inst", background="#123d45", foreground="#e8eef7")
        self.tree.tag_configure("conflict", background="#5c1a1a", foreground="#ffe4e4")
        self.tree.tag_configure("pending", background="#3b2f14", foreground="#fff3d0")

        # Detalle
        ctk.CTkLabel(
            right, text="Detalle", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=10, pady=(10, 2))
        self.detail_title = ctk.CTkLabel(
            right,
            text="Selecciona un mod",
            wraplength=280,
            justify="left",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.detail_title.pack(anchor="w", padx=10, pady=(0, 4))
        self.detail_image = ctk.CTkLabel(right, text="(sin imagen)", width=280, height=130)
        self.detail_image.pack(padx=10, pady=4)
        self.detail_badges = ctk.CTkLabel(
            right, text="", justify="left", wraplength=280, text_color=COLORS["text_muted"]
        )
        self.detail_badges.pack(anchor="w", padx=10, pady=2)

        ctk.CTkLabel(right, text="Descripción", text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=10
        )
        self.detail_desc = ctk.CTkTextbox(right, height=100, wrap="word")
        self.detail_desc.pack(fill="both", expand=True, padx=10, pady=2)

        ctk.CTkLabel(right, text="Información", text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=10, pady=(6, 0)
        )
        self.detail_meta = ctk.CTkTextbox(right, height=180, wrap="word")
        self.detail_meta.pack(fill="both", expand=False, padx=10, pady=2)

        btn_fr = ctk.CTkFrame(right, fg_color="transparent")
        btn_fr.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(
            btn_fr, text="Activar / Desactivar (plan)", command=app.toggle_selected
        ).pack(fill="x", pady=2)
        ctk.CTkButton(btn_fr, text="Elegir variante .pak", command=app.choose_pak).pack(
            fill="x", pady=2
        )
        ctk.CTkButton(
            btn_fr, text="Simular este mod", command=app.simulate_selected_preview
        ).pack(fill="x", pady=2)
        ctk.CTkButton(
            btn_fr, text="Preparar desde archivo", command=app.library_prepare_from_archive
        ).pack(fill="x", pady=2)
        ctk.CTkButton(
            btn_fr, text="Usar fuente WORK", command=app.library_use_work_source
        ).pack(fill="x", pady=2)
        ctk.CTkButton(
            btn_fr, text="Usar fuente Vortex", command=app.library_use_vortex_source
        ).pack(fill="x", pady=2)
        ctk.CTkButton(
            btn_fr, text="Revisar cambios staging", command=app.review_staging_changes
        ).pack(fill="x", pady=2)
        ctk.CTkButton(btn_fr, text="Editar descripción", command=app.edit_description).pack(
            fill="x", pady=2
        )
        ctk.CTkLabel(
            right,
            text=(
                "SELECCIONAR / PREPARAR plan ≠ APLICAR. "
                "Solo «Aplicar» escribe archivos GESTIONADOS en el juego."
            ),
            text_color=COLORS["text_muted"],
            wraplength=280,
            justify="left",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10, pady=(2, 10))

        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, _evt=None) -> None:
        try:
            w = max(200, self._detail_frame.winfo_width() - 24)
            self.detail_title.configure(wraplength=w)
            self.detail_badges.configure(wraplength=w)
        except Exception:
            pass

    def apply_zoom(self, scale: float) -> None:
        """Ajusta anchos de columna según zoom (llamado desde la app)."""
        for k, base in self._col_base.items():
            self.tree.column(k, width=max(40, int(base * scale)), stretch=(k == "mod"))
        try:
            self.after(50, lambda: self.paned.sash_place(0, max(480, int(self.winfo_width() * 0.68)), 0))
        except Exception:
            pass

    def _on_filter_change(self) -> None:
        self.page = 0
        self.redraw()

    def _debounce_redraw(self) -> None:
        app = self.app
        if self._filter_debounce is not None:
            try:
                app.after_cancel(self._filter_debounce)
            except Exception:
                pass
        self._filter_debounce = app.after(120, self._on_filter_change)

    def _sort_by(self, col: str) -> None:
        if self._sort_key == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_key = col
            self._sort_rev = False
        self.page = 0
        self.redraw()

    def page_size(self) -> int:
        try:
            return max(20, min(500, int(self.page_size_var.get())))
        except Exception:
            return LIBRARY_PAGE_SIZE

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.state_var.set(FILTER_ALL)
        self.char_var.set("TODOS")
        self.source_var.set("TODAS")
        self.sort_var.set("Nombre")
        self.page = 0
        self.redraw()

    def filtered(self) -> list:
        app = self.app
        prios = {}
        if app.session:
            from ...core.priority_store import load_priorities

            prios = load_priorities(app.session.priorities_json)

        out = filter_mods(
            app.mods,
            query=self.search_var.get(),
            dimension=self.state_var.get(),
            source=self.source_var.get(),
            character=self.char_var.get(),
        )

        sk = self.sort_var.get()
        if sk == "Estado":
            out.sort(key=lambda m: (0 if m.usar else 1, (m.conflicto or ""), m.name.lower()))
        elif sk == "Prioridad":
            out.sort(key=lambda m: (-int(prios.get(m.folder, -9999)), m.name.lower()))
        elif sk == "En destino":
            out.sort(key=lambda m: (0 if m.on_disk else 1, m.name.lower()))
        elif sk == "Fuente":
            out.sort(
                key=lambda m: (
                    (getattr(m, "source_kind", "") or "").upper(),
                    m.name.lower(),
                )
            )
        else:
            out.sort(key=lambda m: m.name.lower())

        if self._sort_key == "usar":
            out.sort(key=lambda m: (0 if m.usar else 1, m.name.lower()), reverse=self._sort_rev)
        elif self._sort_key == "mod" and self._sort_rev:
            out.reverse()
        elif self._sort_key == "destino":
            out.sort(key=lambda m: (0 if m.on_disk else 1, m.name.lower()), reverse=self._sort_rev)
        return out

    def prev_page(self) -> None:
        if self.page > 0:
            self.page -= 1
            self._paint_page()

    def next_page(self) -> None:
        ps = self.page_size()
        max_page = max(0, (len(self._filtered_cache) - 1) // ps)
        if self.page < max_page:
            self.page += 1
            self._paint_page()

    def redraw(self) -> None:
        chars = sorted({m.character_main for m in self.app.mods})
        cur = self.char_var.get()
        self.char_menu.configure(values=["TODOS"] + chars)
        if cur not in (["TODOS"] + chars):
            self.char_var.set("TODOS")
        self._filtered_cache = self.filtered()
        max_page = max(0, (len(self._filtered_cache) - 1) // self.page_size())
        if self.page > max_page:
            self.page = max_page
        self._paint_page()

    def _row_tag(self, m) -> tuple[str, str]:
        """Devuelve (tag, texto_estado) a partir de dimensiones independientes."""
        st = compute_mod_status(m)
        return st.row_tag, st.row_label

    def _paint_page(self) -> None:
        app = self.app
        prios = {}
        if app.session:
            from ...core.priority_store import load_priorities

            prios = load_priorities(app.session.priorities_json)

        # Conservar selección si sigue visible
        prev = None
        sel = self.tree.selection()
        if sel:
            prev = sel[0]

        self.tree.delete(*self.tree.get_children())
        ps = self.page_size()
        start = self.page * ps
        chunk = self._filtered_cache[start : start + ps]
        for m in chunk:
            tag, estado = self._row_tag(m)
            prio = prios.get(m.folder, "—")
            # Truncar nombre en tabla; completo en detalle
            name = m.name if len(m.name) <= 48 else m.name[:45] + "…"
            var = m.pak_elegido or ("(elige 1)" if m.multi else "—")
            if len(var) > 28:
                var = var[:25] + "…"
            src = getattr(m, "source_kind", "STAGING_VORTEX") or "STAGING_VORTEX"
            src_short = "WORK" if src == "WORK_LIBRARY" else "VORTEX"
            if getattr(m, "archived", False):
                src_short += "+Z"
            self.tree.insert(
                "",
                "end",
                iid=m.folder,
                values=(
                    "SI" if m.usar else "NO",
                    name,
                    estado if len(estado) <= 40 else estado[:37] + "…",
                    src_short,
                    var,
                    prio,
                    "ON" if m.on_disk else "off",
                ),
                tags=(tag,),
            )
        total = len(self._filtered_cache)
        max_page = max(0, (total - 1) // ps) if total else 0
        self.page_label.configure(text=f"Página {self.page + 1} / {max_page + 1}")
        self.page_count.configure(text=f"{ps} por página")
        self.count_label.configure(
            text=f"{total} resultado(s)  ·  {len(app.mods)} en memoria"
        )
        if prev and self.tree.exists(prev):
            self.tree.selection_set(prev)
            self.tree.see(prev)
        self._update_sel_count()

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.app.by_id.get(sel[0])

    def selected_many(self) -> list:
        out = []
        for iid in self.tree.selection():
            m = self.app.by_id.get(iid)
            if m:
                out.append(m)
        return out

    def select_page(self) -> None:
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids)
        self._update_sel_count()
        self.on_select()

    def select_filtered(self) -> None:
        """Selecciona todos los filtrados visibles en la página actual + avisa del total."""
        self.select_page()
        n = len(self._filtered_cache)
        if n > self.page_size():
            # marcar folders filtrados en app para acciones masivas
            self.app._bulk_filter_folders = [m.folder for m in self._filtered_cache]
            if hasattr(self, "sel_count"):
                self.sel_count.configure(
                    text=f"{len(self.tree.selection())} vis. / {n} filtrados"
                )
        else:
            self.app._bulk_filter_folders = [m.folder for m in self._filtered_cache]

    def clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())
        self.app._bulk_filter_folders = None
        self._update_sel_count()

    def _apply_candidate_selection(self, mods: list, label: str) -> None:
        """Marca candidatos para flujos posteriores; no archiva ni restaura."""
        folders = [m.folder for m in mods]
        self.app._bulk_filter_folders = folders or None
        visible = [f for f in folders if self.tree.exists(f)]
        if visible:
            self.tree.selection_set(visible)
        else:
            self.tree.selection_remove(self.tree.selection())
        n = len(folders)
        if hasattr(self, "sel_count"):
            self.sel_count.configure(text=f"{len(visible)} vis. / {n} {label}")
        if n == 0:
            try:
                from tkinter import messagebox

                messagebox.showinfo(
                    "Selección",
                    f"No hay candidatos «{label}» con el inventario actual.",
                )
            except Exception:
                pass

    def select_archive_candidates(self) -> None:
        self._apply_candidate_selection(
            archive_candidates(self._filtered_cache or self.app.mods),
            "ZIP",
        )

    def select_work_candidates(self) -> None:
        self._apply_candidate_selection(
            work_restore_candidates(self._filtered_cache or self.app.mods),
            "WORK",
        )

    def _update_sel_count(self) -> None:
        if hasattr(self, "sel_count"):
            n = len(self.tree.selection())
            extra = getattr(self.app, "_bulk_filter_folders", None)
            if extra and len(extra) > n:
                self.sel_count.configure(text=f"{n} vis. / {len(extra)} filtrados")
            else:
                self.sel_count.configure(text=f"{n} sel.")

    def _on_tree_select(self, _evt=None) -> None:
        self._update_sel_count()
        self.on_select()

    def bulk_target_mods(self) -> list:
        """Preferencia: filtrados marcados > selección visible."""
        folders = getattr(self.app, "_bulk_filter_folders", None)
        if folders:
            return [self.app.by_id[f] for f in folders if f in self.app.by_id]
        return self.selected_many()

    def _staging_change_label(self, m) -> str:
        """Etiqueta de cambio local (caché en app; no implica Nexus)."""
        cache = getattr(self.app, "_staging_labels", None) or {}
        if m.folder in cache:
            return cache[m.folder]
        if not self.app.session:
            return "—"
        fp = self.app.session.staging_fingerprint_json
        if not fp.is_file():
            return "sin huella (usar Revisar cambios)"
        return cache.get(m.folder, "sin cambios registrados")

    def _refresh_staging_labels(self) -> None:
        if not self.app.session:
            self.app._staging_labels = {}
            return
        from ...core.staging_watch import detect_staging_changes, load_fingerprint

        fp = self.app.session.staging_fingerprint_json
        if not fp.is_file():
            self.app._staging_labels = {
                m.folder: "sin huella (usar Revisar cambios)" for m in self.app.mods
            }
            return
        # Comparación ligera: solo si huella existe
        result = detect_staging_changes(self.app.mods, fp, quick=True)
        labels = {m.folder: "OK (huella al día)" for m in self.app.mods}
        for d in result.deltas:
            labels[d.folder] = d.label or "Cambio local detectado"
        self.app._staging_labels = labels
        _ = load_fingerprint  # API disponible

    def _affected_files(self, m) -> list[str]:
        """Archivos del plan vigente para este mod (si hay análisis)."""
        plan = self.app._last_plan
        out: list[str] = []
        if plan and plan.desired_meta:
            for rel, meta in plan.desired_meta.items():
                if meta.mod_folder == m.folder:
                    out.append(rel)
        if not out and m.paks:
            # Fallback: variantes conocidas en staging (no implica instalado)
            if m.multi and m.pak_elegido:
                out = [m.pak_elegido]
            else:
                out = list(m.paks[:12])
        return out

    def on_select(self, _evt=None) -> None:
        """Solo actualiza el detalle; no relanza análisis (rendimiento)."""
        m = self.selected()
        if not m:
            return
        self.app._selected_folder = m.folder
        title = m.nexus_mod_name or m.name
        self.detail_title.configure(text=title)

        prios = {}
        if self.app.session:
            from ...core.priority_store import load_priorities

            prios = load_priorities(self.app.session.priorities_json)
        prio = prios.get(m.folder, "(sin prioridad)")

        st = compute_mod_status(m)
        conf_txt = m.conflicto if m.conflicto else "(sin conflicto reportado)"
        staging_txt = self._staging_change_label(m)
        from ...core.game_status import lifecycle_for_mod

        life = lifecycle_for_mod(m)
        src = getattr(m, "source_kind", "STAGING_VORTEX") or "(fuente no disponible)"
        game_name = "—"
        if self.app.session and getattr(self.app.session, "record", None):
            game_name = getattr(self.app.session.record, "name", None) or self.app.session.record.id
        arch_hash = (
            getattr(m, "archive_content_sha256", "")
            or getattr(m, "archive_zip_sha256", "")
            or ""
        )
        arch_hash_txt = (arch_hash[:16] + "…") if arch_hash else "(hash no disponible)"
        self.detail_badges.configure(
            text=(
                f"Juego: {game_name}\n"
                f"Id carpeta: {m.folder}\n"
                f"Ciclo UI: {life}\n"
                f"Fuente: {src}\n"
                f"Flags: {status_badges_text(st)}\n"
                f"Conflicto: {conf_txt}\n"
                f"Staging local: {staging_txt}\n"
                f"ZIP hash: {arch_hash_txt}\n"
                f"(Plan ≠ destino ≠ ZIP ≠ WORK; Enabled Vortex ≠ instalado real)"
            )
        )

        self.detail_desc.configure(state="normal")
        self.detail_desc.delete("1.0", "end")
        self.detail_desc.insert("1.0", m.description or "(sin descripción)")
        self.detail_desc.configure(state="normal")  # scrollable editable view OK

        files = self._affected_files(m)
        files_txt = "\n".join(f"  • {f}" for f in files[:20]) if files else "  (sin datos de plan)"
        if len(files) > 20:
            files_txt += f"\n  • … y {len(files) - 20} más"

        # S08 — clasificación por adaptador (solo lectura)
        cls_txt = ""
        try:
            from ...core.content_classify import classify_mod

            aid = self.app.session.adapter_id if self.app.session else "generic_folder"
            mc = classify_mod(m, aid)
            inst = "\n".join(f"  • {x}" for x in mc.installable[:15]) or "  (ninguno)"
            docs = "\n".join(f"  • {x}" for x in mc.documentation[:10]) or "  (ninguna)"
            special = "\n".join(f"  • {x}" for x in mc.special[:8]) or "  (ninguno)"
            unk = "\n".join(f"  • {x}" for x in mc.unknown[:8]) or "  (ninguno)"
            alts = "\n".join(f"  • {x}" for x in mc.variant_alts[:8]) or "  (ninguna)"
            cls_txt = (
                f"\nContenido ({mc.summary_kind()}):\n"
                f"Instalables:\n{inst}\n"
                f"Documentación excluida:\n{docs}\n"
                f"Destino especial:\n{special}\n"
                f"Desconocido / pendiente:\n{unk}\n"
                f"Variantes alt.:\n{alts}\n"
            )
        except Exception:
            cls_txt = ""

        self.detail_meta.configure(state="normal")
        self.detail_meta.delete("1.0", "end")
        author_txt = m.author.strip() if (m.author or "").strip() else "(no verificado)"
        size_txt = "(tamaño no calculado en inventario; evitar escaneo masivo)"
        self.detail_meta.insert(
            "1.0",
            (
                f"Prioridad: {prio}\n"
                f"Variante: {m.pak_elegido or ('(elige 1)' if m.multi else '—')}\n"
                f"Multi: {'SI' if m.multi else 'NO'}  ·  Paks conocidos: {len(m.paks)}\n"
                f"Tipo: {m.category or '(no disponible)'}\n"
                f"Personaje: {', '.join(m.characters) or '(no disponible)'}\n"
                f"Autor: {author_txt}\n"
                f"Tamaño: {size_txt}\n"
                f"Ruta staging: {m.stage_path or '(no disponible)'}\n"
                f"ZIP propio: {getattr(m, 'archive_path', '') or '(no disponible)'}\n"
                f"Slots: {', '.join(m.slots) or '(no disponible)'}\n"
                f"{cls_txt}"
                f"\nArchivos relevantes (plan / staging):\n{files_txt}"
            ),
        )
        self.detail_meta.configure(state="disabled")
        self.app.show_thumb_for(m, self.detail_image)

    def refresh(self) -> None:
        try:
            self._refresh_staging_labels()
        except Exception:
            self.app._staging_labels = {}
        self.redraw()
