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

Caché verificable de SHA-256 (mtime + size).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


class HashCache:
    """Persiste hashes; invalida si cambian mtime o tamaño."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._data: dict[str, dict] = {}
        if path and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw.get("files") or {}
            except Exception:
                self._data = {}

    def get(self, file_path: Path) -> str | None:
        if not file_path.is_file():
            return None
        key = str(file_path.resolve())
        try:
            st = file_path.stat()
        except OSError:
            return None
        ent = self._data.get(key)
        if (
            ent
            and int(ent.get("mtime_ns", -1)) == getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            and int(ent.get("size", -1)) == st.st_size
            and ent.get("sha256")
        ):
            return str(ent["sha256"])
        digest = sha256_file(file_path)
        self._data[key] = {
            "mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
            "size": st.st_size,
            "sha256": digest,
        }
        return digest

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": 1, "files": self._data}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
