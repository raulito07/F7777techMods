# -*- coding: utf-8 -*-
"""
F7777techMods — paneles visuales de Biblioteca (catálogo / lista con miniatura).
"""

from __future__ import annotations

import customtkinter as ctk

from ...core.library_catalog_model import CatalogModItem
from ...core.library_view_prefs import CARD_DIMS, VISUAL_INSERT_BATCH
from ...core.thumb_async import ThumbAsyncRuntime
from ...core.thumb_display import ThumbImageCache
from ..theme import COLORS

_ROW_COLORS = {
    "ready": "#14352a",
    "conflict": "#5c1a1a",
    "pending": "#3b2f14",
    "active": "#1a2e3d",
    "active_inst": "#1a2e3d",
    "installed": "#1a2e3d",
    "off": "#2a2a32",
    "unchanged": "#2a2a32",
}

_IMAGE_REF_CAP = 384


class LibraryVisualPane:
    """Renderizado incremental en CTkScrollableFrame."""

    def __init__(self, master, *, on_click) -> None:
        self.master = master
        self.on_click = on_click
        self.scroll = ctk.CTkScrollableFrame(master, fg_color=COLORS["bg_card"])
        self._gen = 0
        self._items: list[CatalogModItem] = []
        self._widgets: dict[str, ctk.CTkFrame] = {}
        self._selected: set[str] = set()
        self._layout = "visual_list"
        self._card_size = "medium"
        self._thumb_cache = ThumbImageCache(max_entries=128)
        self._thumb_async: ThumbAsyncRuntime | None = None
        self._idx = 0
        self._grid_frame = None
        self._image_refs: list = []

    def pack(self, **kw) -> None:
        self.scroll.pack(**kw)

    def pack_forget(self) -> None:
        self.scroll.pack_forget()

    def set_selection(self, folders: set[str]) -> None:
        self._selected = set(folders)
        self._refresh_selection_style()

    def clear_widgets(self) -> None:
        self._gen += 1
        if self._thumb_async:
            self._thumb_async.set_paint_gen(self._gen)
        self._items = []
        self._idx = 0
        self._grid_frame = None
        self._image_refs.clear()
        for w in self.scroll.winfo_children():
            w.destroy()
        self._widgets.clear()

    def set_thumb_cache(self, cache: ThumbImageCache | None) -> None:
        if cache is not None:
            self._thumb_cache = cache

    def set_thumb_async(self, runtime: ThumbAsyncRuntime | None) -> None:
        self._thumb_async = runtime

    def start_paint(
        self,
        items: list[CatalogModItem],
        *,
        layout: str,
        card_size: str,
        selected: set[str] | None = None,
    ) -> None:
        self.clear_widgets()
        if selected is not None:
            self._selected = set(selected)
        self._gen += 1
        gen = self._gen
        if self._thumb_async:
            self._thumb_async.set_paint_gen(gen)
        self._items = list(items)
        self._layout = layout
        self._card_size = card_size
        self._idx = 0
        self._paint_batch(gen)

    def _paint_batch(self, gen: int) -> None:
        if gen != self._gen:
            return
        end = min(self._idx + VISUAL_INSERT_BATCH, len(self._items))
        if self._layout == "catalog":
            self._paint_catalog_range(gen, self._idx, end)
        else:
            self._paint_list_range(gen, self._idx, end)
        self._idx = end
        self._refresh_selection_style()
        if end < len(self._items):
            self.master.after(1, lambda: self._paint_batch(gen))

    def _hold_image_ref(self, img) -> None:
        self._image_refs.append(img)
        if len(self._image_refs) > _IMAGE_REF_CAP:
            del self._image_refs[: len(self._image_refs) - _IMAGE_REF_CAP]

    def _apply_thumb(
        self,
        gen: int,
        mod_id: str,
        label: ctk.CTkLabel,
        ctk_img,
    ) -> None:
        if gen != self._gen or mod_id not in self._widgets:
            return
        try:
            if not label.winfo_exists():
                return
        except Exception:
            return
        self._hold_image_ref(ctk_img)
        label._sgm_thumb_ref = ctk_img  # type: ignore[attr-defined]
        label._sgm_mod_id = mod_id  # type: ignore[attr-defined]
        label.configure(image=ctk_img, text="")

    def _thumb_label(
        self, gen: int, parent, item: CatalogModItem, tw: int, th: int
    ) -> ctk.CTkLabel:
        path = item.preview_path
        label = ctk.CTkLabel(
            parent,
            text="—",
            width=tw,
            height=th,
            fg_color="#252830",
            text_color=COLORS["text_muted"],
        )
        if not path:
            return label
        runtime = self._thumb_async
        if runtime is not None:
            mod_id = item.mod_id

            def _ready(img, g=gen, mid=mod_id, lab=label):
                self._apply_thumb(g, mid, lab, img)

            runtime.request_ctk_image(
                path=path,
                mod_id=mod_id,
                max_w=tw,
                max_h=th,
                paint_gen=gen,
                on_ready=_ready,
            )
            return label
        try:
            img = self._thumb_cache.get_ctk_image(path, tw, th)
            self._hold_image_ref(img)
            label.configure(image=img, text="")
            label._sgm_thumb_ref = img  # type: ignore[attr-defined]
        except (OSError, FileNotFoundError):
            pass
        return label

    def _bind_click(self, widget, folder: str) -> None:
        def _handler(evt, f=folder):
            self.on_click(f, evt)
            return "break"

        widget.bind("<Button-1>", _handler)
        for ch in widget.winfo_children():
            self._bind_click(ch, folder)

    def _refresh_selection_style(self) -> None:
        for fid, fr in self._widgets.items():
            try:
                fr.configure(
                    border_width=2 if fid in self._selected else 0,
                    border_color="#5a9fd4",
                )
            except Exception:
                pass

    def _paint_list_range(self, gen: int, start: int, end: int) -> None:
        for i in range(start, end):
            item = self._items[i]
            bg = _ROW_COLORS.get(item.state_tag, "#2a2a32")
            row = ctk.CTkFrame(self.scroll, fg_color=bg, corner_radius=6)
            row.pack(fill="x", padx=4, pady=2)
            thumb = self._thumb_label(gen, row, item, 56, 56)
            thumb.pack(side="left", padx=6, pady=4)
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, padx=4, pady=4)
            plan = "Plan: SI" if item.plan_active else "Plan: NO"
            ctk.CTkLabel(
                col,
                text=item.display_name,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(anchor="w")
            ctk.CTkLabel(
                col,
                text=f"{item.state_label} · {plan} · {item.source}",
                anchor="w",
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w")
            ctk.CTkLabel(
                col,
                text=f"Etiquetas: {', '.join(item.tags[:6]) or '—'}",
                anchor="w",
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=10),
            ).pack(anchor="w")
            self._widgets[item.mod_id] = row
            self._bind_click(row, item.mod_id)

    def _paint_catalog_range(self, gen: int, start: int, end: int) -> None:
        tw, th, cw = CARD_DIMS.get(self._card_size, CARD_DIMS["medium"])
        if self._grid_frame is None:
            self._grid_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
            self._grid_frame.pack(fill="x", padx=4, pady=4)
        grid = self._grid_frame
        max_cols = max(2, 520 // cw)
        for i in range(start, end):
            item = self._items[i]
            bg = _ROW_COLORS.get(item.state_tag, "#2a2a32")
            card = ctk.CTkFrame(grid, fg_color=bg, corner_radius=8, width=cw)
            card.grid(row=i // max_cols, column=i % max_cols, padx=6, pady=6, sticky="n")
            thumb = self._thumb_label(gen, card, item, tw, th)
            thumb.pack(padx=8, pady=(8, 4))
            name = item.display_name
            if len(name) > 36:
                name = name[:33] + "…"
            ctk.CTkLabel(
                card,
                text=name,
                wraplength=cw - 12,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(padx=6)
            ctk.CTkLabel(
                card,
                text=item.category,
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=10),
            ).pack(padx=6)
            ctk.CTkLabel(
                card,
                text=item.state_label[:32],
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=10),
            ).pack(padx=6, pady=(0, 6))
            self._widgets[item.mod_id] = card
            self._bind_click(card, item.mod_id)

    def select_all_visible(self) -> set[str]:
        return set(self._widgets.keys())
