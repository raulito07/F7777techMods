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

S04 — inventario del destino y clasificación de procedencia verificable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .hash_cache import HashCache

CASE_INSENSITIVE = os.name == "nt"
KEEP = {"vortex.deployment.json", "_manual_loadout.json"}


class Provenance(str, Enum):
    GESTIONADO = "GESTIONADO"
    VORTEX = "VORTEX"
    EXTERNO = "EXTERNO"
    DESCONOCIDO = "DESCONOCIDO"


class Integrity(str, Enum):
    OK = "OK"
    MISSING_HASH = "SIN_HASH"
    MATCH = "COINCIDE"
    DRIFT = "MODIFICADO_EXTERNO"
    UNKNOWN = "DESCONOCIDO"
    ERROR = "ERROR"


def _norm_rel(rel: str) -> str:
    s = rel.replace("\\", "/").strip("/")
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _norm_key(rel: str) -> str:
    n = _norm_rel(rel)
    return n.casefold() if CASE_INSENSITIVE else n


@dataclass
class DestFileInfo:
    rel: str
    abs_path: Path
    size: int
    provenance: Provenance
    integrity: Integrity
    sha256: str = ""
    mod_folder: str = ""
    mod_name: str = ""
    vortex_source: str = ""
    note: str = ""


@dataclass
class DestInventory:
    files: list[DestFileInfo] = field(default_factory=list)
    vortex_deploy_active: bool = False
    vortex_targets: dict[str, str] = field(default_factory=dict)


def parse_vortex_deployment(deploy_path: Path) -> dict[str, str]:
    """Mapa dest_key → source. Solo evidencia del JSON de deploy."""
    if not deploy_path.exists():
        return {}
    try:
        data = json.loads(deploy_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for entry in data.get("files") or []:
        if not isinstance(entry, dict):
            continue
        rel = (
            entry.get("relPath")
            or entry.get("relativePath")
            or entry.get("path")
            or entry.get("dest")
            or entry.get("target")
            or entry.get("rel")
            or entry.get("base")
            or entry.get("file")
            or entry.get("name")
        )
        source = entry.get("source") or entry.get("src") or ""
        if not rel:
            continue
        rel_n = _norm_rel(str(rel))
        p = Path(rel_n)
        if p.is_absolute() or getattr(p, "drive", ""):
            continue
        if any(part == ".." for part in p.parts):
            continue
        out[_norm_key(rel_n)] = str(source)
    return out


def scan_destination(
    mods_dir: Path,
    *,
    manifest: dict[str, dict],
    deploy_path: Path,
    hash_cache: HashCache | None = None,
    compute_hashes: bool = False,
) -> DestInventory:
    """Clasifica cada archivo del destino. No modifica nada."""
    inv = DestInventory(vortex_deploy_active=deploy_path.exists())
    inv.vortex_targets = parse_vortex_deployment(deploy_path)
    managed = {_norm_key(r): (r, meta) for r, meta in manifest.items()}
    cache = hash_cache or HashCache(None)

    if not mods_dir.exists():
        return inv

    root_res = mods_dir.resolve()
    for f in sorted(mods_dir.rglob("*"), key=lambda p: str(p).lower()):
        if not f.is_file() or f.name in KEEP:
            continue
        try:
            rel = _norm_rel(f.relative_to(mods_dir).as_posix())
            resolved = f.resolve(strict=False)
            resolved.relative_to(root_res)
        except Exception:
            inv.files.append(
                DestFileInfo(
                    rel=str(f),
                    abs_path=f,
                    size=0,
                    provenance=Provenance.DESCONOCIDO,
                    integrity=Integrity.ERROR,
                    note="Ruta no validable bajo el destino autorizado.",
                )
            )
            continue

        k = _norm_key(rel)
        try:
            size = f.stat().st_size
        except OSError:
            inv.files.append(
                DestFileInfo(
                    rel=rel,
                    abs_path=f,
                    size=0,
                    provenance=Provenance.DESCONOCIDO,
                    integrity=Integrity.ERROR,
                    note="No se pudo leer metadatos del archivo.",
                )
            )
            continue

        sha = ""
        if compute_hashes:
            try:
                sha = cache.get(f) or ""
            except Exception:
                sha = ""

        if k in managed:
            canon, meta = managed[k]
            expected = str(meta.get("sha256") or "")
            integ = Integrity.MISSING_HASH
            if expected and sha:
                integ = Integrity.MATCH if sha == expected else Integrity.DRIFT
            elif expected and not sha:
                integ = Integrity.UNKNOWN
            inv.files.append(
                DestFileInfo(
                    rel=canon,
                    abs_path=f,
                    size=size,
                    provenance=Provenance.GESTIONADO,
                    integrity=integ,
                    sha256=sha,
                    mod_folder=str(meta.get("mod_folder") or ""),
                    mod_name=str(meta.get("mod_name") or ""),
                    note=str(meta.get("origin") or "install"),
                )
            )
            continue

        if k in inv.vortex_targets:
            inv.files.append(
                DestFileInfo(
                    rel=rel,
                    abs_path=f,
                    size=size,
                    provenance=Provenance.VORTEX,
                    integrity=Integrity.UNKNOWN,
                    sha256=sha,
                    vortex_source=inv.vortex_targets[k],
                    note="Listado en vortex.deployment.json",
                )
            )
            continue

        inv.files.append(
            DestFileInfo(
                rel=rel,
                abs_path=f,
                size=size,
                provenance=Provenance.EXTERNO,
                integrity=Integrity.UNKNOWN,
                sha256=sha,
                note="Sin manifiesto del gestor ni entrada verificable de deploy Vortex.",
            )
        )

    try:
        cache.save()
    except Exception:
        pass
    return inv
