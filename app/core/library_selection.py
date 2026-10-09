# -*- coding: utf-8 -*-
"""
F7777techMods — selección compartida Biblioteca (todas las presentaciones).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LibrarySelection:
    """Conjunto de mod_id seleccionados + ancla para Shift+rango."""

    selected: set[str] = field(default_factory=set)
    anchor: str = ""

    def clear(self) -> None:
        self.selected.clear()
        self.anchor = ""

    def click(
        self,
        folder: str,
        *,
        visible_order: list[str],
        ctrl: bool,
        shift: bool,
    ) -> None:
        if not folder:
            return
        if shift and self.anchor and self.anchor in visible_order and folder in visible_order:
            i0 = visible_order.index(self.anchor)
            i1 = visible_order.index(folder)
            lo, hi = sorted((i0, i1))
            rng = set(visible_order[lo : hi + 1])
            if ctrl:
                self.selected ^= rng
            else:
                self.selected = rng
        elif ctrl:
            if folder in self.selected:
                self.selected.discard(folder)
            else:
                self.selected.add(folder)
        else:
            self.selected = {folder}
        self.anchor = folder

    def set_folders(self, folders: list[str], *, replace: bool = True) -> None:
        if replace:
            self.selected = set(folders)
        else:
            self.selected.update(folders)
        if folders:
            self.anchor = folders[-1]

    def primary(self) -> str:
        if self.anchor and self.anchor in self.selected:
            return self.anchor
        return next(iter(self.selected), "")
