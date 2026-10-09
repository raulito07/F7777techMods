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

Hilo auxiliar: solo I/O y PIL. CTkImage y widgets solo en el main loop.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable

from PIL import Image

from .thumb_display import ThumbImageCache
from .thumbs import ensure_thumb


class ThumbAsyncRuntime:
    """Cola en hilo UI para prefetch/decodificación de miniaturas."""

    def __init__(self, tk_root, *, cache: ThumbImageCache | None = None) -> None:
        self._root = tk_root
        self._cache = cache or ThumbImageCache(max_entries=128)
        self._main_q: queue.Queue = queue.Queue()
        self._work_q: queue.Queue = queue.Queue()
        self._session_gen = 0
        self._paint_gen = 0
        self._prefetch_cb_seq = 0
        self._prefetch_cbs: dict[int, Callable[[], None]] = {}
        self._decode_seq = 0
        self._decode_cbs: dict[int, tuple[int, int, str, Callable]] = {}
        self._cancel_prefetch = threading.Event()
        self._poll_scheduled = False
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    @property
    def cache(self) -> ThumbImageCache:
        return self._cache

    def start_polling(self) -> None:
        if not self._poll_scheduled:
            self._poll_scheduled = True
            self._schedule_poll()

    def set_session_gen(self, gen: int) -> None:
        self._session_gen = int(gen)
        self.cancel_prefetch()
        self._decode_cbs.clear()
        self._work_q.put(("flush",))

    def set_paint_gen(self, gen: int) -> None:
        self._paint_gen = int(gen)

    def cancel_prefetch(self) -> None:
        self._cancel_prefetch.set()
        self._cancel_prefetch = threading.Event()

    def prefetch_missing(
        self,
        meta_by_folder: dict,
        folders: list[str],
        *,
        thumbs_dir: Path | None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.cancel_prefetch()
        ev = self._cancel_prefetch
        session = self._session_gen
        cb_id = 0
        if on_done:
            self._prefetch_cb_seq += 1
            cb_id = self._prefetch_cb_seq
            self._prefetch_cbs[cb_id] = on_done
        self._work_q.put(
            ("prefetch", session, cb_id, list(folders), meta_by_folder, thumbs_dir, ev)
        )

    def request_ctk_image(
        self,
        *,
        path: str,
        mod_id: str,
        max_w: int,
        max_h: int,
        paint_gen: int,
        on_ready: Callable[[object], None],
    ) -> None:
        session = self._session_gen
        hit = self._cache.peek(path, max_w, max_h)
        if hit is not None:
            if session == self._session_gen and paint_gen == self._paint_gen:
                on_ready(hit)
            return
        self._decode_seq += 1
        rid = self._decode_seq
        self._decode_cbs[rid] = (session, int(paint_gen), mod_id, on_ready)
        self._work_q.put(
            ("decode", session, int(paint_gen), mod_id, path, max_w, max_h, rid)
        )

    def _worker_loop(self) -> None:
        while True:
            job = self._work_q.get()
            if not job:
                continue
            kind = job[0]
            if kind == "flush":
                continue
            if kind == "prefetch":
                _, session, cb_id, folders, meta_by, thumbs_dir, ev = job
                for folder in folders:
                    if ev.is_set():
                        break
                    meta = (meta_by or {}).get(folder) or {}
                    ensure_thumb(folder, meta, thumbs_dir=thumbs_dir)
                self._main_q.put(("prefetch_done", session, cb_id))
            elif kind == "decode":
                _, session, paint_gen, mod_id, path, max_w, max_h, rid = job
                if session != self._session_gen:
                    self._main_q.put(("decode_skip", rid))
                    continue
                p = Path(path)
                if not p.is_file():
                    self._main_q.put(("decode_skip", rid))
                    continue
                try:
                    light, dark = _pil_pair(path, max_w, max_h)
                except OSError:
                    self._main_q.put(("decode_skip", rid))
                    continue
                self._main_q.put(
                    (
                        "decode_done",
                        session,
                        paint_gen,
                        mod_id,
                        path,
                        max_w,
                        max_h,
                        light,
                        dark,
                        rid,
                    )
                )

    def _schedule_poll(self) -> None:
        try:
            if not self._poll_scheduled:
                return
            try:
                if not self._root.winfo_exists():
                    self._poll_scheduled = False
                    return
            except Exception:
                self._poll_scheduled = False
                return
            self._drain_main_queue()
        finally:
            if not self._poll_scheduled:
                return
            try:
                if self._root.winfo_exists():
                    self._root.after(25, self._schedule_poll)
                else:
                    self._poll_scheduled = False
            except Exception:
                self._poll_scheduled = False

    def _drain_main_queue(self) -> None:
        while True:
            try:
                msg = self._main_q.get_nowait()
            except queue.Empty:
                break
            kind = msg[0]
            if kind == "prefetch_done":
                session, cb_id = msg[1], msg[2]
                if session != self._session_gen:
                    self._prefetch_cbs.pop(cb_id, None)
                    continue
                cb = self._prefetch_cbs.pop(cb_id, None)
                if cb:
                    cb()
            elif kind == "decode_skip":
                self._decode_cbs.pop(msg[1], None)
            elif kind == "decode_done":
                (
                    session,
                    paint_gen,
                    mod_id,
                    path,
                    max_w,
                    max_h,
                    light,
                    dark,
                    rid,
                ) = msg[1:]
                entry = self._decode_cbs.pop(rid, None)
                if entry is None:
                    light.close()
                    dark.close()
                    continue
                es, ep, em, on_ready = entry
                if (
                    session != self._session_gen
                    or paint_gen != self._paint_gen
                    or es != session
                    or ep != paint_gen
                    or em != mod_id
                ):
                    light.close()
                    dark.close()
                    continue
                try:
                    ctk_img = self._cache.insert_from_pil(
                        path, max_w, max_h, light, dark
                    )
                    on_ready(ctk_img)
                except Exception:
                    pass

    def shutdown(self) -> None:
        self.cancel_prefetch()
        self._decode_cbs.clear()
        self._poll_scheduled = False


def _pil_pair(path: str, max_w: int, max_h: int) -> tuple[Image.Image, Image.Image]:
    with Image.open(path) as src:
        img = src.convert("RGBA")
    img.thumbnail((max_w, max_h))
    return img.copy(), img.copy()


def schedule_on_main(tk_root, fn: Callable[[], None]) -> None:
    """Programa un callback en el hilo principal."""
    try:
        tk_root.after(0, fn)
    except Exception:
        pass
