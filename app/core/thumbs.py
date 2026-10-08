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

Load Vortex/Nexus mod pictures and cache them locally.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from pathlib import Path

from .paths import DATA, LEGACY_FF7R_VORTEX_ID
from .vortex_sync import find_vortex_state_backup


def _latest_state() -> Path | None:
    """Backup JSON histórico de Vortex (meta/imágenes). No es estado vivo."""
    return find_vortex_state_backup()


def extract_vortex_meta(
    force: bool = False,
    *,
    vortex_game_id: str | None = None,
    meta_cache: Path | None = None,
) -> dict[str, dict]:
    """
    folder_name -> {pictureUrl, shortDescription, modName, modId, description}
    """
    game_id = vortex_game_id or LEGACY_FF7R_VORTEX_ID
    cache = meta_cache if meta_cache is not None else DATA / "vortex_mod_meta.json"

    if not game_id:
        return {}

    if cache.exists() and not force:
        try:
            age_ok = True
            state = _latest_state()
            if state and state.stat().st_mtime > cache.stat().st_mtime:
                age_ok = False
            if age_ok:
                return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    state = _latest_state()
    if not state:
        return {}
    try:
        obj = json.loads(state.read_text(encoding="utf-8"))
    except Exception:
        return {}

    mods_root = obj.get("persistent", {}).get("mods", {}).get(game_id, {})
    out: dict[str, dict] = {}
    for folder, info in mods_root.items():
        attrs = info.get("attributes") or {}
        out[folder] = {
            "pictureUrl": attrs.get("pictureUrl") or "",
            "shortDescription": attrs.get("shortDescription") or "",
            "description": attrs.get("description") or "",
            "modName": attrs.get("modName") or attrs.get("customFileName") or "",
            "modId": attrs.get("modId"),
            "author": attrs.get("author") or attrs.get("uploader") or "",
        }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def thumb_path_for(
    folder: str,
    mod_id,
    url: str,
    *,
    thumbs_dir: Path | None = None,
) -> Path:
    base = thumbs_dir if thumbs_dir is not None else DATA / "thumbs"
    ext = ".jpg"
    if url:
        m = re.search(r"\.(png|jpe?g|webp|gif)(?:\?|$)", url, re.I)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
    key = str(mod_id) if mod_id else re.sub(r"[^\w\-]+", "_", folder)[:80]
    return base / f"{key}{ext}"


def ensure_thumb(
    folder: str,
    meta: dict,
    timeout: float = 12.0,
    *,
    thumbs_dir: Path | None = None,
) -> Path | None:
    url = (meta or {}).get("pictureUrl") or ""
    if not url:
        return None
    path = thumb_path_for(folder, meta.get("modId"), url, thumbs_dir=thumbs_dir)
    if path.exists() and path.stat().st_size > 500:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nexusmods.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 200:
            return None
        path.write_bytes(data)
        return path
    except Exception:
        return None


def prefetch_thumbs(
    meta_by_folder: dict[str, dict],
    folders: list[str],
    on_done=None,
    *,
    thumbs_dir: Path | None = None,
) -> None:
    """Download missing thumbs in background."""

    def worker():
        for folder in folders:
            meta = meta_by_folder.get(folder) or {}
            ensure_thumb(folder, meta, thumbs_dir=thumbs_dir)
        if on_done:
            on_done()

    threading.Thread(target=worker, daemon=True).start()
