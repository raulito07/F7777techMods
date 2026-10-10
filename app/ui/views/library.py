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

from ...core.library_selection import LibrarySelection
from ...core.library_catalog_model import (
    TAG_FILTER_ALL,
    build_catalog_item,
    collect_tags_from_mods,
)
from ...core.library_status import (
    FILTER_ALL,
    archive_candidates,
    compute_mod_status,
    filter_mods,
    status_badges_text,
    work_restore_candidates,
)
from ...core.library_view_prefs import (
    CARD_TO_UI,
    LAYOUT_CATALOG,
    LAYOUT_TABLE,
    LAYOUT_TO_UI,
    LAYOUT_VISUAL_LIST,
    MODE_FULL,
    MODE_PAGINATED,
    MODE_TO_UI,
    TREE_INSERT_BATCH,
    UI_CARD_MEDIUM,
    UI_LABEL_FULL,
    UI_LABEL_PAGINATED,
    UI_LAYOUT_CATALOG,
    UI_LAYOUT_TABLE,
    UI_LAYOUT_VISUAL,
    UI_TO_CARD,
    UI_TO_LAYOUT,
    UI_TO_MODE,
    display_slice,
    list_summary_text,
    load_library_card_size,
    load_library_layout,
    load_library_view_mode,
    save_library_card_size,
    save_library_layout,
    save_library_view_mode,
)
from .library_visual_pane import LibraryVisualPane
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
    # S28 estructura
    "Paquete incompleto",
    "Revisión manual",
    "No soportado",
    "Bloqueo estructura",
    "Con variantes",
    "Formato UE4 PAK",
    "Formato UE5 IoStore",
    "Formato genérico",
    # S49 investigación
    "Invest. confirmada",
    "Invest. probable",
    "Invest. externa",
    "Invest. no soportada",
    "Invest. desconocida",
    "Sin .pak (payload)",
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
        self.tag_var = tk.StringVar(value=TAG_FILTER_ALL)
        self.source_var = tk.StringVar(value="TODAS")
        self.sort_var = tk.StringVar(value="Nombre")
        self.page_size_var = tk.StringVar(value=str(LIBRARY_PAGE_SIZE))
        self.view_mode_var = tk.StringVar(value=UI_LABEL_PAGINATED)
        self.layout_var = tk.StringVar(value=UI_LAYOUT_TABLE)
        self.card_size_var = tk.StringVar(value=UI_CARD_MEDIUM)
        self._view_mode = MODE_PAGINATED
        self._layout_mode = LAYOUT_TABLE
        self._card_size = "medium"
        self._page_size_menu = None
        self._card_size_menu = None
        self._pager_frame = None
        self._large_hint = None
        self._library_sel = LibrarySelection()
        self._visible_order: list[str] = []

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

        def make_tag(cell):
            self.tag_menu = ctk.CTkOptionMenu(
                cell,
                variable=self.tag_var,
                values=[TAG_FILTER_ALL],
                width=140,
                command=lambda _=None: self._on_filter_change(),
            )
            self.tag_menu.pack(anchor="w")
            return self.tag_menu

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
            self._page_size_menu = m
            return m

        def make_view_mode(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.view_mode_var,
                values=[UI_LABEL_PAGINATED, UI_LABEL_FULL],
                width=110,
                command=lambda _=None: self._on_view_mode_change(),
            )
            m.pack(anchor="w")
            return m

        _labeled(filters, "Buscar", make_search)
        self.search_var.trace_add("write", lambda *_: self._debounce_redraw())
        _labeled(filters, "Dimensión / estado", make_state)
        _labeled(filters, "Etiqueta", make_tag)
        _labeled(filters, "Fuente", make_source)
        _labeled(filters, "Orden", make_sort)
        _labeled(filters, "Vista", make_view_mode)

        def make_layout(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.layout_var,
                values=[UI_LAYOUT_TABLE, UI_LAYOUT_CATALOG, UI_LAYOUT_VISUAL],
                width=120,
                command=lambda _=None: self._on_layout_change(),
            )
            m.pack(anchor="w")
            return m

        def make_card_size(cell):
            m = ctk.CTkOptionMenu(
                cell,
                variable=self.card_size_var,
                values=["Pequeña", "Mediana", "Grande"],
                width=100,
                command=lambda _=None: self._on_card_size_change(),
            )
            m.pack(anchor="w")
            self._card_size_menu = m
            return m

        _labeled(filters, "Presentación", make_layout)
        _labeled(filters, "Tarjeta", make_card_size)
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
                "Verde=Apply listo · Ámbar=revisión · Rojo=bloqueo · Gris=sin cambios. "
                "Acciones de PLAN no escriben en el juego; ZIP/WORK solo seleccionan candidatos."
            ),
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        legend.pack(fill="x", padx=6, pady=(2, 2))
        self._large_hint = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._large_hint.pack(fill="x", padx=8, pady=(0, 2))

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
            text="Simular cambios (selección)",
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
        self._pager_frame = pager
        self._btn_prev = ctk.CTkButton(
            pager, text="« Anterior", width=100, command=self.prev_page
        )
        self._btn_prev.pack(side="left")
        self.page_label = ctk.CTkLabel(pager, text="Página 1")
        self.page_label.pack(side="left", padx=12)
        self._btn_next = ctk.CTkButton(
            pager, text="Siguiente »", width=100, command=self.next_page
        )
        self._btn_next.pack(side="left")
        self.page_count = ctk.CTkLabel(pager, text="", text_color=COLORS["text_muted"])
        self.page_count.pack(side="right", padx=8)

        self._list_host = ctk.CTkFrame(left, fg_color="transparent")
        self._list_host.pack(side="top", fill="both", expand=True, padx=2, pady=2)

        tree_wrap = tk.Frame(self._list_host, bg="#1a222d", highlightthickness=0)
        self.tree_wrap = tree_wrap
        tree_wrap.pack(side="top", fill="both", expand=True)

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
        self.tree.bind("<Return>", lambda e: app.toggle_selected())

        self.visual_pane = LibraryVisualPane(
            self._list_host,
            on_click=self._on_mod_click,
        )
        self.visual_pane.pack(fill="both", expand=True)
        self.visual_pane.pack_forget()
        # S39: VERDE=preparado Apply · AMARILLO=revisión · ROJO=bloqueo · GRIS=sin cambios
        self.tree.tag_configure("off", background="#2a2a32", foreground="#a0a8b4")
        self.tree.tag_configure("unchanged", background="#2a2a32", foreground="#a0a8b4")
        self.tree.tag_configure("active", background="#1a2e3d", foreground="#c8d0dc")
        self.tree.tag_configure("installed", background="#1a2e3d", foreground="#c8d0dc")
        self.tree.tag_configure("active_inst", background="#1a2e3d", foreground="#c8d0dc")
        self.tree.tag_configure("ready", background="#14352a", foreground="#d8ffe8")
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
        self.detail_state = ctk.CTkLabel(
            right, text="", justify="left", wraplength=280, anchor="w"
        )
        self.detail_state.pack(anchor="w", padx=10, pady=2)
        self.detail_warnings = ctk.CTkLabel(
            right, text="", justify="left", wraplength=280, text_color="#ffb4b4", anchor="w"
        )
        self.detail_warnings.pack(anchor="w", padx=10, pady=0)
        self.detail_provenance = ctk.CTkLabel(
            right, text="", justify="left", wraplength=280, text_color=COLORS["text_muted"]
        )
        self.detail_provenance.pack(anchor="w", padx=10, pady=2)
        self._tech_visible = False
        self._btn_tech = ctk.CTkButton(
            right,
            text="Información técnica ▼",
            width=200,
            fg_color=COLORS["btn_secondary"],
            command=self._toggle_detail_technical,
        )
        self._btn_tech.pack(anchor="w", padx=10, pady=2)

        ctk.CTkLabel(right, text="Descripción", text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=10
        )
        self.detail_desc = ctk.CTkTextbox(right, height=100, wrap="word")
        self.detail_desc.pack(fill="both", expand=True, padx=10, pady=2)

        self.detail_meta = ctk.CTkTextbox(right, height=160, wrap="word")
        self.detail_meta.pack(fill="both", expand=False, padx=10, pady=2)
        self.detail_meta.pack_forget()

        btn_fr = ctk.CTkFrame(right, fg_color="transparent")
        btn_fr.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(
            btn_fr, text="Activar / Desactivar en plan", command=app.toggle_selected
        ).pack(fill="x", pady=2)
        ctk.CTkButton(
            btn_fr, text="Elegir componentes .pak", command=app.choose_pak
        ).pack(
            fill="x", pady=2
        )
        ctk.CTkButton(
            btn_fr, text="Revisar estructura", command=app.review_structure
        ).pack(fill="x", pady=2)
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
            self.detail_state.configure(wraplength=w)
            self.detail_provenance.configure(wraplength=w)
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

    def is_full_view(self) -> bool:
        return self._view_mode == MODE_FULL

    def _sync_view_mode_from_var(self) -> None:
        label = self.view_mode_var.get()
        self._view_mode = UI_TO_MODE.get(label, MODE_PAGINATED)

    def _on_view_mode_change(self) -> None:
        self._sync_view_mode_from_var()
        self.page = 0
        if self.app.session:
            save_library_view_mode(
                self.app.session.record.id,
                self._view_mode,
            )
        self._update_pager_controls()
        self.redraw()

    def _update_pager_controls(self) -> None:
        full = self.is_full_view()
        state = "disabled" if full else "normal"
        try:
            self._btn_prev.configure(state=state)
            self._btn_next.configure(state=state)
        except Exception:
            pass
        if self._page_size_menu is not None:
            try:
                self._page_size_menu.configure(state=state)
            except Exception:
                pass
        if full:
            self.page_label.configure(text="Vista completa")
            self.page_count.configure(text="")

    def apply_view_prefs_for_game(self, game_id: str) -> None:
        mode = load_library_view_mode(game_id)
        self._view_mode = mode
        self.view_mode_var.set(MODE_TO_UI.get(mode, UI_LABEL_PAGINATED))
        layout = load_library_layout(game_id)
        self._layout_mode = layout
        self.layout_var.set(LAYOUT_TO_UI.get(layout, UI_LAYOUT_TABLE))
        cs = load_library_card_size(game_id)
        self._card_size = cs
        self.card_size_var.set(CARD_TO_UI.get(cs, UI_CARD_MEDIUM))
        self._update_pager_controls()
        self._update_layout_controls()
        self._switch_layout_display()

    def _on_layout_change(self) -> None:
        self._layout_mode = UI_TO_LAYOUT.get(self.layout_var.get(), LAYOUT_TABLE)
        if self.app.session:
            save_library_layout(self.app.session.record.id, self._layout_mode)
        self._update_layout_controls()
        self._sync_selection_views()
        self._switch_layout_display()
        self.redraw()

    def _on_card_size_change(self) -> None:
        self._card_size = UI_TO_CARD.get(self.card_size_var.get(), "medium")
        if self.app.session:
            save_library_card_size(self.app.session.record.id, self._card_size)
        if self._layout_mode == LAYOUT_CATALOG:
            self.redraw()

    def _update_layout_controls(self) -> None:
        cat = self._layout_mode == LAYOUT_CATALOG
        state = "normal" if cat else "disabled"
        if self._card_size_menu is not None:
            try:
                self._card_size_menu.configure(state=state)
            except Exception:
                pass

    def _switch_layout_display(self) -> None:
        if self._layout_mode == LAYOUT_TABLE:
            self.visual_pane.pack_forget()
            self.tree_wrap.pack(side="top", fill="both", expand=True)
        else:
            self.tree_wrap.pack_forget()
            self.visual_pane.pack(fill="both", expand=True)
            self.visual_pane.set_thumb_cache(getattr(self.app, "_thumb_cache", None))
            self.visual_pane.set_thumb_async(getattr(self.app, "_thumb_async", None))

    def _on_mod_click(self, folder: str, evt) -> None:
        ctrl = bool(getattr(evt, "state", 0) & 0x4)
        shift = bool(getattr(evt, "state", 0) & 0x1)
        self._library_sel.click(
            folder,
            visible_order=self._visible_order,
            ctrl=ctrl,
            shift=shift,
        )
        self._sync_selection_views()
        self.on_select()

    def _sync_selection_views(self) -> None:
        sel = list(self._library_sel.selected)
        if self._layout_mode == LAYOUT_TABLE:
            ids = [f for f in sel if self.tree.exists(f)]
            if ids:
                self.tree.selection_set(ids)
                self.tree.focus(ids[-1])
            else:
                self.tree.selection_remove(self.tree.selection())
        else:
            self.visual_pane.set_selection(self._library_sel.selected)

    def _toggle_detail_technical(self) -> None:
        self._tech_visible = not self._tech_visible
        if self._tech_visible:
            self.detail_meta.pack(fill="both", expand=False, padx=10, pady=2)
            self._btn_tech.configure(text="Información técnica ▲")
        else:
            self.detail_meta.pack_forget()
            self._btn_tech.configure(text="Información técnica ▼")

    def _catalog_items(self, mods: list) -> list:
        gid = self.app.session.record.id if self.app.session else ""
        intel_map = getattr(self.app, "mod_intel", None) or {}
        struct_map = getattr(self.app, "_structure_by_folder", None) or {}
        inv_map = getattr(self.app, "mod_investigations", None) or {}
        out = []
        for m in mods:
            srep = struct_map.get(m.folder)
            intel = intel_map.get(m.folder)
            inv = inv_map.get(m.folder)
            st = compute_mod_status(
                m, structure_report=srep, intel=intel, investigation=inv
            )
            tag, lab = self._row_tag(m)
            warns = []
            if m.conflicto:
                warns.append(m.conflicto[:120])
            out.append(
                build_catalog_item(
                    m,
                    game_id=gid,
                    status=st,
                    state_tag=tag,
                    state_label=lab,
                    warnings=warns,
                )
            )
        return out

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
        self.tag_var.set(TAG_FILTER_ALL)
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

        struct = getattr(app, "_structure_by_folder", None) or {}
        intel_map = getattr(app, "mod_intel", None) or {}
        inv_map = getattr(app, "mod_investigations", None) or {}
        out = filter_mods(
            app.mods,
            query=self.search_var.get(),
            dimension=self.state_var.get(),
            source=self.source_var.get(),
            tag=self.tag_var.get(),
            structure_by_folder=struct,
            intel_by_folder=intel_map,
            investigation_by_folder=inv_map,
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
        if self.is_full_view():
            return
        if self.page > 0:
            self.page -= 1
            self._paint_page()

    def next_page(self) -> None:
        if self.is_full_view():
            return
        ps = self.page_size()
        max_page = max(0, (len(self._filtered_cache) - 1) // ps)
        if self.page < max_page:
            self.page += 1
            self._paint_page()

    def redraw(self) -> None:
        tags = collect_tags_from_mods(self.app.mods)
        cur = self.tag_var.get()
        self.tag_menu.configure(values=[TAG_FILTER_ALL] + tags)
        if cur not in ([TAG_FILTER_ALL] + tags):
            self.tag_var.set(TAG_FILTER_ALL)
        self._sync_view_mode_from_var()
        self._filtered_cache = self.filtered()
        if not self.is_full_view():
            max_page = max(0, (len(self._filtered_cache) - 1) // self.page_size())
            if self.page > max_page:
                self.page = max_page
        self._paint_page()

    def _row_tag(self, m) -> tuple[str, str]:
        """S39: verde solo si operación Apply preparada sin bloqueos; no por estar en plan."""
        from ...core.apply_confirm import apply_row_visual, mod_apply_pending_flags

        from ...core.structure_resolution import (
            effective_blocks_prepare,
            structure_row_state,
        )

        app = self.app
        plan = getattr(app, "_last_plan", None)
        ready = bool(
            getattr(app, "_analysis_ready", False)
            and getattr(app, "_analysis_for_gen", -1) == getattr(app, "_session_gen", -2)
        )
        reports = getattr(app, "_structure_by_folder", None) or {}
        rep = reports.get(m.folder)
        resolutions = getattr(app, "_structure_resolutions", None) or {}
        res = resolutions.get(m.folder)
        struct = False
        struct_lab = ""
        if rep is not None:
            struct = effective_blocks_prepare(rep, res)
            _tag, struct_lab = structure_row_state(rep, res, usar=m.usar)
        pending = mod_apply_pending_flags(m, plan)
        if pending:
            return apply_row_visual(
                m,
                plan,
                structure_blocks=struct,
                structure_label=struct_lab,
                analysis_ready=ready,
            )
        if struct_lab and m.usar:
            tag, lab = structure_row_state(rep, res, usar=m.usar)
            if tag == "ready":
                tag = "pending"
            return tag, lab
        return apply_row_visual(
            m, plan, structure_blocks=struct, structure_label=struct_lab, analysis_ready=ready
        )

    def _insert_tree_row(self, m, prios: dict) -> None:
        tag, estado = self._row_tag(m)
        prio = prios.get(m.folder, "—")
        name = m.name if len(m.name) <= 48 else m.name[:45] + "…"
        from ...core.component_selection import selected_paks

        sel = selected_paks(m)
        if m.multi and not sel:
            var = "(elige)"
        elif len(sel) > 1:
            var = f"{len(sel)} comps"
        elif sel:
            var = sel[0]
        else:
            var = "—"
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

    def _paint_page(self) -> None:
        app = self.app
        self._pull_tree_selection_if_needed()
        prios = {}
        if app.session:
            from ...core.priority_store import load_priorities

            prios = load_priorities(app.session.priorities_json)

        chunk = display_slice(
            self._filtered_cache,
            mode=self._view_mode,
            page=self.page,
            page_size=self.page_size(),
        )
        self._visible_order = [m.folder for m in chunk]
        if self._layout_mode == LAYOUT_TABLE:
            self.tree.delete(*self.tree.get_children())
            for i, m in enumerate(chunk):
                self._insert_tree_row(m, prios)
                if i and i % TREE_INSERT_BATCH == 0:
                    try:
                        self.tree.update_idletasks()
                    except Exception:
                        pass
        else:
            items = self._catalog_items(chunk)
            layout_key = (
                "catalog" if self._layout_mode == LAYOUT_CATALOG else "visual_list"
            )
            self.visual_pane.start_paint(
                items,
                layout=layout_key,
                card_size=self._card_size,
                selected=set(self._library_sel.selected),
            )

        total = len(self._filtered_cache)
        head, pager_hint, warn_large = list_summary_text(
            mode=self._view_mode,
            total_filtered=total,
            page=self.page,
            page_size=self.page_size(),
            total_in_memory=len(app.mods),
        )
        self.count_label.configure(text=head)
        if self.is_full_view():
            self.page_label.configure(text="Vista completa")
            self.page_count.configure(text="")
        else:
            ps = self.page_size()
            max_page = max(0, (total - 1) // ps) if total else 0
            self.page_label.configure(text=f"Página {self.page + 1} / {max_page + 1}")
            self.page_count.configure(text=pager_hint)
        if self._large_hint is not None:
            if warn_large:
                self._large_hint.configure(
                    text=(
                        f"Vista completa en biblioteca grande ({total} mods); "
                        "puede tardar más al filtrar o cambiar orden."
                    )
                )
            else:
                self._large_hint.configure(text="")
        self._sync_selection_views()
        primary = self._library_sel.primary()
        if primary and self._layout_mode == LAYOUT_TABLE and self.tree.exists(primary):
            self.tree.see(primary)
        self._update_sel_count()

    def _pull_tree_selection_if_needed(self) -> None:
        if self._layout_mode != LAYOUT_TABLE:
            return
        ts = list(self.tree.selection())
        if ts:
            self._library_sel.set_folders(ts)
            focus = self.tree.focus()
            if focus:
                self._library_sel.anchor = focus

    def selected(self):
        self._pull_tree_selection_if_needed()
        fid = self._library_sel.primary()
        return self.app.by_id.get(fid) if fid else None

    def selected_many(self) -> list:
        self._pull_tree_selection_if_needed()
        out = []
        for fid in self._library_sel.selected:
            m = self.app.by_id.get(fid)
            if m:
                out.append(m)
        return out

    def select_page(self) -> None:
        self._library_sel.set_folders(list(self._visible_order))
        self._sync_selection_views()
        self._update_sel_count()
        self.on_select()

    def select_filtered(self) -> None:
        """Selecciona filtrados visibles; en vista completa = todos los filtrados."""
        self.select_page()
        n = len(self._filtered_cache)
        self.app._bulk_filter_folders = [m.folder for m in self._filtered_cache]
        vis = len(self.selected_many())
        if hasattr(self, "sel_count"):
            if self.is_full_view() or n <= self.page_size():
                self.sel_count.configure(text=f"{vis} sel. / {n} filtrados")
            else:
                self.sel_count.configure(text=f"{vis} vis. / {n} filtrados")

    def clear_selection(self) -> None:
        self._library_sel.clear()
        self.tree.selection_remove(self.tree.selection())
        self.visual_pane.set_selection(set())
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
            n = len(self.selected_many())
            extra = getattr(self.app, "_bulk_filter_folders", None)
            if extra and len(extra) > n:
                self.sel_count.configure(text=f"{n} vis. / {len(extra)} filtrados")
            else:
                self.sel_count.configure(text=f"{n} sel.")

    def _on_tree_select(self, _evt=None) -> None:
        sel = list(self.tree.selection())
        self._library_sel.set_folders(sel)
        if sel:
            focus = self.tree.focus()
            if focus:
                self._library_sel.anchor = focus
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

        struct_map = getattr(self.app, "_structure_by_folder", None) or {}
        srep = struct_map.get(m.folder)
        intel = (getattr(self.app, "mod_intel", None) or {}).get(m.folder)
        inv = (getattr(self.app, "mod_investigations", None) or {}).get(m.folder)
        st = compute_mod_status(
            m, structure_report=srep, intel=intel, investigation=inv
        )
        conf_txt = m.conflicto if m.conflicto else "(sin conflicto reportado)"
        prov_txt = intel.provenance_summary() if intel else "(intel Vortex no cargada)"
        from ...core.player_support_messages import (
            player_facing_investigation,
            player_facing_unknown_mod,
        )

        player_inv = player_facing_investigation(inv)
        inv_txt = inv.library_summary() if inv else "(investigación S49 no cargada)"
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
        if srep is not None:
            grp_bits = []
            for g in (srep.groups or [])[:6]:
                miss = f" falta {','.join(g.missing)}" if g.missing else " OK"
                grp_bits.append(f"{g.stem}{miss}")
            var_bits = [
                f"{v.label} ({len(v.members)})" for v in (srep.variants or [])[:6]
            ]
            iss_bits = [
                f"{i.code}: {i.message}" for i in (srep.issues or [])[:5] if i.confirmed
            ]
            struct_txt = (
                f"Formato: {srep.format_label}\n"
                f"Clasificación: {srep.classification} ({srep.certainty.value})\n"
                f"Estructura: {srep.explanation}\n"
                f"Instalables: {len(srep.installable)} · Grupos: {len(srep.groups)} · "
                f"Variantes: {len(srep.variants)}\n"
                f"Grupos: {'; '.join(grp_bits) if grp_bits else '(ninguno)'}\n"
                f"Variantes: {'; '.join(var_bits) if var_bits else '(ninguna)'}\n"
                f"Problemas: {'; '.join(iss_bits) if iss_bits else '(ninguno confirmado)'}\n"
                f"Bloqueo prep.: {'SI' if srep.blocks_prepare else 'no'} · "
                f"Revisión: {'SI' if srep.needs_manual_review else 'no'}\n"
                f"Motivo bloqueo: "
                f"{srep.explanation if srep.blocks_prepare else '(no aplica)'}\n"
            )
        else:
            struct_txt = (
                "Estructura: (sin análisis aún — use Actualizar / Analizar plan)\n"
            )
        from ...core.library_catalog_model import tags_for_mod

        plan_txt = "Activo en plan (usar): SÍ" if m.usar else "Activo en plan (usar): NO"
        disk_txt = "En destino juego: SÍ" if m.on_disk else "En destino juego: NO"
        self.detail_state.configure(
            text=(
                f"{plan_txt} · {disk_txt}\n"
                f"Estado: {st.row_label}\n"
                f"Etiquetas: {', '.join(tags_for_mod(m)) or '—'}\n"
                f"Categoría: {m.category or '—'}\n"
                f"Fuente datos: {src}\n"
                f"Flags: {status_badges_text(st)}"
            )
        )
        warn_lines = [conf_txt] if conf_txt and conf_txt != "(sin conflicto reportado)" else []
        if srep is not None and srep.needs_manual_review:
            warn_lines.append("Revisión de estructura recomendada.")
        if srep is not None and srep.blocks_prepare:
            warn_lines.append("Bloqueo de preparación / Apply.")
        if inv is not None and not getattr(inv, "f7777_installable", False):
            warn_lines.append(
                player_facing_unknown_mod(mod_name=m.nexus_mod_name or m.name).split("\n")[0]
            )
        self.detail_warnings.configure(
            text=("Advertencias: " + " · ".join(warn_lines)) if warn_lines else ""
        )
        # S50 — resumen claro al jugador; detalle técnico solo en «Información técnica»
        self.detail_provenance.configure(
            text=(
                f"{player_inv}\n\n"
                f"Procedencia\n{prov_txt}\n\n"
                f"Paquete origen: "
                f"{getattr(m, 'package_name', '') or getattr(m, 'package_folder', '') or '—'}\n"
                f"Staging: {staging_txt}\n"
                f"Juego: {game_name} · Id: {m.folder[:48]}{'…' if len(m.folder)>48 else ''}"
            )
        )

        self.detail_desc.configure(state="normal")
        self.detail_desc.delete("1.0", "end")
        self.detail_desc.insert("1.0", m.description or "(sin descripción)")
        self.detail_desc.configure(state="normal")  # scrollable editable view OK

        plan_hint = ""
        last_plan = getattr(self.app, "_last_plan", None)
        if self.app.session:
            from ...core.plan_diagnostics import diagnose_mod

            diag = diagnose_mod(
                m,
                last_plan,
                adapter_id=self.app.session.adapter_id,
                mods_dest=self.app._ctx().mods,
            )
            plan_hint = (
                f"\nPlan / simulación (mod en detalle):\n"
                f"  Activo en loadout (usar): {'SÍ' if m.usar else 'NO'}\n"
                f"  Archivos en plan deseado: {len(diag.planned_files)}\n"
            )
            for r in diag.reasons[:5]:
                plan_hint += f"  ⚠ {r}\n"
            if m.usar and not diag.planned_files and not diag.reasons:
                plan_hint += "  ⚠ Sin archivos preparados — pulse «Simular plan».\n"
            plan_hint += (
                "  Simular plan = loadout · Simular selección = filas marcadas · "
                "Simular este mod = solo esta fila.\n"
            )

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
                f"Componentes: "
                f"{', '.join(getattr(m, 'paks_elegidos', None) or ([m.pak_elegido] if m.pak_elegido else [])) or ('(elige)' if m.multi else '—')}\n"
                f"Modo selección: {getattr(m, 'selection_mode', '') or '(auto)'}\n"
                f"Multi: {'SI' if m.multi else 'NO'}  ·  Paks conocidos: {len(m.paks)}\n"
                f"Payload: {len(getattr(m, 'payload_files', None) or [])} "
                f"exts={', '.join(getattr(m, 'payload_exts', None) or []) or '—'}\n"
                f"Tipo: {m.category or '(no disponible)'}\n"
                f"Etiquetas motor: {', '.join(tags_for_mod(m)) or '(ninguna)'}\n"
                f"{struct_txt}"
                f"Autor: {author_txt}\n"
                f"Tamaño: {size_txt}\n"
                f"Ruta staging: {m.stage_path or '(no disponible)'}\n"
                f"ZIP propio: {getattr(m, 'archive_path', '') or '(no disponible)'}\n"
                f"Slots: {', '.join(m.slots) or '(no disponible)'}\n"
                f"{plan_hint}"
                f"{cls_txt}"
                f"\nDetalle avanzado investigación (S49)\n{inv_txt}\n"
                f"\nArchivos relevantes (plan / staging):\n{files_txt}"
            ),
        )
        self.detail_meta.configure(state="disabled")
        self.app.show_thumb_for(m, self.detail_image)

    def refresh(self) -> None:
        if self.app.session:
            self.apply_view_prefs_for_game(self.app.session.record.id)
        try:
            self._refresh_staging_labels()
        except Exception:
            self.app._staging_labels = {}
        self.redraw()
