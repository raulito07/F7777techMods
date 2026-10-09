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

Fusión no destructiva de managed_manifest (recuperación S19 / migraciones).
"""

from __future__ import annotations

import json
from pathlib import Path


def _read_manifest(path: Path) -> dict:
    if not path.is_file():
        return {"version": 2, "updated_at": "", "files": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Manifiesto inválido: {path}")
    files = raw.get("files")
    if files is None:
        files = {}
    if not isinstance(files, dict):
        raise ValueError(f"Manifiesto files inválido: {path}")
    return {
        "version": int(raw.get("version") or 2),
        "updated_at": str(raw.get("updated_at") or ""),
        "files": dict(files),
    }


def merge_managed_manifest(
    target: Path,
    source: Path,
    *,
    only_rel: set[str] | None = None,
) -> tuple[int, int]:
    """Añade entradas ausentes en target desde source. No sobrescribe claves existentes.

    Returns (added, skipped_existing).
    """
    tgt = _read_manifest(target)
    src = _read_manifest(source)
    added = 0
    skipped = 0
    for rel, meta in src["files"].items():
        if only_rel is not None and rel not in only_rel:
            continue
        if not isinstance(meta, dict):
            continue
        if rel in tgt["files"]:
            skipped += 1
            continue
        tgt["files"][rel] = meta
        added += 1
    if added and not tgt["updated_at"]:
        tgt["updated_at"] = src.get("updated_at") or tgt["updated_at"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(tgt, ensure_ascii=False, indent=2), encoding="utf-8")
    return added, skipped
