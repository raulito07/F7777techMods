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

S06 — shell de navegación + controlador de sesión (CustomTkinter).
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, filedialog

import customtkinter as ctk
from PIL import Image

from ..branding import PRODUCT_NAME, window_title
from ..version import __version__
from ..core.inventory import scan_staging, ModEntry
from ..core.descriptions import apply_descriptions, save_override
from ..core.conflicts import evaluate
from ..core.loadout_store import merge_loadout, save_loadout, load_loadout
from ..core.apply import plan_apply, execute, vortex_deploy_present, ApplyError
from ..core.conflict_engine import semantic_enabled
from ..core.thumbs import extract_vortex_meta, ensure_thumb, prefetch_thumbs, thumb_path_for
from ..core.vortex_sync import apply_vortex_enablement, disable_all
from ..core.paths import ROOT, UI_SETTINGS_JSON, DATA
from ..core.adapters import adapter_choices, adapter_id_from_choice, suggest_mods_dir
from ..core.games import (
    GameRecord,
    GamePaths,
    GamesRegistry,
    ensure_registry,
    save_registry,
    game_paths_for,
    add_game,
    update_game,
    remove_game,
    set_active_game,
    ensure_game_data_dir,
    validate_game_paths,
    destination_conflict_message,
    prepare_ff7r_migration,
    default_record_from_root,
)

from .theme import COLORS, NAV_ITEMS
from .dialogs import ProgressBarHost, ask_scroll_confirm, show_scroll_text
from .views import (
    SummaryView,
    LibraryView,
    ConflictsView,
    InstalledView,
    StorageArchiveView,
    HistoryView,
    SettingsView,
    AboutView,
)

ZOOM_MIN = 90
ZOOM_MAX = 180
ZOOM_STEP = 10
ZOOM_DEFAULT = 125


