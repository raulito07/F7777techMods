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

Caché acotada de miniaturas CTkImage y carga PIL sin fugas de descriptores.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from .win_compat import log_ui

DEFAULT_THUMB_CACHE_MAX = 96


class ThumbImageCache:
    """LRU de CTkImage; reutiliza PhotoImage internos al navegar muchos mods."""

    def __init__(self, max_entries: int = DEFAULT_THUMB_CACHE_MAX) -> None:
        self._max = max(1, min(256, int(max_entries)))
        self._cache: OrderedDict[tuple, ctk.CTkImage] = OrderedDict()

    def clear(self) -> None:
        self._cache.clear()

    def _key_for(self, path: str, max_w: int, max_h: int) -> tuple:
        p = Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size, max_w, max_h)

    def peek(self, path: str, max_w: int, max_h: int):
        p = Path(path)
        if not p.is_file():
            return None
        try:
            key = self._key_for(path, max_w, max_h)
        except OSError:
            return None
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        return None

    def insert_from_pil(
        self,
        path: str,
        max_w: int,
        max_h: int,
        light: Image.Image,
        dark: Image.Image,
    ) -> ctk.CTkImage:
        key = self._key_for(path, max_w, max_h)
        size = light.size
        ctk_img = ctk.CTkImage(light_image=light, dark_image=dark, size=size)
        self._cache[key] = ctk_img
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return ctk_img

    @staticmethod
    def load_thumbnail_pil(path: str, max_w: int, max_h: int) -> Image.Image:
        with Image.open(path) as src:
            img = src.convert("RGBA")
        img.thumbnail((max_w, max_h))
        return img

    def get_ctk_image(self, path: str, max_w: int, max_h: int) -> ctk.CTkImage:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(path)
        hit = self.peek(path, max_w, max_h)
        if hit is not None:
            return hit
        light = self.load_thumbnail_pil(path, max_w, max_h)
        dark = light.copy()
        return self.insert_from_pil(path, max_w, max_h, light, dark)


def thumb_display_size(zoom_pct: int) -> tuple[int, int]:
    scale = zoom_pct / 100.0
    w = int(300 * min(max(scale, 0.9), 1.4))
    h = int(160 * min(max(scale, 0.9), 1.4))
    return w, h


def log_thumb_error(message: str, *, exc: BaseException | None = None) -> None:
    if exc is not None:
        log_ui(f"thumb ERROR {message}: {type(exc).__name__}: {exc}")
    else:
        log_ui(f"thumb {message}")