def _fmt_bytes_ui(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KiB", 1024), ("MiB", 1024**2), ("GiB", 1024**3)):
        if n < div * 1024 or unit == "GiB":
            return f"{n / div:.2f} {unit}"
    return f"{n} B"


class ModManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(window_title())
        self.geometry("1480x900")
        self.minsize(1100, 700)
        self.configure(fg_color=COLORS["bg_app"])

        self.mods: list[ModEntry] = []
        self.by_id: dict[str, ModEntry] = {}
        self.vortex_meta: dict = {}
        self._photo_ref = None
        self._last_plan = None
        self._analyze_gen = 0
        self._session_gen = 0
        self._busy_plan = False
        self._busy_write = False
        self._selected_folder = ""
        self._current_view = "summary"
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._analysis_ready = False
        self._analysis_for_gen = -1
        self.zoom = self._load_zoom()
        self.game_var = tk.StringVar(value="")

        self.registry: GamesRegistry = ensure_registry()
        self.session: GamePaths | None = None
        self._reload_session()

        self._build_shell()
        self._refresh_game_selector()
        self.apply_zoom()
        self.refresh()
        self.show_view("summary")
        self._maybe_show_migration_notice()

    # ---------- session / locks ----------
    def is_busy(self) -> bool:
        return bool(self._busy_plan or self._busy_write)

    def _reload_session(self) -> None:
        self._session_gen += 1
        gid = self.registry.active_game_id
        if gid and gid in self.registry.games:
            self.session = game_paths_for(self.registry.games[gid])
            ensure_game_data_dir(self.session)
        else:
            self.session = None

    def _ctx(self):
        if not self.session:
            raise RuntimeError("No hay juego activo configurado.")
        # S10: sin destino verificado — sandbox bajo data_dir (nunca escribe al juego)
        if not self.session.record.mods_dir.strip():
            from ..core.apply import ApplyContext

            sandbox = self.session.data_dir / "_no_destination"
            sandbox.mkdir(parents=True, exist_ok=True)
            return ApplyContext(
                mods=sandbox,
                deploy=sandbox / "vortex.deployment.json",
                loadout_marker=sandbox / "_manual_loadout.json",
                manifest=self.session.data_dir / "managed_manifest.json",
                backups=self.session.data_dir / "backups",
                stage=self.session.stage_dir or Path("."),
                data_dir=self.session.data_dir,
            )
        return self.session.apply_context()

    def _settings(self):
        if not self.session:
            raise RuntimeError("No hay juego activo configurado.")
        return self.session.conflict_settings()

    def _semantic(self) -> bool:
        if not self.session:
            return False
        return semantic_enabled(self.session.adapter_id)

    # ---------- zoom / appearance ----------
    def _load_zoom(self) -> int:
        try:
            if UI_SETTINGS_JSON.exists():
                data = json.loads(UI_SETTINGS_JSON.read_text(encoding="utf-8"))
                z = int(data.get("zoom", ZOOM_DEFAULT))
                return max(ZOOM_MIN, min(ZOOM_MAX, z))
        except Exception:
            pass
        return ZOOM_DEFAULT

    def _save_zoom(self) -> None:
        DATA.mkdir(parents=True, exist_ok=True)
        payload = {"zoom": self.zoom}
        try:
            if UI_SETTINGS_JSON.exists():
                old = json.loads(UI_SETTINGS_JSON.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    old["zoom"] = self.zoom
                    payload = old
        except Exception:
            pass
        UI_SETTINGS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_zoom(self, value: int) -> None:
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, int(value)))
        self._save_zoom()
        self.apply_zoom()
        if hasattr(self, "view_settings"):
            self.view_settings.refresh()
        if hasattr(self, "view_library"):
            self.view_library.apply_zoom(self.zoom / 100.0)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom + ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom - ZOOM_STEP)

    def zoom_reset(self) -> None:
        self.set_zoom(ZOOM_DEFAULT)

    def _on_mousewheel_zoom(self, event) -> None:
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def set_appearance(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)

    def apply_zoom(self) -> None:
        scale = self.zoom / 100.0
        body = max(10, int(round(11 * scale)))
        title = max(16, int(round(20 * scale)))
        row_h = max(26, int(round(30 * scale)))
        if hasattr(self, "title_label"):
            self.title_label.configure(
                font=ctk.CTkFont(family="Segoe UI Semibold", size=title)
            )
        if hasattr(self, "status"):
            self.status.configure(font=ctk.CTkFont(size=max(11, body)))
        try:
            from tkinter import ttk

            style = ttk.Style(self)
            style.configure(
                "Lib.Treeview",
                background="#1e1e2e",
                foreground="#e8e8e8",
                fieldbackground="#1e1e2e",
                rowheight=row_h,
                borderwidth=0,
                font=("Segoe UI", body),
            )
            style.configure(
                "Lib.Treeview.Heading",
                background="#2b2d42",
                foreground="#ffffff",
                font=("Segoe UI Semibold", max(11, body)),
                relief="flat",
            )
        except Exception:
            pass

    # ---------- shell ----------
    def _build_shell(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_header"], corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.title_label = ctk.CTkLabel(
            header,
            text=f"{PRODUCT_NAME}  ·  v{__version__}",
            font=ctk.CTkFont(family="Segoe UI Semibold", size=18),
            text_color=COLORS["text"],
        )
        self.title_label.pack(side="left", padx=20, pady=12)
        self.status = ctk.CTkLabel(header, text="", text_color=COLORS["text_muted"])
        self.status.pack(side="right", padx=16)

        # Game bar (always visible)
        game_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_muted"], corner_radius=0)
        game_bar.pack(fill="x")
        ctk.CTkLabel(game_bar, text="Juego activo", text_color=COLORS["text_muted"]).pack(
            side="left", padx=(16, 8), pady=10
        )
        self.game_menu = ctk.CTkOptionMenu(
            game_bar,
            variable=self.game_var,
            values=["(sin juegos)"],
            width=340,
            command=self._on_game_selected,
        )
        self.game_menu.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            game_bar,
            text="1 Actualizar → 2 Preparar plan → 3 Simular → 4 Aplicar",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(4, 8))
        ctk.CTkButton(
            game_bar, text="1·Actualizar", width=100, command=self.refresh
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            game_bar,
            text="3·Simular",
            width=90,
            fg_color=COLORS["btn_secondary"],
            command=self.simulate,
        ).pack(side="left", padx=3)
        self.apply_btn = ctk.CTkButton(
            game_bar,
            text="4·Aplicar",
            width=90,
            fg_color=COLORS["btn_apply"],
            command=self.apply_to_game,
            state="disabled",
        )
        self.apply_btn.pack(side="left", padx=3)
        ctk.CTkButton(
            game_bar,
            text="Conflictos",
            width=100,
            fg_color=COLORS["btn_warn"],
            command=lambda: self.show_view("conflicts"),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            game_bar,
            text="Guardar plan",
            width=100,
            command=self.save_plan,
        ).pack(side="left", padx=3)

        # Progress
        self.progress = ProgressBarHost(self)
        self.progress.pack_hide()

        # Body: sidebar + content
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(body, width=200, fg_color=COLORS["bg_sidebar"], corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(
            sidebar,
            text="NAVEGACIÓN",
            text_color=COLORS["text_muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        for key, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                fg_color="transparent",
                text_color=COLORS["text"],
                hover_color=COLORS["nav_active"],
                command=lambda k=key: self.show_view(k),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_buttons[key] = btn

        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        self.view_summary = SummaryView(self.content, self)
        self.view_library = LibraryView(self.content, self)
        self.view_conflicts = ConflictsView(self.content, self)
        self.view_installed = InstalledView(self.content, self)
        self.view_storage = StorageArchiveView(self.content, self)
        self.view_history = HistoryView(self.content, self)
        self.view_settings = SettingsView(self.content, self)
        self.view_about = AboutView(self.content, self)
        self._archive_catalog = None
        self._archive_view_text = ""
        self._archive_cancel = False
        self._archive_pause = False
        self._archive_job = None
        self._work_index = None
        self._bulk_filter_folders = None
        self._isolated_plan_folders: list[str] | None = None
        self._structure_by_folder: dict = {}
        self._structure_cache: dict = {}
        self._structure_blocks_apply: bool = False
        self._views = {
            "summary": self.view_summary,
            "library": self.view_library,
            "conflicts": self.view_conflicts,
            "installed": self.view_installed,
            "storage": self.view_storage,
            "history": self.view_history,
            "settings": self.view_settings,
            "about": self.view_about,
        }

        self.footer_label = ctk.CTkLabel(
            self, text="", text_color=COLORS["text_muted"], justify="left"
        )
        self.footer_label.pack(fill="x", padx=16, pady=(0, 8))

        self.bind_all("<Control-plus>", lambda e: self.zoom_in())
        self.bind_all("<Control-equal>", lambda e: self.zoom_in())
        self.bind_all("<Control-minus>", lambda e: self.zoom_out())
        self.bind_all("<Control-0>", lambda e: self.zoom_reset())
        self.bind_all("<Control-MouseWheel>", self._on_mousewheel_zoom)
        if hasattr(self, "view_library"):
            self.view_library.apply_zoom(self.zoom / 100.0)
        self._sync_apply_button()

    def plan_is_applyable(self) -> bool:
        """True solo con análisis vigente del juego actual y sin bloqueos."""
        if not self.session or self.is_busy():
            return False
        # S10: sin destino verificado no hay Apply
        if not bool(getattr(self.session.record, "destination_verified", False)):
            return False
        if not self.session.record.mods_dir.strip():
            return False
        if not self._analysis_ready or self._analysis_for_gen != self._session_gen:
            return False
        plan = self._last_plan
        if plan is None:
            return False
        if plan.conflicts or plan.file_unresolved or plan.errors:
            return False
        if getattr(self, "_structure_blocks_apply", False):
            return False
        try:
            if vortex_deploy_present(self._ctx()):
                return False
        except Exception:
            return False
        return True

    def _sync_apply_button(self) -> None:
        if not hasattr(self, "apply_btn"):
            return
        ok = self.plan_is_applyable()
        self.apply_btn.configure(state="normal" if ok else "disabled")
        if not self.session:
            tip = "Sin juego"
        elif self.is_busy():
            tip = "Operación en curso"
        elif not self._analysis_ready or self._analysis_for_gen != self._session_gen:
            tip = "Analizando plan…"
        elif not bool(getattr(self.session.record, "destination_verified", False)):
            tip = "Destino no verificado — Apply bloqueado"
        elif self._last_plan and (
            self._last_plan.conflicts
            or self._last_plan.file_unresolved
            or self._last_plan.errors
        ):
            tip = "Plan bloqueado — ver Conflictos"
        elif getattr(self, "_structure_blocks_apply", False):
            tip = "Estructura incompleta/ambigua — revisión manual"
        else:
            tip = "Listo para aplicar" if ok else "No aplicable"
        try:
            self.apply_btn.configure(text="Aplicar" if ok else "Aplicar (bloq.)")
        except Exception:
            pass
        self._apply_tip = tip

    def show_view(self, key: str) -> None:
        if key not in self._views:
            return
        self._current_view = key
        for k, view in self._views.items():
            view.pack_forget()
            btn = self._nav_buttons.get(k)
            if btn:
                btn.configure(
                    fg_color=COLORS["nav_active"] if k == key else "transparent"
                )
        self._views[key].pack(fill="both", expand=True)
        # Refresh visible view
        view = self._views[key]
        if hasattr(view, "refresh"):
            view.refresh()

    # ---------- game selector ----------
    def _game_label(self, g: GameRecord) -> str:
        return f"{g.name}  [{g.id}]"

    def _id_from_label(self, label: str) -> str:
        if "[" in label and label.endswith("]"):
            return label[label.rfind("[") + 1 : -1]
        return ""

    def _refresh_game_selector(self) -> None:
        games = list(self.registry.games.values())
        if not games:
            self.game_menu.configure(values=["(sin juegos)"])
            self.game_var.set("(sin juegos)")
            return
        labels = [self._game_label(g) for g in games]
        self.game_menu.configure(values=labels)
        active = self.registry.games.get(self.registry.active_game_id)
        if active:
            self.game_var.set(self._game_label(active))
        else:
            self.game_var.set(labels[0])

    def _on_game_selected(self, choice: str) -> None:
        if self.is_busy():
            messagebox.showinfo(
                "Operación en curso",
                "No se puede cambiar de juego durante una instalación o cálculo.",
            )
            self._refresh_game_selector()
            return
        gid = self._id_from_label(choice)
        if not gid or gid == self.registry.active_game_id:
            return
        errs = set_active_game(self.registry, gid)
        if errs:
            messagebox.showerror("No se puede cambiar de juego", "\n".join(errs))
            self._refresh_game_selector()
            return
        save_registry(self.registry)
        self._reload_session()
        self._last_plan = None
        self._analysis_ready = False
        self._analysis_for_gen = -1
        self._sync_apply_button()
        self.refresh()
        self.show_view(self._current_view)

    def _update_footer(self) -> None:
        if not self.session:
            self.footer_label.configure(text="Sin juego activo. Usa «Juegos y ajustes».")
            return
        r = self.session.record
        self.footer_label.configure(
            text=(
                f"{r.name}  |  {r.adapter}  |  Staging: {self.session.stage_dir}  |  "
                f"Destino: {self.session.mods_dir}  |  Zoom {self.zoom}%"
            )
        )

    def _maybe_show_migration_notice(self) -> None:
        g = self.registry.games.get(self.registry.active_game_id)
        if g and g.migration_status == "pending" and g.migration_note:
            self.after(
                400,
                lambda: messagebox.showinfo(
                    "Migración FF7R pendiente",
                    g.migration_note
                    + "\n\nUsa «Juegos y ajustes» → Migración FF7R…\n"
                    "No se ha tocado Steam ni Vortex.",
                ),
            )

    def _enrich_mod_sources(self) -> None:
        """S15: procedencia + WORK_LIBRARY / ARCHIVO_PROPIO (sin mezclar rutas)."""
        if not self.session:
            return
        from ..core.mod_source import (
            SOURCE_WORK_LIBRARY,
            annotate_staging_mods,
            enrich_from_work_index,
            switch_mod_to_work_source,
        )
        from ..core.real_archive_job import STATUS_OK, job_path, load_job
        from ..core.work_library import load_index

        annotate_staging_mods(self.mods)
        work = self._work_root()
        idx = load_index(work, game_id=self.session.record.id)
        self._work_index = idx
        self.mods = enrich_from_work_index(
            self.mods, idx, stage_root=self.session.stage_dir
        )
        job = self._archive_job or load_job(job_path(self.session.data_dir))
        archived_folders = set()
        if job:
            for it in job.items.values():
                if it.status == STATUS_OK:
                    archived_folders.add(it.folder)
        for m in self.mods:
            if m.folder in archived_folders or m.archive_path:
                m.archived = True
            if m.mod_id and m.mod_id in idx.mods:
                m.work_extracted = True
        # Fuente predeterminada WORK_LIBRARY: cambiar explícitamente si hay extract
        pref = (getattr(self.session.record, "default_mod_source", "") or "").upper()
        if pref == SOURCE_WORK_LIBRARY:
            for m in self.mods:
                if m.work_extracted and m.source_kind != SOURCE_WORK_LIBRARY:
                    switch_mod_to_work_source(m, idx)

    # ---------- data refresh ----------
    def refresh(self) -> None:
        self._session_gen += 1
        gen = self._session_gen
        self._analysis_ready = False
        self._sync_apply_button()
        if not self.session:
            self.mods = []
            self.by_id = {}
            self._update_footer()
            self.status.configure(text="Sin juego activo")
            self.view_summary.refresh()
            self.view_library.refresh()
            return

        ensure_game_data_dir(self.session)
        ctx = self._ctx()
        self.vortex_meta = extract_vortex_meta(
            force=False,
            vortex_game_id=self.session.vortex_game_id or None,
            meta_cache=self.session.meta_cache,
        )
        self.mods = scan_staging(self.session.stage_dir, deploy_path=ctx.deploy)
        merge_loadout(self.mods, self.session.loadout_json)
        self._enrich_mod_sources()
        apply_descriptions(
            self.mods,
            self.vortex_meta,
            overrides_path=self.session.desc_override,
        )
        for m in self.mods:
            meta = self.vortex_meta.get(m.folder) or {}
            if meta.get("pictureUrl"):
                m.picture_url = meta["pictureUrl"]
            cand = thumb_path_for(
                m.folder,
                meta.get("modId"),
                meta.get("pictureUrl") or "",
                thumbs_dir=self.session.thumbs_dir,
            )
            if cand.exists():
                m.thumb_path = str(cand)
        evaluate(self.mods, semantic=self._semantic())
        self.by_id = {m.folder: m for m in self.mods}
        self._update_footer()
        self.view_library.refresh()
        self.view_summary.refresh()
        self.analyze_conflicts()
        folders = [
            m.folder
            for m in self.mods
            if (self.vortex_meta.get(m.folder) or {}).get("pictureUrl")
        ]
        prefetch_thumbs(
            self.vortex_meta,
            folders,
            on_done=lambda: self.after(0, lambda: self._thumbs_ready(gen)),
            thumbs_dir=self.session.thumbs_dir,
        )
        self._update_status_bar()

    def _thumbs_ready(self, gen: int) -> None:
        if gen != self._session_gen or not self.session:
            return
        for m in self.mods:
            meta = self.vortex_meta.get(m.folder) or {}
            cand = thumb_path_for(
                m.folder,
                meta.get("modId"),
                meta.get("pictureUrl") or "",
                thumbs_dir=self.session.thumbs_dir,
            )
            if cand.exists():
                m.thumb_path = str(cand)
        if self._current_view == "library":
            m = self.view_library.selected()
            if m:
                self.show_thumb_for(m, self.view_library.detail_image)

    def analyze_conflicts(self, on_done=None) -> None:
        if not self.session:
            return
        self._analyze_gen += 1
        gen = self._analyze_gen
        session_gen = self._session_gen
        game_id = self.registry.active_game_id
        self._analysis_ready = False
        self._sync_apply_button()
        mods_snapshot = list(self.mods)
        ctx = self._ctx()
        settings = self._settings()

        adapter_id = (
            str(getattr(self.session.record, "adapter", "") or "generic_folder")
            if self.session
            else "generic_folder"
        )
        struct_cache = getattr(self, "_structure_cache", None)
        if struct_cache is None:
            self._structure_cache = {}
            struct_cache = self._structure_cache

        def worker():
            from ..core.mod_structure import (
                analyze_library_structures,
                structure_blocks_apply,
            )

            try:
                plan = plan_apply(mods_snapshot, ctx, settings)
            except Exception:
                plan = None
            try:
                structures = analyze_library_structures(
                    mods_snapshot,
                    adapter_id,
                    cache=struct_cache,
                    only_usar=False,
                )
                blocks = structure_blocks_apply(structures, mods_snapshot)
            except Exception:
                structures = {}
                blocks = False

            def done():
                if gen != self._analyze_gen or session_gen != self._session_gen:
                    return
                if game_id != self.registry.active_game_id:
                    return
                try:
                    if not self.winfo_exists():
                        return
                except Exception:
                    return
                self._last_plan = plan
                self._analysis_ready = plan is not None
                self._analysis_for_gen = session_gen
                self._structure_by_folder = structures
                self._structure_blocks_apply = bool(blocks)
                self._merge_file_conflict_labels()
                self._merge_structure_labels()
                # Solo repintar biblioteca (no resetear página/filtros de más)
                self.view_library.redraw()
                self.view_summary.refresh()
                self._update_status_bar()
                self._sync_apply_button()
                if on_done:
                    on_done()

            try:
                self.after(0, done)
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _merge_structure_labels(self) -> None:
        """Anota bloqueos de estructura en la etiqueta de conflicto (solo UI/plan)."""
        reports = getattr(self, "_structure_by_folder", None) or {}
        for m in self.mods:
            r = reports.get(m.folder)
            if not r or not r.blocks_prepare:
                continue
            tag = f"ESTRUCTURA:{r.classification}"
            if tag not in (m.conflicto or ""):
                m.conflicto = (
                    f"{m.conflicto}; {tag}".strip("; ") if m.conflicto else tag
                )

    def _merge_file_conflict_labels(self) -> None:
        plan = self._last_plan
        if not plan or not plan.analysis:
            return
        for fc in plan.analysis.file_conflicts:
            if fc.resolved:
                continue
            for o in fc.offers:
                m = self.by_id.get(o.mod_folder)
                if not m or not m.usar:
                    continue
                label = fc.kind.value
                if label not in (m.conflicto or ""):
                    m.conflicto = (
                        f"{m.conflicto}; {label}".strip("; ") if m.conflicto else label
                    )

    def _update_status_bar(self) -> None:
        if not self.session:
            self.status.configure(text="Sin juego activo")
            return
        on = sum(1 for m in self.mods if m.usar)
        plan = self._last_plan
        if not self._analysis_ready or self._analysis_for_gen != self._session_gen:
            blockers = "…"
        elif plan is None:
            blockers = "?"
        else:
            blockers = int(plan.conflicts)
        try:
            deploy = "DEPLOY Vortex" if vortex_deploy_present(self._ctx()) else "OK"
        except Exception:
            deploy = "?"
        apply_state = "Aplicar OK" if self.plan_is_applyable() else "Aplicar bloq."
        mode = "COPY"
        if self.session:
            mode = str(getattr(self.session.record, "install_mode", "COPY") or "COPY")
        add = upd = rem = 0
        if plan is not None and self._analysis_ready:
            add, upd, rem = len(plan.to_add), len(plan.to_update), len(plan.to_remove)
        scope = "plan completo"
        if self._isolated_plan_folders is not None:
            scope = f"aislado ({len(self._isolated_plan_folders)})"
        self.status.configure(
            text=(
                f"{self.session.record.name if self.session else '?'} · "
                f"{len(self.mods)} mods · {on} plan · "
                f"+{add}/~{upd}/-{rem} · conf {blockers} · {mode} · "
                f"Vortex {deploy} · {scope} · {apply_state}"
            )
        )

    # ---------- thumbs ----------
    def show_thumb_for(self, m: ModEntry, label_widget) -> None:
        if not self.session:
            return
        meta = self.vortex_meta.get(m.folder) or {}
        path = m.thumb_path
        if (not path or not Path(path).exists()) and meta.get("pictureUrl"):
            cand = thumb_path_for(
                m.folder,
                meta.get("modId"),
                meta.get("pictureUrl") or "",
                thumbs_dir=self.session.thumbs_dir,
            )
            if cand.exists():
                path = str(cand)
                m.thumb_path = path
            else:
                folder = m.folder
                session_gen = self._session_gen

                def worker():
                    got = ensure_thumb(folder, meta, thumbs_dir=self.session.thumbs_dir)
                    if not got:
                        return

                    def apply():
                        if session_gen != self._session_gen:
                            return
                        sel = self.view_library.selected()
                        if sel and sel.folder == folder:
                            sel.thumb_path = str(got)
                            self._paint_thumb(str(got), label_widget)

                    self.after(0, apply)

                threading.Thread(target=worker, daemon=True).start()
        if path and Path(path).exists():
            self._paint_thumb(path, label_widget)
            return
        self._photo_ref = None
        label_widget.configure(image=None, text="(sin imagen Nexus/Vortex)")

    def _paint_thumb(self, path: str, label_widget) -> None:
        try:
            scale = self.zoom / 100.0
            w = int(300 * min(max(scale, 0.9), 1.4))
            h = int(160 * min(max(scale, 0.9), 1.4))
            img = Image.open(path)
            img.thumbnail((w, h))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._photo_ref = ctk_img
            label_widget.configure(image=ctk_img, text="")
        except Exception:
            label_widget.configure(image=None, text="(sin imagen Nexus/Vortex)")

    # ---------- library actions ----------
    def selected(self) -> ModEntry | None:
        if self._current_view == "library":
            return self.view_library.selected()
        if self._selected_folder:
            return self.by_id.get(self._selected_folder)
        return None

    def toggle_selected(self) -> None:
        m = self.selected()
        if not m:
            return
        m.usar = not m.usar
        if m.usar and m.multi and not m.pak_elegido:
            self.choose_pak()
        self._isolated_plan_folders = None
        self.view_library.redraw()
        self.view_summary.refresh()
        # Reanalizar (invalidará Aplicar hasta completar)
        self.analyze_conflicts()
        # Refrescar detalle del mod seleccionado sin análisis extra
        self.view_library.on_select()

    def bulk_plan_activate(self) -> None:
        """Activa mods en el PLAN (memoria). No escribe en el juego."""
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Hay una operación en curso.")
            return
        mods = self.view_library.bulk_target_mods()
        if not mods:
            messagebox.showinfo("Selección", "Selecciona mods o usa «Sel. filtrados».")
            return
        n = 0
        pending_var = 0
        for m in mods:
            m.usar = True
            n += 1
            if m.multi and not m.pak_elegido:
                pending_var += 1
        self._bulk_filter_folders = None
        self._isolated_plan_folders = None
        self.view_library.redraw()
        self.view_summary.refresh()
        self.analyze_conflicts()
        messagebox.showinfo(
            "Plan actualizado",
            f"Activados en plan: {n}.\n"
            f"Variante pendiente: {pending_var}.\n\n"
            "No se ha escrito nada en el juego. Usa Simular / Aplicar.",
        )

    def bulk_plan_deactivate(self) -> None:
        """Desactiva mods en el PLAN (memoria). No escribe en el juego."""
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Hay una operación en curso.")
            return
        mods = self.view_library.bulk_target_mods()
        if not mods:
            messagebox.showinfo("Selección", "Selecciona mods o usa «Sel. filtrados».")
            return
        for m in mods:
            m.usar = False
        self._bulk_filter_folders = None
        self._isolated_plan_folders = None
        self.view_library.redraw()
        self.view_summary.refresh()
        self.analyze_conflicts()
        messagebox.showinfo(
            "Plan actualizado",
            f"Desactivados en plan: {len(mods)}.\n"
            "No se ha escrito nada en el juego hasta Aplicar.",
        )

    def simulate_selection_plan(self) -> None:
        """Simula plan solo con la selección (aislado). No guarda loadout ni Apply."""
        if not self.session or self.is_busy():
            return
        mods = self.view_library.bulk_target_mods()
        if not mods:
            messagebox.showinfo("Simular selección", "Selecciona al menos un mod.")
            return
        # Activar temporalmente solo estos en el snapshot de simulación
        folders = {m.folder for m in mods}
        self._isolated_plan_folders = list(folders)
        self._busy_plan = True
        self.progress.show("Simulando selección…", determinate=False)
        # snapshot: usar=True solo para selección
        snap = []
        for m in self.mods:
            # shallow copy of flags
            from copy import copy

            cm = copy(m)
            cm.usar = m.folder in folders
            snap.append(cm)
        ctx = self._ctx()
        settings = self._settings()
        session_gen = self._session_gen
        game_id = self.registry.active_game_id

        def worker():
            try:
                evaluate(snap, semantic=self._semantic())
                plan = plan_apply(snap, ctx, settings)
                err = None
            except Exception as e:
                plan = None
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if session_gen != self._session_gen or game_id != self.registry.active_game_id:
                    return
                if err is not None:
                    show_scroll_text(self, title="Simulación selección", body=str(err), kind="error")
                    return
                # No sustituir el plan completo del loadout como «aplicable» global
                # salvo que el usuario lo confirme; mostramos preview aislado.
                body = self._format_plan_preview(
                    plan,
                    ctx,
                    title=(
                        f"SIMULACIÓN AISLADA — {len(folders)} mod(s) seleccionados\n"
                        "No se ha modificado el loadout ni el disco.\n"
                        "Apply usa el plan de mods con «usar» activo, no este aislamiento."
                    ),
                )
                show_scroll_text(self, title="Simulación (selección)", body=body)
                self._update_status_bar()

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def choose_pak(self) -> None:
        m = self.selected()
        if not m:
            return
        if not m.paks:
            messagebox.showinfo("Sin paks", "Este mod no tiene archivos .pak.")
            return
        dest_hint = "Paks/~mods (nombre del .pak)"
        if self.session and self.session.adapter_id == "ue4_paks_mods":
            dest_hint = str(self.session.mods_dir) if hasattr(self.session, "mods_dir") else dest_hint
        win = ctk.CTkToplevel(self)
        win.title(f"Variante — {m.name}")
        win.geometry("560x420")
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Elige UNA variante .pak (no se selecciona automáticamente)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(pady=(12, 4))
        ctk.CTkLabel(
            win,
            text=f"Destino final: {dest_hint}\n{m.description[:160] if m.description else '(sin descripción)'}",
            text_color=COLORS["text_muted"],
            wraplength=520,
            justify="left",
        ).pack(padx=16, pady=4)
        var = tk.StringVar(value=m.pak_elegido or "")
        box = ctk.CTkScrollableFrame(win, height=220)
        box.pack(fill="both", expand=True, padx=16)
        for p in m.paks:
            ctk.CTkRadioButton(
                box,
                text=f"{p}  →  destino: {p}",
                variable=var,
                value=p,
            ).pack(anchor="w", pady=3)
        if not m.pak_elegido:
            ctk.CTkLabel(
                win,
                text="Sin elección: el mod permanece bloqueado para instalar.",
                text_color=COLORS["warn"],
            ).pack(pady=4)

        def ok():
            if not var.get():
                messagebox.showinfo("Variante", "Debes elegir una variante.", parent=win)
                return
            m.pak_elegido = var.get()
            m.usar = True
            win.destroy()
            self.view_library.refresh()
            self.analyze_conflicts()

        ctk.CTkButton(win, text="Usar esta variante", command=ok).pack(pady=12)

    def edit_description(self) -> None:
        if not self.session:
            return
        m = self.selected()
        if not m:
            return
        new = simpledialog.askstring(
            "Descripción", "Qué es este mod:", initialvalue=m.description, parent=self
        )
        if new is None:
            return
        m.description = new.strip()
        save_override(
            m.folder, m.description, m.category, path=self.session.desc_override
        )
        self.view_library.refresh()

    def simulate_selected_preview(self) -> None:
        """Vista previa de qué copiaría el mod seleccionado (sin Apply)."""
        if not self.session:
            messagebox.showerror("Sin juego", "Configura un juego activo primero.")
            return
        m = self.selected()
        if not m:
            messagebox.showinfo("Selección", "Selecciona un mod en la biblioteca.")
            return
        from ..core.content_classify import classify_mod

        mc = classify_mod(m, self.session.adapter_id)
        lines = [
            f"=== Vista previa — {m.name} ===",
            f"Adaptador: {self.session.adapter_id}",
            f"Clasificación: {mc.summary_kind()}",
            f"Variante: {m.pak_elegido or ('(pendiente)' if m.multi else '—')}",
            "",
            "Instalables (se copiarían si el mod está activo y sin bloqueos):",
        ]
        for x in mc.installable or ["(ninguno)"]:
            lines.append(f"  → {x}")
        lines.append("")
        lines.append("Documentación excluida:")
        for x in mc.documentation[:30] or ["(ninguna)"]:
            lines.append(f"  · {x}")
        if mc.special:
            lines.append("")
            lines.append("Destino especial (no → ~mods):")
            for x in mc.special:
                lines.append(f"  ! {x}")
        if mc.unknown:
            lines.append("")
            lines.append("Pendiente de clasificación:")
            for x in mc.unknown:
                lines.append(f"  ? {x}")
        if mc.variant_pending:
            lines.append("")
            lines.append("BLOQUEO: elige variante antes de instalar.")
        lines.append("")
        lines.append("Apply NO ejecutado.")
        show_scroll_text(self, title="Vista previa instalación", body="\n".join(lines))

    def show_safe_subset(self) -> None:
        """Propone subconjunto seguro sin mutar el loadout ni Apply."""
        if not self.session:
            messagebox.showerror("Sin juego", "Configura un juego activo primero.")
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Ya hay una operación en curso.")
            return
        self._busy_plan = True
        self.progress.show("Calculando subconjunto seguro…", determinate=False)
        mods_snapshot = list(self.mods)
        settings = self._settings()
        ctx = self._ctx()
        session_gen = self._session_gen
        game_id = self.registry.active_game_id

        def worker():
            try:
                from ..core.safe_loadout import format_safe_subset_report, propose_safe_subset

                # Primera propuesta controlada: cupo pequeño; el informe lista excluidos
                prop = propose_safe_subset(
                    mods_snapshot, settings, ctx, max_mods=15
                )
                body = format_safe_subset_report(prop)
                err = None
            except Exception as e:
                body = ""
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if session_gen != self._session_gen or game_id != self.registry.active_game_id:
                    return
                if err is not None:
                    show_scroll_text(self, title="Subconjunto seguro", body=str(err), kind="error")
                    return
                show_scroll_text(self, title="Subconjunto seguro (simulación)", body=body)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def save_plan(self) -> None:
        if not self.session:
            return
        save_loadout(self.mods, self.session.loadout_json)
        messagebox.showinfo("Guardado", f"Plan guardado en:\n{self.session.loadout_json}")

    def disable_all_mods(self) -> None:
        if not self.session or self.is_busy():
            return
        if not messagebox.askyesno(
            "Desactivar todo",
            "Pone usar=NO en TODOS los mods del gestor.\n"
            "No toca Vortex ni el juego hasta Aplicar.\n\n¿Continuar?",
        ):
            return
        disable_all(self.mods)
        save_loadout(self.mods, self.session.loadout_json)
        self.view_library.refresh()
        self.analyze_conflicts()

    def sync_from_vortex(self) -> None:
        """Consulta Vortex (solo lectura) y opcionalmente importa un backup histórico.

        No trata hourly/daily como estado actual. No Deploy/Purge. No toca Vortex.
        """
        if not self.session or self.is_busy():
            return
        if not self.session.vortex_game_id:
            messagebox.showinfo(
                "Sin Vortex",
                "Este juego no tiene vortex_game_id.\nConfigura staging en Ajustes.",
            )
            return
        from ..core.vortex_sync import (
            VortexReliability,
            format_vortex_status_report,
            probe_vortex_enable_state,
        )

        ctx = self._ctx()
        snap = probe_vortex_enable_state(
            self.session.vortex_game_id,
            mods_dir=ctx.mods,
        )
        report = format_vortex_status_report(snap)

        # Meta/imágenes desde backup OK (no implica enablement actual)
        self.vortex_meta = extract_vortex_meta(
            force=True,
            vortex_game_id=self.session.vortex_game_id,
            meta_cache=self.session.meta_cache,
        )
        self.mods = scan_staging(self.session.stage_dir, deploy_path=ctx.deploy)
        merge_loadout(self.mods, self.session.loadout_json)
        self._enrich_mod_sources()
        apply_descriptions(
            self.mods, self.vortex_meta, overrides_path=self.session.desc_override
        )
        # Restaurar variantes del loadout; NO tocar usar salvo import histórico explícito
        saved = load_loadout(self.session.loadout_json)
        for m in self.mods:
            if m.folder in saved:
                if saved[m.folder].get("pak_elegido"):
                    m.pak_elegido = saved[m.folder]["pak_elegido"]
                if "usar" in saved[m.folder]:
                    m.usar = bool(saved[m.folder]["usar"])

        import_historical = False
        if snap.reliability == VortexReliability.HISTORICAL_BACKUP:
            show_scroll_text(self, title="Estado Vortex", body=report)
            import_historical = messagebox.askyesno(
                "Backup histórico — no es estado actual",
                "Estado Vortex actual no verificado.\n\n"
                f"{snap.ui_historical_label}\n\n"
                "Ese JSON (hourly/daily) NO es el estado vivo de Vortex.\n"
                "¿Importar ese SNAPSHOT HISTÓRICO al plan del gestor (usar SI/NO)?\n\n"
                "No se modificará Vortex ni el juego.\n"
                "Elige NO para solo refrescar meta y mantener el plan actual.",
            )
        else:
            show_scroll_text(self, title="Estado Vortex", body=report)
            messagebox.showinfo(
                "Vortex",
                "Estado Vortex actual no verificado.\n"
                "El plan del gestor no se ha modificado.",
            )

        on = off = 0
        msg = snap.message
        if import_historical:
            on, off, msg = apply_vortex_enablement(
                self.mods,
                self.session.vortex_game_id,
                mods_dir=ctx.mods,
                allow_historical=True,
            )
            save_loadout(self.mods, self.session.loadout_json)
            messagebox.showinfo(
                "Plan actualizado desde backup histórico",
                f"{msg}\n\nGestor → usar SI: {on} · usar NO: {off}",
            )
        else:
            # Mantener plan; solo refrescar vistas
            pass

        self.by_id = {m.folder: m for m in self.mods}
        self.view_library.refresh()
        self.analyze_conflicts()

    # ---------- plan preview / apply ----------
    def _format_plan_preview(self, plan, ctx, *, title: str) -> str:
        resolved = 0
        if plan.analysis:
            resolved = sum(1 for c in plan.analysis.file_conflicts if c.resolved)

        def _list(label: str, items: list[str], limit: int = 40) -> str:
            if not items:
                return f"{label}: (ninguno)\n"
            lines = [f"{label} ({len(items)}):"]
            for rel in items[:limit]:
                src = ""
                meta = plan.desired_meta.get(rel)
                if meta:
                    src = f"  ← {meta.source}"
                lines.append(f"  • {rel}{src}")
            if len(items) > limit:
                lines.append(f"  • … y {len(items) - limit} más")
            return "\n".join(lines) + "\n"

        blocked = [e for e in plan.errors]
        # S09 — métodos e espacio estimado
        decisions = plan.install_decisions or {}
        need_copy = [
            r for r, d in decisions.items() if str(d.get("method")) == "COPY"
        ]
        use_hl = [
            r for r, d in decisions.items() if str(d.get("method")) == "HARDLINK"
        ]
        blocked_hl = [r for r, d in decisions.items() if d.get("blocked")]
        bytes_copy = sum(int(d.get("size") or 0) for r, d in decisions.items() if r in need_copy)
        bytes_hl = sum(int(d.get("size") or 0) for r, d in decisions.items() if r in use_hl)
        method_lines = [
            f"Política instalación: {plan.install_mode_policy}",
            f"HARDLINK previsto: {len(use_hl)} archivos "
            f"(lógico {_fmt_bytes_ui(bytes_hl)}; espacio adicional ~0 si elegible)",
            f"COPY previsto: {len(need_copy)} archivos "
            f"(espacio adicional estimado {_fmt_bytes_ui(bytes_copy)})",
        ]
        if blocked_hl:
            method_lines.append(f"HARDLINK bloqueados (requieren COPY o abortan): {len(blocked_hl)}")
        for r in (plan.to_add + plan.to_update)[:40]:
            d = decisions.get(r) or {}
            method_lines.append(
                f"  [{d.get('method', '?')}] {r}  "
                f"({_fmt_bytes_ui(int(d.get('size') or 0))}) — {d.get('reason', '')}"
            )

        msg = (
            f"{title}\n"
            f"Juego: {self.session.record.name}\n"
            f"Destino: {ctx.mods}\n"
            f"Activos en plan: {sum(1 for m in self.mods if m.usar)}\n"
            f"Conflictos bloqueantes: {plan.conflicts}\n"
            f"Sin resolver: {plan.file_unresolved}  ·  Resueltos: {resolved}\n\n"
            + "\n".join(method_lines)
            + "\n\n"
            + _list("AÑADIR", plan.to_add)
            + _list("ACTUALIZAR (sustitución atómica; no escribe in-place)", plan.to_update)
            + _list("RETIRAR (solo gestionados; staging intacto)", plan.to_remove)
        )
        if plan.drifted:
            msg += _list("DERIVA (bloquea sobrescritura)", plan.drifted, 20)
        if blocked:
            msg += "\nBLOQUEADOS / avisos:\n" + "\n".join(f"• {e}" for e in blocked[:30])
        if vortex_deploy_present(ctx):
            msg += (
                "\n\nSEGURIDAD: vortex.deployment.json presente. "
                "Haz Purge en Vortex; la instalación está bloqueada."
            )
        msg += (
            "\n\nNota S09: hardlinks comparten datos con staging; "
            "integridad Vortex > ahorro. Backups siempre en COPY."
        )
        return msg

    def simulate(self) -> None:
        if not self.session:
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Ya hay una operación en curso.")
            return
        self._busy_plan = True
        self.progress.show("Simulando plan…", determinate=False)
        mods_snapshot = list(self.mods)
        ctx = self._ctx()
        settings = self._settings()
        session_gen = self._session_gen
        game_id = self.registry.active_game_id

        def worker():
            try:
                evaluate(mods_snapshot, semantic=self._semantic())
                plan = plan_apply(mods_snapshot, ctx, settings)
                err = None
            except Exception as e:
                plan = None
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if session_gen != self._session_gen or game_id != self.registry.active_game_id:
                    return
                if err is not None:
                    show_scroll_text(self, title="Simulación", body=str(err), kind="error")
                    return
                self._last_plan = plan
                self._merge_file_conflict_labels()
                self.view_library.refresh()
                self.view_summary.refresh()
                show_scroll_text(
                    self,
                    title="Simulación (sin cambios en disco)",
                    body=self._format_plan_preview(
                        plan, ctx, title="VISTA PREVIA — no se ha escrito nada"
                    ),
                )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def apply_to_game(self) -> None:
        if not self.session:
            messagebox.showerror("Sin juego", "Configura un juego activo primero.")
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Ya hay una operación en curso.")
            return
        if not self.plan_is_applyable():
            messagebox.showinfo(
                "Aplicar bloqueado",
                getattr(self, "_apply_tip", None)
                or "El plan vigente tiene bloqueos o el análisis no está listo.\n"
                "Usa «Conflictos» o espera al análisis.",
            )
            return
        ctx = self._ctx()
        conflict = destination_conflict_message(self.registry, self.session.record)
        if conflict:
            messagebox.showerror("Destino compartido", conflict)
            return
        path_errs = validate_game_paths(self.session.record)
        if path_errs:
            show_scroll_text(self, title="Rutas inválidas", body="\n".join(path_errs), kind="error")
            return
        if vortex_deploy_present(ctx):
            messagebox.showerror(
                "Instalación bloqueada",
                "Hay un despliegue activo de Vortex (vortex.deployment.json).\n"
                "Haz Purge en Vortex antes de aplicar.",
            )
            return

        self._busy_plan = True
        self.progress.show("Preparando vista previa…", determinate=False)
        mods_snapshot = list(self.mods)
        settings = self._settings()
        session_gen = self._session_gen
        game_id = self.registry.active_game_id

        def worker():
            try:
                evaluate(mods_snapshot, semantic=self._semantic())
                plan = plan_apply(mods_snapshot, ctx, settings)
                err = None
            except Exception as e:
                plan = None
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if session_gen != self._session_gen or game_id != self.registry.active_game_id:
                    return
                if err is not None:
                    show_scroll_text(self, title="Error", body=str(err), kind="error")
                    return
                self._last_plan = plan
                self._merge_file_conflict_labels()
                self.view_library.refresh()
                if plan.conflicts or plan.errors or plan.file_unresolved:
                    show_scroll_text(
                        self,
                        title="No se puede aplicar",
                        body=self._format_plan_preview(
                            plan, ctx, title="PLAN BLOQUEADO — no se ha escrito nada"
                        ),
                        kind="error",
                    )
                    return
                summary = self._format_plan_preview(
                    plan,
                    ctx,
                    title="CONFIRMACIÓN — se escribirá en el destino del juego",
                )
                summary += (
                    "\n\nSolo se eliminan archivos GESTIONADOS.\n"
                    "Se creará backup + snapshot de manifiesto."
                )
                if not ask_scroll_confirm(
                    self,
                    title="Confirmar aplicación",
                    body=summary,
                    confirm_label="Aplicar ahora",
                ):
                    return
                self._execute_apply(plan, ctx)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _execute_apply(self, plan, ctx) -> None:
        self._busy_write = True
        self.progress.show("Aplicando…", determinate=False)
        session_gen = self._session_gen
        game_id = self.registry.active_game_id

        def on_progress(phase: str, current: int, total: int) -> None:
            self.after(0, lambda: self.progress.update(phase, current, total))

        def worker():
            result = {"ok": False, "error": None, "apply_error": None}
            try:
                execute(plan, ctx, mods=self.mods, progress=on_progress)
                save_loadout(self.mods, self.session.loadout_json)
                result["ok"] = True
            except PermissionError as e:
                result["error"] = ("permission", e)
            except ApplyError as e:
                result["apply_error"] = e
            except Exception as e:
                result["error"] = ("other", e)

            def done():
                self._busy_write = False
                self.progress.hide()
                if session_gen != self._session_gen or game_id != self.registry.active_game_id:
                    return
                if result["ok"]:
                    messagebox.showinfo(
                        "Aplicado",
                        "Loadout aplicado.\nBackup + manifiesto actualizados.",
                    )
                    self.refresh()
                    return
                if result["apply_error"] is not None:
                    e = result["apply_error"]
                    extra = ""
                    if e.rollback_ok is True:
                        extra = "\n\nSe restauró la copia de seguridad."
                    elif e.rollback_ok is False:
                        extra = "\n\nATENCIÓN: rollback incompleto. Revisa backups."
                    show_scroll_text(
                        self, title="Error de instalación", body=str(e) + extra, kind="error"
                    )
                    self.refresh()
                    return
                kind, e = result["error"]
                if kind == "permission":
                    messagebox.showerror(
                        "Permiso denegado",
                        "No se pudo escribir en la carpeta del juego.",
                    )
                else:
                    show_scroll_text(self, title="Error", body=str(e), kind="error")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def show_storage_report(self) -> None:
        if not self.session:
            messagebox.showinfo("Sin juego", "No hay juego activo.")
            return
        from ..core.storage_report import (
            build_storage_report,
            plan_sources_from_desired,
        )
        from ..core.install_modes import volume_compatibility_report

        ctx = self._ctx()
        settings = self._settings()
        plan = self._last_plan
        sources = []
        if plan and plan.desired_meta:
            sources = plan_sources_from_desired(plan.desired_meta, ctx.mods)
        dl = Path(self.session.record.downloads_dir) if self.session.record.downloads_dir else None
        rep = build_storage_report(
            mods_dir=ctx.mods,
            stage_dir=self.session.stage_dir,
            downloads_dir=dl if dl and dl.is_dir() else None,
            plan_sources=sources,
            install_mode=settings.install_mode,
        )
        vol = volume_compatibility_report(self.session.stage_dir, ctx.mods)
        show_scroll_text(
            self,
            title="Almacenamiento y volumen",
            body=rep.format() + "\n\n" + vol,
        )

    def set_install_mode(self, mode: str) -> None:
        if not self.session or self.is_busy():
            return
        mode_u = (mode or "COPY").strip().upper()
        if mode_u not in ("COPY", "HARDLINK", "AUTO"):
            return
        rec = self.session.record
        rec.install_mode = mode_u
        errs = update_game(self.registry, rec)
        if errs:
            messagebox.showerror("Modo instalación", "\n".join(errs))
            return
        save_registry(self.registry)
        self._reload_session()
        self.view_settings.refresh()
        self.view_summary.refresh()
        messagebox.showinfo(
            "Modo instalación",
            f"Política: {mode_u}\n"
            "HARDLINK solo si es elegible; AUTO hace fallback a COPY.\n"
            "Integridad del staging Vortex tiene prioridad.",
        )

    def review_staging_changes(self) -> None:
        """Detecta cambios locales en staging; no modifica staging ni el juego."""
        if not self.session or self.is_busy():
            return
        from ..core.staging_watch import (
            detect_staging_changes,
            format_staging_watch_report,
            record_staging_fingerprint,
        )

        fp = self.session.staging_fingerprint_json
        result = detect_staging_changes(self.mods, fp)
        body = format_staging_watch_report(result)
        show_scroll_text(self, title="Cambios en staging", body=body)
        if result.changed_mods:
            if messagebox.askyesno(
                "Registrar huella",
                "¿Marcar el estado actual del staging como revisado "
                "(actualizar huella SHA-256)?\n\n"
                "No modifica archivos de staging ni del juego.",
            ):
                record_staging_fingerprint(self.mods, fp)
                messagebox.showinfo("Huella", "Huella de staging actualizada.")
        elif not fp.exists():
            if messagebox.askyesno(
                "Crear huella",
                "No hay huella previa. ¿Crear la huella inicial del staging?",
            ):
                record_staging_fingerprint(self.mods, fp)
                messagebox.showinfo("Huella", "Huella inicial creada.")
        self.view_library.refresh()

    # ---------- S11 archive (simulación; no borra staging ni mueve Downloads) ----------
    def archive_analyze(self) -> None:
        if not self.session:
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Operación en curso.")
            return
        self._busy_plan = True
        self.progress.show("Analizando biblioteca de paquetes…", determinate=False)
        mods = list(self.mods)
        session = self.session
        gen = self._session_gen

        def worker():
            err = None
            text = ""
            cat = None
            loaded_job = None
            try:
                from ..core.archive_catalog import build_catalog, save_catalog
                from ..core.archive_match import apply_match_grades, enrich_from_vortex_meta
                from ..core.library_archive import attach_own_archives_from_dir
                from ..core.real_archive_job import job_path, load_job

                dl = Path(session.record.downloads_dir) if session.record.downloads_dir else None
                meta_path = session.meta_cache
                if meta_path.is_file():
                    try:
                        import json as _json

                        enrich_from_vortex_meta(
                            mods, _json.loads(meta_path.read_text(encoding="utf-8"))
                        )
                    except Exception:
                        pass
                cat = build_catalog(
                    game_id=session.record.id,
                    mods=mods,
                    downloads_dir=dl,
                    stage_dir=session.stage_dir,
                    archive_root_config=getattr(session.record, "archive_dir", "") or "",
                    hash_packages=False,
                )
                attach_own_archives_from_dir(
                    cat, session.data_dir / "own_archive_demo"
                )
                ad = getattr(session.record, "archive_dir", "") or ""
                if ad:
                    attach_own_archives_from_dir(cat, Path(ad))
                loaded_job = load_job(job_path(session.data_dir))
                grades = apply_match_grades(cat, verify_content=False)
                out = session.data_dir / "archive_catalog.json"
                save_catalog(cat, out)
                c = cat.to_dict()["counts"]
                text = (
                    f"Catálogo guardado en {out}\n\n"
                    f"Paquetes en downloads: {c['packages']}\n"
                    f"Mods staging: {c['mods']}\n"
                    f"ORIGINAL_VORTEX vinculados: "
                    f"{sum(1 for m in cat.mods if m.archive_path)}\n"
                    f"ARCHIVO_PROPIO locales: "
                    f"{sum(1 for m in cat.mods if m.own_archive_path)}\n"
                    f"Match PROBABLE: {grades.get('PROBABLE', 0)} "
                    f"(falta verificar contenido → VERIFICADA)\n"
                    f"Ambiguos: {c['ambiguous']}\n"
                    f"Solo staging: {c['staging_only']}\n"
                    f"Especiales: {c['special']}\n"
                    f"Solo descarga: {c['download_only']}\n\n"
                    "PROBABLE no es recuperable vía original hasta VERIFICADA + sandbox.\n"
                    "No se ha movido ni borrado nada."
                )
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                if err:
                    show_scroll_text(self, title="Archivo", body=str(err), kind="error")
                    return
                self._archive_catalog = cat
                self._archive_job = loaded_job
                self._archive_view_text = text
                self.view_storage.refresh()
                show_scroll_text(self, title="Análisis de biblioteca", body=text)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def archive_verify(self) -> None:
        if not self.session:
            return
        if self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Primero «Analizar biblioteca».")
            return
        if self.is_busy():
            return
        self._busy_plan = True
        self.progress.show("Verificando paquetes (listado)…", determinate=False)
        cat = self._archive_catalog
        gen = self._session_gen

        def worker():
            err = None
            text = ""
            try:
                from ..core.archive_catalog import save_catalog
                from ..core.archive_match import apply_match_grades
                from ..core.archive_verify import verify_catalog

                reps = verify_catalog(cat, deep_extract=False)
                grades = apply_match_grades(cat, verify_content=False)
                # Reaplicar grades tras verify: entries ya tienen match VERIFICADA
                ver = sum(1 for m in cat.mods if m.match_grade == "VERIFICADA")
                save_catalog(cat, self.session.data_dir / "archive_catalog.json")
                ok = sum(1 for r in reps if r.status == "ARCHIVO VERIFICADO")
                lines = [
                    f"Listado OK (ARCHIVO VERIFICADO / match VERIFICADA): {ok}",
                    f"Grados tras pase: VERIFICADA≈{ver} "
                    f"PROBABLE={grades.get('PROBABLE', 0)} "
                    f"AMBIGUA={grades.get('AMBIGUA', 0)}",
                    "Recuperable=True solo tras sandbox (botón restauración o demo propio).",
                    "",
                    "Muestra pendientes:",
                ]
                for r in [x for x in reps if x.recoverable is not True][:30]:
                    lines.append(f"  — {r.folder}: {r.note}")
                text = "\n".join(lines)
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                if err:
                    show_scroll_text(self, title="Verificar", body=str(err), kind="error")
                    return
                self._archive_view_text = text
                self.view_storage.refresh()
                show_scroll_text(self, title="Verificación de paquetes", body=text)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def archive_simulate(self) -> None:
        if not self.session or self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Analiza y verifica antes de simular.")
            return
        from ..core.archive_plan import format_archive_simulation, simulate_archive_plan

        mods_dir = (
            self.session.mods_dir
            if self.session.record.mods_dir.strip()
            else None
        )
        sim = simulate_archive_plan(
            self._archive_catalog,
            self.mods,
            mods_dir=mods_dir,
            pending_ops=self.is_busy(),
        )
        text = format_archive_simulation(sim)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Simulación de archivado", body=text)

    def archive_test_restore(self) -> None:
        if not self.session or self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Primero analiza la biblioteca.")
            return
        if self.is_busy():
            return
        # Probar solo un subconjunto con paquete (sandbox)
        candidates = [
            m
            for m in self._archive_catalog.mods
            if m.archive_path and m.status != "CORRESPONDENCIA AMBIGUA"
        ][:5]
        if not candidates:
            messagebox.showinfo("Archivo", "No hay candidatos con paquete vinculado.")
            return
        self._busy_plan = True
        self.progress.show("Restauración sandbox (muestra)…", determinate=False)
        gen = self._session_gen
        parent = self.session.data_dir / "sandbox_extract"
        parent.mkdir(parents=True, exist_ok=True)

        def worker():
            err = None
            lines = [
                "Prueba de restauración en SANDBOX (máx. 5 mods).",
                "No toca staging ni Downloads.",
                "",
            ]
            try:
                from ..core.archive_verify import verify_mod_package

                for entry in candidates:
                    rep = verify_mod_package(
                        entry, deep_extract=True, sandbox_parent=parent
                    )
                    lines.append(
                        f"{'OK' if rep.recoverable else 'FAIL'} {entry.name}: {rep.note}"
                    )
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                body = str(err) if err else "\n".join(lines)
                self._archive_view_text = body
                self.view_storage.refresh()
                show_scroll_text(
                    self,
                    title="Restauración sandbox",
                    body=body,
                    kind="error" if err else "info",
                )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def archive_config_dir(self) -> None:
        if not self.session or self.is_busy():
            return
        initial = getattr(self.session.record, "archive_dir", "") or ""
        path = filedialog.askdirectory(initialdir=initial or str(ROOT), mustexist=False)
        if not path:
            return
        self.session.record.archive_dir = path
        update_game(self.registry, self.session.record)
        save_registry(self.registry)
        from ..core.own_archive import is_archive_root_available

        ok, note = is_archive_root_available(path)
        messagebox.showinfo(
            "Carpeta de archivo",
            f"Configurada:\n{path}\n\n"
            f"Estado: {'disponible' if ok else 'NO DISPONIBLE'} — {note}\n\n"
            "No se mueven Downloads automáticamente.\n"
            "Sacar paquetes de Vortex Downloads puede romper actualizaciones.\n"
            "Disco desconectado ≠ archivo perdido en el catálogo.",
        )
        self.view_storage.refresh()

    def archive_cancel_job(self) -> None:
        self._archive_cancel = True
        self._archive_pause = False
        messagebox.showinfo(
            "Cancelar",
            "Se pedirá cancelación en el próximo punto seguro.\n"
            "No se publicarán ZIP incompletos.",
        )

    def archive_pause_job(self) -> None:
        self._archive_pause = not self._archive_pause
        messagebox.showinfo(
            "Pausa",
            "Pausa ACTIVADA — el lote esperará en el próximo punto seguro."
            if self._archive_pause
            else "Pausa DESACTIVADA — el lote continúa.",
        )

    def archive_liberate_unavailable(self) -> None:
        messagebox.showwarning(
            "Liberar staging",
            "NO DISPONIBLE (S16).\n\n"
            "Política: LIBERABLE | BLOQUEADO | PENDIENTE_VORTEX.\n"
            "Un ZIP correcto no autoriza el borrado.\n"
            "Si Vortex aún registra el mod → use Uninstall en Vortex.\n"
            "El gestor no modifica state.v2 ni borra staging real.",
        )

    def _work_root(self) -> Path:
        assert self.session is not None
        from ..core.work_library import resolve_work_root

        return resolve_work_root(
            self.session.data_dir,
            configured=getattr(self.session.record, "work_library_dir", "") or "",
            stage_dir=self.session.stage_dir,
        )

    def work_config_dir(self) -> None:
        if not self.session or self.is_busy():
            return
        initial = getattr(self.session.record, "work_library_dir", "") or str(
            self.session.data_dir / "work_library"
        )
        path = filedialog.askdirectory(initialdir=initial, mustexist=False)
        if not path:
            return
        # rechazar staging
        chosen = Path(path)
        if self.session.stage_dir and self.session.stage_dir.exists():
            try:
                chosen.resolve().relative_to(self.session.stage_dir.resolve())
                messagebox.showerror(
                    "Carpeta inválida",
                    "La biblioteca de trabajo no puede estar dentro del staging Vortex.",
                )
                return
            except ValueError:
                pass
        root = chosen
        self.session.record.work_library_dir = str(root)
        update_game(self.registry, self.session.record)
        save_registry(self.registry)
        messagebox.showinfo(
            "Biblioteca de trabajo",
            f"Configurada:\n{root}\n\nNo es staging Vortex. ZIP propio = fuente primaria.",
        )
        self.view_storage.refresh()

    def work_show_status(self) -> None:
        if not self.session:
            return
        from ..core.work_library import (
            format_work_library_status,
            load_index,
            resolve_work_root,
        )

        root = self._work_root()
        idx = load_index(root, game_id=self.session.record.id)
        self._work_index = idx
        text = format_work_library_status(idx)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Biblioteca de trabajo", body=text)

    def work_restore_from_archive(self) -> None:
        if not self.session:
            return
        if self.is_busy():
            return
        from ..core.real_archive_job import STATUS_OK, job_path, load_job

        job = self._archive_job or load_job(job_path(self.session.data_dir))
        archives: list[Path] = []
        if job:
            for it in job.items.values():
                if it.status == STATUS_OK and it.path and Path(it.path).is_file():
                    archives.append(Path(it.path))
        if not archives and self._archive_catalog:
            for m in self._archive_catalog.mods:
                if m.own_archive_path and Path(m.own_archive_path).is_file():
                    archives.append(Path(m.own_archive_path))
        if not archives:
            messagebox.showinfo(
                "Restaurar",
                "No hay ARCHIVO_PROPIO verificados. Archiva primero (S13).",
            )
            return
        scope = messagebox.askyesnocancel(
            "Restaurar a biblioteca de trabajo",
            f"Hay {len(archives)} ZIP propios.\n\n"
            "SÍ = restaurar todos\n"
            "NO = solo los 3 más pequeños (demo)\n"
            "CANCELAR = abortar\n\n"
            "No se escribe en staging Vortex.",
        )
        if scope is None:
            return
        if scope is False:
            # ordenar por tamaño
            archives = sorted(archives, key=lambda p: p.stat().st_size)[:3]
        if not messagebox.askyesno(
            "Confirmar restauración",
            f"Restaurar {len(archives)} mod(s) a:\n{self._work_root()}\n\n"
            "¿Continuar?",
        ):
            return
        self._archive_cancel = False
        self._busy_plan = True
        self.progress.show("Restaurando a biblioteca de trabajo…", determinate=True)
        session = self.session
        gen = self._session_gen
        root = self._work_root()

        def worker():
            err = None
            text = ""
            idx = None
            try:
                from ..core.work_library import (
                    format_work_library_status,
                    restore_many_to_work,
                )

                def prog(phase, cur, tot):
                    self.after(0, lambda: self.progress.update(phase, cur, tot))

                results, idx = restore_many_to_work(
                    game_id=session.record.id,
                    archives=archives,
                    work_root=root,
                    progress=prog,
                    cancel=lambda: self._archive_cancel,
                )
                ok = sum(1 for r in results if r.ok)
                fail = sum(1 for r in results if not r.ok)
                lines = [
                    f"Restaurados OK={ok} FAIL={fail} SKIP="
                    f"{sum(1 for r in results if r.skipped)}",
                    f"Destino: {root}",
                    "No se modificó staging Vortex ni Downloads.",
                    "",
                ]
                for r in results[:40]:
                    lines.append(
                        f"{'OK' if r.ok else 'FAIL'} {r.mod_id}: "
                        f"{r.work_path or '; '.join(r.errors[:2])}"
                    )
                lines.append("\n" + format_work_library_status(idx))
                text = "\n".join(lines)
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                if idx is not None:
                    self._work_index = idx
                body = str(err) if err else text
                self._archive_view_text = body
                self.view_storage.refresh()
                show_scroll_text(
                    self,
                    title="Restaurar biblioteca trabajo",
                    body=body,
                    kind="error" if err else "info",
                )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def work_prepare_install(self) -> None:
        if not self.session:
            return
        from ..core.work_install import prepare_install_from_work
        from ..core.work_library import load_index

        root = self._work_root()
        idx = load_index(root, game_id=self.session.record.id)
        if not idx.mods:
            messagebox.showinfo(
                "Preparar instalación",
                "Biblioteca de trabajo vacía. Restaura mods archivados primero.",
            )
            return
        ctx = self._ctx()
        settings = self._settings()
        settings.stage_root = root
        # solo mods marcados usar si hay; si no, todos los extraídos
        marked = [m.folder for m in self.mods if m.usar]
        mod_ids = None
        if marked:
            mod_ids = [
                mid
                for mid, rec in idx.mods.items()
                if rec.folder in marked or rec.in_use
            ] or None
        prep = prepare_install_from_work(
            idx, mod_ids=mod_ids, ctx=ctx, settings=settings, mark_use=True
        )
        self._work_index = idx
        self._archive_view_text = prep.preview
        self.view_storage.refresh()
        show_scroll_text(
            self,
            title="Preparar instalación (simulación)",
            body=prep.preview,
            kind="info" if prep.ok else "error",
        )

    def set_default_mod_source(self, source: str) -> None:
        if not self.session:
            return
        src = (source or "STAGING_VORTEX").upper()
        if src not in ("STAGING_VORTEX", "WORK_LIBRARY", "AUTO"):
            src = "STAGING_VORTEX"
        self.session.record.default_mod_source = src
        update_game(self.registry, self.session.record)
        save_registry(self.registry)
        if hasattr(self.view_settings, "default_source_label"):
            self.view_settings.default_source_label.configure(text=f"Fuente: {src}")
        messagebox.showinfo(
            "Fuente predeterminada",
            f"Fuente: {src}\n\n"
            "WORK_LIBRARY solo afecta a mods ya extraídos en biblioteca propia.\n"
            "No se mezclan rutas con staging Vortex silenciosamente.",
        )
        self.refresh()

    def library_use_work_source(self) -> None:
        m = self.view_library.selected()
        if not m or not self.session:
            return
        from ..core.mod_source import switch_mod_to_work_source
        from ..core.work_library import load_index

        idx = load_index(self._work_root(), game_id=self.session.record.id)
        errs = switch_mod_to_work_source(m, idx)
        if errs:
            messagebox.showerror("Fuente WORK", "\n".join(errs))
            return
        messagebox.showinfo(
            "Fuente WORK",
            f"{m.name} usará WORK_LIBRARY:\n{m.stage_path}\n\n"
            "Plan SI ≠ instalado. Simula antes de Aplicar.",
        )
        self.view_library.redraw()
        self.view_library.on_select()

    def library_use_vortex_source(self) -> None:
        m = self.view_library.selected()
        if not m or not self.session or not self.session.stage_dir:
            return
        vortex_path = self.session.stage_dir / m.folder
        if not vortex_path.is_dir():
            messagebox.showerror(
                "Fuente Vortex",
                "No hay carpeta en staging Vortex para este mod.",
            )
            return
        m.source_kind = "STAGING_VORTEX"
        m.stage_path = str(vortex_path)
        messagebox.showinfo(
            "Fuente Vortex",
            f"{m.name} usará STAGING_VORTEX:\n{m.stage_path}",
        )
        self.view_library.redraw()
        self.view_library.on_select()

    def library_prepare_from_archive(self) -> None:
        """Restaura ZIP propio del mod seleccionado a WORK y cambia fuente."""
        m = self.view_library.selected()
        if not m or not self.session:
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Operación en curso.")
            return
        from ..core.mod_source import switch_mod_to_work_source
        from ..core.real_archive_job import STATUS_OK, job_path, load_job
        from ..core.work_library import load_index, restore_archive_to_work

        arch = Path(m.archive_path) if m.archive_path else None
        if not arch or not arch.is_file():
            job = self._archive_job or load_job(job_path(self.session.data_dir))
            if job:
                for it in job.items.values():
                    if it.folder == m.folder and it.status == STATUS_OK and it.path:
                        arch = Path(it.path)
                        break
        if not arch or not arch.is_file():
            messagebox.showinfo(
                "Preparar desde archivo",
                "No hay ARCHIVO_PROPIO verificado para este mod. Archívalo primero (S13).",
            )
            return
        if not messagebox.askyesno(
            "Preparar desde archivo",
            f"Restaurar a biblioteca de trabajo y usar como fuente:\n{arch.name}\n\n"
            "No se escribe en staging Vortex ni se aplica al juego.",
        ):
            return
        root = self._work_root()
        idx = load_index(root, game_id=self.session.record.id)
        rr = restore_archive_to_work(
            game_id=self.session.record.id,
            archive_path=arch,
            work_root=root,
            idx=idx,
        )
        if not rr.ok:
            messagebox.showerror("Preparar", "\n".join(rr.errors[:8]))
            return
        idx = load_index(root, game_id=self.session.record.id)
        switch_mod_to_work_source(m, idx)
        m.usar = True
        m.archived = True
        self._work_index = idx
        self.by_id[m.folder] = m
        messagebox.showinfo(
            "Preparar desde archivo",
            f"OK — fuente WORK_LIBRARY.\n{m.stage_path}\n\n"
            "Usa Simular / Aplicar cuando el destino esté autorizado.",
        )
        self.view_library.redraw()
        self.view_library.on_select()
        self.analyze_conflicts()

    def work_cleanup_library(self) -> None:
        if not self.session:
            return
        if not messagebox.askyesno(
            "Limpiar biblioteca de trabajo",
            "Se eliminarán EXTRAÍDOS no usados/no fijados de la biblioteca propia.\n"
            "No se borran ZIP ni staging Vortex.\n"
            "Orígenes con hardlink a destino se retienen.\n¿Continuar?",
        ):
            return
        from ..core.work_library import (
            cleanup_work_library,
            format_work_library_status,
            load_index,
        )

        root = self._work_root()
        idx = load_index(root, game_id=self.session.record.id)
        mods_dir = (
            self.session.mods_dir
            if self.session.record.mods_dir.strip()
            else None
        )
        removed, notes = cleanup_work_library(
            idx, only_unused=True, mods_dir=mods_dir
        )
        text = (
            f"Limpiados: {removed}\n"
            + "\n".join(notes[:40])
            + "\n\n"
            + format_work_library_status(idx)
        )
        self._work_index = idx
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Limpieza biblioteca trabajo", body=text)

    def archive_simulate_liberation(self) -> None:
        if not self.session or self._archive_catalog is None:
            messagebox.showinfo("Liberación", "Analiza la biblioteca primero.")
            return
        from ..core.liberation_plan import (
            format_liberation_simulation,
            simulate_staging_liberation,
        )
        from ..core.real_archive_job import job_path, load_job
        from ..core.work_library import load_index

        job = self._archive_job or load_job(job_path(self.session.data_dir))
        widx = load_index(self._work_root(), game_id=self.session.record.id)
        mods_dir = (
            self.session.mods_dir
            if self.session.record.mods_dir.strip()
            else None
        )
        indep = getattr(self, "_independence_by_folder", None) or {}
        pending = False
        if job is not None:
            pending = any(
                getattr(it, "status", "") in ("PENDIENTE", "COMPRIMIENDO", "VERIFICANDO")
                for it in job.items.values()
            )
        game_installed = bool(
            self.session.record.mods_dir.strip()
            and Path(self.session.record.mods_dir).exists()
        )
        sim = simulate_staging_liberation(
            self._archive_catalog,
            self.mods,
            job=job,
            work_idx=widx,
            mods_dir=mods_dir,
            vortex_game_id=getattr(self.session.record, "vortex_game_id", None)
            or None,
            game_installed=game_installed,
            independence_by_folder=indep,
            pending_ops=pending,
        )
        text = format_liberation_simulation(sim)
        out = self.session.data_dir / "liberation_simulation.json"
        out.write_text(
            __import__("json").dumps(sim.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._liberation_counts = {
            "LIBERABLE": sim.liberable_count,
            "PENDIENTE_VORTEX": sim.pendiente_vortex_count,
            "BLOQUEADO": sim.blocked_count,
        }
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Simulación liberación staging S16", body=text)

    def archive_vortex_research(self) -> None:
        from ..core.vortex_liberation import format_vortex_research_summary
        from ..core.vortex_sync import format_vortex_status_report, probe_vortex_enable_state

        research = format_vortex_research_summary()
        live = ""
        if self.session:
            snap = probe_vortex_enable_state(
                getattr(self.session.record, "vortex_game_id", None) or None,
                mods_dir=(
                    self.session.mods_dir
                    if self.session.record.mods_dir.strip()
                    else None
                ),
            )
            live = "\n\n" + format_vortex_status_report(snap)
        text = research + live
        self._archive_view_text = text
        if hasattr(self, "view_storage"):
            self.view_storage.refresh()
        show_scroll_text(self, title="Investigación Vortex (solo lectura)", body=text)

    def archive_check_independence(self) -> None:
        if not self.session or self._archive_catalog is None:
            messagebox.showinfo("Independencia", "Analiza la biblioteca primero.")
            return
        from ..core.apply import ApplyContext
        from ..core.conflict_engine import ConflictSettings
        from ..core.liberation_independence import verify_independence_from_archive

        work = self._work_root()
        data = self.session.data_dir
        sandbox_mods = data / "_s16_indep_sandbox_mods"
        sandbox_data = data / "_s16_indep_sandbox_data"
        sandbox_mods.mkdir(parents=True, exist_ok=True)
        sandbox_data.mkdir(parents=True, exist_ok=True)
        ctx = ApplyContext(
            mods=sandbox_mods,
            deploy=sandbox_mods / "vortex.deployment.json",
            loadout_marker=sandbox_mods / "_manual_loadout.json",
            manifest=sandbox_data / "managed_manifest.json",
            backups=sandbox_data / "backups",
            stage=work,
            data_dir=sandbox_data,
        )
        adapter = getattr(self.session, "adapter_id", None) or "generic"
        settings = ConflictSettings(
            adapter_id=adapter,
            game_id=self.session.record.id,
            work_root=work,
            destination_verified=True,
            install_mode="COPY",
        )
        stage_root = self.session.stage_dir
        indep_map: dict[str, bool] = {}
        lines = ["=== Comprobación independencia (sandbox) ===", ""]
        checked = 0
        for entry in self._archive_catalog.mods:
            path = entry.own_archive_path
            if not path:
                continue
            checked += 1
            r = verify_independence_from_archive(
                game_id=self.session.record.id,
                archive_path=Path(path),
                work_root=work,
                ctx=ctx,
                settings=settings,
                stage_root=stage_root if stage_root.exists() else None,
                pak_elegido=entry.pak_elegido or "",
            )
            indep_map[entry.folder] = r.ok
            st = "OK" if r.ok else "FALLO"
            detail = "; ".join(r.errors[:2]) if r.errors else (
                r.notes[0] if r.notes else ""
            )
            lines.append(f"[{st}] {entry.name} — {detail}")
            if checked >= 25:
                lines.append("… (máx. 25 en esta pasada)")
                break
        if checked == 0:
            lines.append("No hay ARCHIVO_PROPIO en el catálogo.")
        self._independence_by_folder = indep_map
        text = "\n".join(lines)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Independencia del gestor", body=text)

    def archive_physical_space(self) -> None:
        if not self.session:
            return
        from ..core.liberation_plan import estimate_physical_bytes
        from ..core.work_library import estimate_work_bytes, load_index

        lines = ["=== Espacio físico estimado ===", ""]
        total_log = 0
        total_phys = 0
        known = True
        for m in self.mods:
            phys, logical, shared = estimate_physical_bytes(Path(m.stage_path))
            total_log += logical
            if phys is None:
                known = False
            else:
                total_phys += phys
        widx = load_index(self._work_root(), game_id=self.session.record.id)
        work_b = estimate_work_bytes(widx)
        lines.append(f"Staging lógico (mods en memoria)≈ {total_log} B")
        lines.append(
            f"Staging físico est. (nlink==1)≈ {total_phys if known else 'n/d'} B"
        )
        lines.append(f"Biblioteca trabajo (extraídos)≈ {work_b} B")
        lines.append("")
        lines.append(
            "El tamaño lógico no es espacio recuperable garantizado "
            "(clusters, hardlinks, Vortex)."
        )
        lines.append("Liberación real: NO DISPONIBLE.")
        text = "\n".join(lines)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Espacio físico estimado", body=text)

    def archive_release_report(self) -> None:
        if not self.session or self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Analiza la biblioteca primero.")
            return
        from ..core.staging_release import (
            build_staging_release_report,
            format_staging_release_report,
        )

        mods_dir = (
            self.session.mods_dir
            if self.session.record.mods_dir.strip()
            else None
        )
        rep = build_staging_release_report(
            self._archive_catalog,
            self.mods,
            job=self._archive_job,
            mods_dir=mods_dir,
        )
        text = format_staging_release_report(rep)
        out = self.session.data_dir / "staging_release_report.json"
        out.write_text(
            __import__("json").dumps(rep.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Preparación liberación staging", body=text)

    def archive_relink_library(self) -> None:
        if not self.session:
            return
        from ..core.real_archive_job import (
            format_job_report,
            job_path,
            load_job,
            relink_archive_library,
            save_job,
        )

        job = self._archive_job or load_job(job_path(self.session.data_dir))
        if job is None:
            messagebox.showinfo("Revincular", "No hay trabajo de archivado previo.")
            return
        path = filedialog.askdirectory(
            initialdir=job.archive_dir or str(ROOT), mustexist=True
        )
        if not path:
            return
        notes = relink_archive_library(job, Path(path))
        save_job(job, job_path(self.session.data_dir))
        self.session.record.archive_dir = path
        update_game(self.registry, self.session.record)
        save_registry(self.registry)
        self._archive_job = job
        text = "Revinculación:\n" + "\n".join(notes) + "\n\n" + format_job_report(job)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Revincular biblioteca", body=text)

    def archive_verify_published(self) -> None:
        if not self.session or self.is_busy():
            return
        from ..core.real_archive_job import STATUS_OK, format_job_report, job_path, load_job
        from ..core.own_archive import verify_published_own_archive

        job = self._archive_job or load_job(job_path(self.session.data_dir))
        if job is None:
            messagebox.showinfo("Verificar", "No hay trabajo con archivos publicados.")
            return
        self._busy_plan = True
        self.progress.show("Reverificando publicados…", determinate=True)
        gen = self._session_gen

        def worker():
            err = None
            lines = ["Reverificación de ARCHIVO_PROPIO publicados", ""]
            try:
                items = [it for it in job.items.values() if it.status == STATUS_OK]
                for i, it in enumerate(items):
                    if self._archive_cancel:
                        break
                    self.after(
                        0,
                        lambda i=i, n=len(items), name=it.name: self.progress.update(
                            name, i + 1, n
                        ),
                    )
                    r = verify_published_own_archive(
                        Path(it.path), expect_game_id=job.game_id
                    )
                    lines.append(
                        f"{'OK' if r.ok else 'FAIL'} {it.name}: "
                        f"{r.published_path or '; '.join(r.errors[:2])}"
                    )
                    if not r.ok:
                        it.status = "ERROR"
                        it.errors = list(r.errors)
                from ..core.real_archive_job import save_job

                save_job(job, job_path(self.session.data_dir))
                lines.append("\n" + format_job_report(job))
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                body = str(err) if err else "\n".join(lines)
                self._archive_job = job
                self._archive_view_text = body
                self.view_storage.refresh()
                show_scroll_text(
                    self,
                    title="Verificar publicados",
                    body=body,
                    kind="error" if err else "info",
                )

            self.after(0, done)

        self._archive_cancel = False
        threading.Thread(target=worker, daemon=True).start()

    def archive_real_start(self) -> None:
        """Archivado REAL con confirmación explícita hacia carpeta del usuario."""
        if not self.session:
            return
        if self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Primero «Analizar biblioteca».")
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Operación en curso.")
            return
        arch = getattr(self.session.record, "archive_dir", "") or ""
        if not arch:
            messagebox.showinfo(
                "Carpeta requerida",
                "Elige primero una carpeta de archivo (no uses el disco del juego).",
            )
            self.archive_config_dir()
            arch = getattr(self.session.record, "archive_dir", "") or ""
            if not arch:
                return
        from ..core.own_archive import is_archive_root_available, validate_archive_destination

        ok, note = is_archive_root_available(arch)
        if not ok:
            messagebox.showerror("Disco", f"Carpeta no disponible:\n{note}")
            return
        dest_errs = validate_archive_destination(
            Path(arch),
            stage_root=self.session.stage_dir,
            game_root=self.session.game_root,
            mods_dir=self.session.mods_dir
            if self.session.record.mods_dir.strip()
            else None,
        )
        if dest_errs:
            messagebox.showerror("Destino inválido", "\n".join(dest_errs))
            return

        scope = messagebox.askyesnocancel(
            "Alcance del archivado real",
            "SÍ = todo el juego (mods pendientes del catálogo)\n"
            "NO = solo mods marcados «usar» en la biblioteca\n"
            "CANCELAR = abortar\n\n"
            "Prioridad recomendada: Rebirth → Stellar → Remake.",
        )
        if scope is None:
            return
        if scope:
            folders = [m.folder for m in self._archive_catalog.mods]
        else:
            folders = [m.folder for m in self.mods if m.usar]
            if not folders:
                messagebox.showinfo(
                    "Selección",
                    "No hay mods marcados «usar». Marca algunos en Biblioteca o elige todo el juego.",
                )
                return

        if not messagebox.askyesno(
            "CONFIRMAR ARCHIVADO REAL",
            f"Se crearán ARCHIVO_PROPIO verificados en:\n{arch}\n\n"
            f"Mods a considerar: {len(folders)}\n"
            f"Juego: {self.session.record.name}\n\n"
            "• No se modifica staging ni Downloads ni Vortex\n"
            "• No se sobrescriben ZIP existentes\n"
            "• No se borra staging\n"
            "• ARCHIVO_PROPIO ≠ paquete Nexus original\n\n"
            "¿Confirmas el archivado REAL?",
        ):
            return

        self._run_real_archive_job(folders)

    def archive_real_resume(self) -> None:
        if not self.session:
            return
        from ..core.real_archive_job import job_path, load_job

        job = self._archive_job or load_job(job_path(self.session.data_dir))
        if job is None:
            messagebox.showinfo("Reanudar", "No hay trabajo persistido.")
            return
        pending = [k for k, v in job.items.items() if v.status == "PENDIENTE"]
        if not pending and not messagebox.askyesno(
            "Reanudar",
            "No hay PENDIENTE. ¿Reintentar ERROR pasándolos a PENDIENTE?",
        ):
            return
        self._archive_job = job
        folders = list(job.items.keys())
        if not messagebox.askyesno(
            "CONFIRMAR REANUDACIÓN",
            f"Reanudar job {job.job_id[:8]}…\n"
            f"Carpeta: {job.archive_dir}\n"
            "Se omitirán los ya ARCHIVADO VERIFICADO.\n¿Continuar?",
        ):
            return
        self._run_real_archive_job(folders, resume=True)

    def _run_real_archive_job(
        self, folders: list[str], *, resume: bool = False
    ) -> None:
        session = self.session
        assert session is not None
        self._archive_cancel = False
        self._archive_pause = False
        self._busy_plan = True
        self.progress.show("Archivado real…", determinate=True)
        mods = list(self.mods)
        cat = self._archive_catalog
        gen = self._session_gen
        arch = Path(session.record.archive_dir)

        def worker():
            err = None
            text = ""
            job = None
            try:
                from ..core.archive_catalog import save_catalog
                from ..core.real_archive_job import (
                    apply_job_to_catalog,
                    build_or_update_job,
                    format_job_report,
                    job_path,
                    load_job,
                    run_archive_job,
                )

                existing = load_job(job_path(session.data_dir)) if resume else None
                if resume and existing:
                    # reintentar errores
                    for it in existing.items.values():
                        if it.status == "ERROR":
                            it.status = "PENDIENTE"
                            it.errors = []
                job = build_or_update_job(
                    game_id=session.record.id,
                    archive_dir=arch,
                    mods=mods,
                    cat=cat,
                    folders=folders,
                    data_dir=session.data_dir,
                    existing=existing if resume else (existing if existing and existing.game_id == session.record.id else None),
                )

                def prog(phase, cur, tot):
                    self.after(0, lambda: self.progress.update(phase, cur, tot))

                job = run_archive_job(
                    job,
                    mods=mods,
                    stage_root=session.stage_dir,
                    data_dir=session.data_dir,
                    game_root=session.game_root,
                    mods_dir=session.mods_dir
                    if session.record.mods_dir.strip()
                    else None,
                    progress=prog,
                    cancel=lambda: self._archive_cancel,
                    pause=lambda: self._archive_pause,
                    history_path=session.data_dir / "archive_history.json",
                    limit=None,
                )
                if cat is not None:
                    apply_job_to_catalog(job, cat)
                    save_catalog(cat, session.data_dir / "archive_catalog.json")
                text = format_job_report(job)
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                if job is not None:
                    self._archive_job = job
                body = str(err) if err else text
                self._archive_view_text = body
                self.view_storage.refresh()
                show_scroll_text(
                    self,
                    title="Archivado real",
                    body=body,
                    kind="error" if err else "info",
                )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def archive_prepare_library(self) -> None:
        if not self.session:
            return
        if self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Primero «Analizar biblioteca».")
            return
        from ..core.library_archive import format_library_plan, prepare_library_plan

        plan = prepare_library_plan(
            self._archive_catalog,
            archive_dir=getattr(self.session.record, "archive_dir", "") or "",
        )
        text = format_library_plan(plan)
        self._archive_view_text = text
        self.view_storage.refresh()
        show_scroll_text(self, title="Preparar archivo de biblioteca", body=text)

    def archive_show_history(self) -> None:
        if not self.session:
            return
        from ..core.library_archive import load_history

        path = self.session.data_dir / "archive_history.json"
        entries = load_history(path)
        if not entries:
            messagebox.showinfo("Historial", "Sin entradas de archivado todavía.")
            return
        lines = ["Historial de archivado (S12 demos / planes)", ""]
        for e in entries[-80:]:
            lines.append(
                f"{e.get('at')} | {'OK' if e.get('ok') else 'FAIL'} | "
                f"{e.get('action')} | {e.get('folder')} | {e.get('detail', '')[:80]}"
            )
        show_scroll_text(self, title="Historial archivado", body="\n".join(lines))

    def archive_create_own_demo(self) -> None:
        """Crea ARCHIVO_PROPIO de demo en data/.../own_archive_demo (no Vortex)."""
        if not self.session:
            return
        if self._archive_catalog is None:
            messagebox.showinfo("Archivo", "Primero «Analizar biblioteca».")
            return
        if self.is_busy():
            messagebox.showinfo("Ocupado", "Operación en curso.")
            return
        if not messagebox.askyesno(
            "Demo ARCHIVO_PROPIO",
            "Se comprimirán hasta 3 mods del juego activo hacia la carpeta "
            "temporal del gestor (own_archive_demo).\n\n"
            "NO se modifica Vortex, Downloads ni staging.\n"
            "NO se borra nada extraído.\n\n¿Continuar?",
        ):
            return
        self._archive_cancel = False
        self._busy_plan = True
        self.progress.show("Creando ARCHIVO_PROPIO (demo)…", determinate=True)
        session = self.session
        mods = list(self.mods)
        cat = self._archive_catalog
        gen = self._session_gen

        def worker():
            err = None
            text = ""
            try:
                from ..core.archive_catalog import save_catalog
                from ..core.library_archive import create_demo_own_archives

                demo = session.data_dir / "own_archive_demo"
                hist = session.data_dir / "archive_history.json"

                def prog(phase, cur, tot):
                    self.after(0, lambda: self.progress.update(phase, cur, tot))

                _results, text = create_demo_own_archives(
                    game_id=session.record.id,
                    mods=mods,
                    cat=cat,
                    stage_root=session.stage_dir,
                    demo_dir=demo,
                    limit=3,
                    progress=prog,
                    cancel=lambda: self._archive_cancel,
                    history_path=hist,
                )
                save_catalog(cat, session.data_dir / "archive_catalog.json")
            except Exception as e:
                err = e

            def done():
                self._busy_plan = False
                self.progress.hide()
                if gen != self._session_gen:
                    return
                if err:
                    show_scroll_text(
                        self, title="ARCHIVO_PROPIO", body=str(err), kind="error"
                    )
                    return
                self._archive_view_text = text
                self.view_storage.refresh()
                show_scroll_text(self, title="Demo ARCHIVO_PROPIO", body=text)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- game dialogs (settings) ----------
    def _pick_dir(self, initial: str = "") -> str:
        path = filedialog.askdirectory(initialdir=initial or str(ROOT), mustexist=True)
        return path or ""

    def _game_form(self, title: str, initial: GameRecord | None, on_save) -> None:
        if self._busy_write:
            messagebox.showinfo(
                "Operación en curso",
                "No se pueden editar rutas durante una instalación.",
            )
            return
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("720x560")
        win.grab_set()
        form = ctk.CTkScrollableFrame(win)
        form.pack(fill="both", expand=True, padx=16, pady=12)

        def row(label: str, var: tk.StringVar, browse=False, suggest=False):
            fr = ctk.CTkFrame(form, fg_color="transparent")
            fr.pack(fill="x", pady=4)
            ctk.CTkLabel(fr, text=label, width=160, anchor="w").pack(side="left")
            ctk.CTkEntry(fr, textvariable=var, width=420).pack(side="left", padx=6)

            def do_browse():
                p = self._pick_dir(var.get())
                if p:
                    var.set(p)
                    if suggest and game_root_var.get() and adapter_var.get():
                        aid = adapter_id_from_choice(adapter_var.get())
                        mods_var.set(str(suggest_mods_dir(Path(game_root_var.get()), aid)))

            if browse:
                ctk.CTkButton(fr, text="…", width=36, command=do_browse).pack(side="left")

        name_var = tk.StringVar(value=initial.name if initial else "")
        root_var = tk.StringVar(value=initial.game_root if initial else "")
        game_root_var = root_var
        mods_var = tk.StringVar(value=initial.mods_dir if initial else "")
        stage_var = tk.StringVar(value=initial.stage_dir if initial else "")
        vortex_var = tk.StringVar(value=initial.vortex_game_id if initial else "")
        platform_var = tk.StringVar(value=initial.platform if initial else "manual")
        notes_var = tk.StringVar(value=initial.notes if initial else "")
        adapter_var = tk.StringVar(
            value=next(
                (
                    c
                    for c in adapter_choices()
                    if c.startswith((initial.adapter if initial else "generic_folder") + " ")
                ),
                adapter_choices()[0],
            )
        )
        row("Nombre visible", name_var)
        fr_p = ctk.CTkFrame(form, fg_color="transparent")
        fr_p.pack(fill="x", pady=4)
        ctk.CTkLabel(fr_p, text="Plataforma", width=160, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            fr_p, variable=platform_var, values=["steam", "epic", "gog", "manual", "other"], width=200
        ).pack(side="left", padx=6)
        fr_a = ctk.CTkFrame(form, fg_color="transparent")
        fr_a.pack(fill="x", pady=4)
        ctk.CTkLabel(fr_a, text="Adaptador", width=160, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(fr_a, variable=adapter_var, values=adapter_choices(), width=420).pack(
            side="left", padx=6
        )
        row("Raíz del juego", root_var, browse=True, suggest=True)
        row("Carpeta mods (destino)", mods_var, browse=True)
        row("Staging Vortex/local", stage_var, browse=True)
        row("Vortex gameId (opcional)", vortex_var)
        downloads_var = tk.StringVar(value=initial.downloads_dir if initial else "")
        row("Downloads Vortex (opcional)", downloads_var, browse=True)
        row("Notas", notes_var)
        install_var = tk.StringVar(
            value=(initial.install_mode if initial else "COPY") or "COPY"
        )
        fr_i = ctk.CTkFrame(form, fg_color="transparent")
        fr_i.pack(fill="x", pady=4)
        ctk.CTkLabel(fr_i, text="Instalación S09", width=160, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            fr_i, variable=install_var, values=["COPY", "HARDLINK", "AUTO"], width=200
        ).pack(side="left", padx=6)

        def suggest_mods():
            if root_var.get():
                aid = adapter_id_from_choice(adapter_var.get())
                mods_var.set(str(suggest_mods_dir(Path(root_var.get()), aid)))

        ctk.CTkButton(form, text="Sugerir carpeta mods según adaptador", command=suggest_mods).pack(
            pady=8
        )

        def save():
            aid = adapter_id_from_choice(adapter_var.get())
            if initial:
                rec = GameRecord(
                    id=initial.id,
                    name=name_var.get().strip(),
                    vortex_game_id=vortex_var.get().strip(),
                    game_root=root_var.get().strip(),
                    mods_dir=mods_var.get().strip(),
                    stage_dir=stage_var.get().strip(),
                    adapter=aid,
                    platform=platform_var.get().strip() or "manual",
                    data_mode=initial.data_mode,
                    data_dir_name=initial.data_dir_name,
                    notes=notes_var.get().strip(),
                    migration_status=initial.migration_status,
                    migration_note=initial.migration_note,
                    install_mode=install_var.get().strip().upper() or "COPY",
                    downloads_dir=downloads_var.get().strip(),
                    destination_verified=bool(initial.destination_verified),
                    path_status=initial.path_status or "pending",
                )
            else:
                rec = default_record_from_root(
                    name_var.get().strip(),
                    root_var.get().strip(),
                    adapter=aid,
                    platform=platform_var.get().strip() or "manual",
                    vortex_game_id=vortex_var.get().strip(),
                    stage_dir=stage_var.get().strip(),
                )
                rec.mods_dir = mods_var.get().strip() or rec.mods_dir
                rec.notes = notes_var.get().strip()
                rec.install_mode = install_var.get().strip().upper() or "COPY"
                rec.downloads_dir = downloads_var.get().strip()
            on_save(rec, win)

        ctk.CTkButton(win, text="Guardar", fg_color=COLORS["btn_apply"], command=save).pack(pady=12)

    def add_game_dialog(self) -> None:
        def on_save(rec: GameRecord, win):
            errs = add_game(self.registry, rec)
            if errs:
                messagebox.showerror("No se pudo añadir", "\n".join(errs), parent=win)
                return
            save_registry(self.registry)
            ensure_game_data_dir(game_paths_for(rec))
            self._refresh_game_selector()
            set_active_game(self.registry, rec.id)
            save_registry(self.registry)
            self._reload_session()
            win.destroy()
            self.refresh()
            messagebox.showinfo(
                "Juego añadido",
                f"«{rec.name}» registrado.\nDatos en:\n{game_paths_for(rec).data_dir}",
            )

        self._game_form("Añadir juego", None, on_save)

    def edit_game_dialog(self) -> None:
        if not self.session:
            messagebox.showinfo("Sin juego", "No hay juego activo.")
            return

        def on_save(rec: GameRecord, win):
            errs = update_game(self.registry, rec)
            if errs:
                messagebox.showerror("No se pudo guardar", "\n".join(errs), parent=win)
                return
            save_registry(self.registry)
            self._reload_session()
            win.destroy()
            self.refresh()

        self._game_form("Editar carpetas del juego", self.session.record, on_save)

    def remove_game_dialog(self) -> None:
        if not self.session or self.is_busy():
            return
        g = self.session.record
        if not messagebox.askyesno(
            "Quitar del registro",
            f"¿Quitar «{g.name}» del registro?\n\n"
            "NO se borran archivos del juego, staging ni backups.",
        ):
            return
        errs = remove_game(self.registry, g.id)
        if errs:
            messagebox.showerror("Error", "\n".join(errs))
            return
        save_registry(self.registry)
        self._reload_session()
        self._refresh_game_selector()
        self.refresh()

    def migration_dialog(self) -> None:
        if self.is_busy():
            return
        plan = prepare_ff7r_migration(self.registry)
        msg = (
            f"Estado: {'BLOQUEADO' if plan.blocked else 'Preparada'}\n"
            f"{plan.reason}\n\n"
            f"Origen: {plan.source_data}\n"
            f"Destino: {plan.target_data}\n"
            f"Archivos: {', '.join(plan.files_to_copy) or '(ninguno)'}\n\n"
            f"{plan.reversible_note}\n\n"
            "La migración NO se ejecuta sola.\n"
            "¿Ejecutar ahora la COPIA aislada?"
        )
        if plan.blocked:
            show_scroll_text(self, title="Migración FF7R", body=msg, kind="error")
            return
        if not ask_scroll_confirm(
            self, title="Migración FF7R", body=msg, confirm_label="Copiar datos"
        ):
            return
        try:
            from ..core.games import execute_ff7r_migration_copy

            self.registry = execute_ff7r_migration_copy(self.registry, plan)
            self._reload_session()
            self._refresh_game_selector()
            self.refresh()
            messagebox.showinfo(
                "Migración completada",
                "Datos copiados. Originales conservados. Steam/Vortex no tocados.",
            )
        except Exception as e:
            show_scroll_text(self, title="Migración fallida", body=str(e), kind="error")

    # Compat S05 tests: panel openers → navigation
    def open_conflicts_panel(self) -> None:
        self.show_view("conflicts")

    def open_files_panel(self) -> None:
        self.show_view("installed")

    def open_history_panel(self) -> None:
        self.show_view("history")


def run() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = ModManagerApp()
    app.mainloop()
