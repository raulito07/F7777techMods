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
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .paths import STAGE, DEPLOY

# Extensiones de payload inventariables (S49). No implica instalabilidad.
_PAYLOAD_SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
_PAYLOAD_SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".db",
}
_PAYLOAD_MAX_FILES = 200

CHAR_PATS = [
    ("CLOUD", ["cloud", "buster sword", "hard edge", "iron sword", "mythril", "fusion sword", "noctis", "squall"]),
    ("TIFA", ["tifa"]),
    ("AERITH", ["aerith"]),
    ("BARRET", ["barret", "barrett"]),
    ("YUFFIE", ["yuffie", "sonon"]),
    ("SEPHIROTH", ["sephiroth"]),
    ("SCARLET", ["scarlet", "scarlett"]),
    ("SHIVA", ["shiva"]),
    ("MADAM_M / HONEYBEE", ["madam", "madame", "honeybee", "andrea"]),
    ("RED XIII", ["red xiii", "redxiii"]),
    ("JESSIE / BIGGS / NPC", ["jessie", "biggs", "wedge", "kyrie"]),
    ("RUDE / SHINRA", ["rude", "shinra", "huntsman", "riot", "security trooper", "machine gun", "shotgun", "killzone"]),
    ("COMBATE / QOL", ["atb", "stagger", "lv99", "aggro", "enemy", "double ap", "timer", "summons", "equipment", "betterweapon", "owa", "slayer", "fov70", "invincible", "learn enemy", "respawn", "no red", "grapple"]),
    ("MUSICA / CUTSCENE", ["music", "bgm", "rescore", "mako", "chapter", "wall market", "roche", "sewer", "eligor", "flowers", "fixed color", "castellano", "bilingual", "multilingual", "mm -"]),
    ("GRAFICOS", ["reshade", "basemod", "3dmigoto", "hdr", "vulkan", "hyper hd", "ffviihook"]),
]


def short_name(folder: str) -> str:
    s = re.sub(r"-\d{3,}(-|$).*", "", folder)
    s = re.sub(r"-\d{9,}.*", "", s)
    return s.strip(" -_")


def classify(text: str) -> list[str]:
    t = text.lower()
    hits = [char for char, pats in CHAR_PATS if any(p in t for p in pats)]
    return hits or ["OTROS"]


def nexus_id_from_folder(folder: str) -> str | None:
    # Name-1234-version-timestamp
    m = re.search(r"-(\d{2,6})-\d", folder)
    return m.group(1) if m else None


@dataclass
class ModEntry:
    folder: str
    name: str
    characters: list[str]
    character_main: str
    paks: list[str]
    multi: bool
    on_disk: bool
    stage_path: str
    nexus_id: str | None = None
    description: str = ""
    category: str = ""
    slots: list[str] = field(default_factory=list)
    usar: bool = False
    pak_elegido: str = ""
    paks_elegidos: list[str] = field(default_factory=list)
    selection_mode: str = ""
    conflicto: str = ""
    picture_url: str = ""
    thumb_path: str = ""
    author: str = ""
    nexus_mod_name: str = ""
    # S15 — procedencia
    source_kind: str = "STAGING_VORTEX"  # STAGING_VORTEX | WORK_LIBRARY
    mod_id: str = ""
    archive_path: str = ""
    archive_content_sha256: str = ""
    archive_zip_sha256: str = ""
    work_extracted: bool = False
    archived: bool = False
    # S38 — identidad de componente dentro de un paquete/colección
    package_folder: str = ""
    package_name: str = ""
    companion_ids: list[str] = field(default_factory=list)
    tag_certainty: str = ""
    installable_unit: bool = True
    # S49 — payload universal (identidad en Biblioteca ≠ instalable)
    payload_files: list[str] = field(default_factory=list)
    payload_exts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def package_payload_summary(mod: ModEntry) -> tuple[list[str], list[str]]:
    """Devuelve (payload_files, payload_exts) del ModEntry."""
    files = list(getattr(mod, "payload_files", None) or [])
    exts = list(getattr(mod, "payload_exts", None) or [])
    return files, exts


def collect_payload(stage_dir: Path) -> tuple[list[str], list[str]]:
    """
    Lista relativa de archivos de payload y extensiones únicas (solo lectura).
    Incluye formatos desconocidos para que el mod aparezca en Biblioteca.
    """
    files: list[str] = []
    ext_set: set[str] = set()
    if not stage_dir.is_dir():
        return files, []
    for p in stage_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower() in _PAYLOAD_SKIP_NAMES:
            continue
        suf = p.suffix.lower()
        if suf in _PAYLOAD_SKIP_SUFFIXES:
            continue
        try:
            rel = str(p.relative_to(stage_dir)).replace("\\", "/")
        except ValueError:
            rel = p.name
        files.append(rel)
        ext_set.add(suf or "(none)")
        if len(files) >= _PAYLOAD_MAX_FILES:
            break
    files.sort(key=str.lower)
    return files, sorted(ext_set)


def load_deployed_sources(deploy_path: Path | None = None) -> set[str]:
    path = deploy_path if deploy_path is not None else DEPLOY
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {f["source"] for f in data.get("files", [])}
    except Exception:
        return set()


def scan_staging(
    stage_dir: Path | None = None,
    *,
    deploy_path: Path | None = None,
) -> list[ModEntry]:
    """Escanea staging (Vortex u otra carpeta local compatible). Solo lectura."""
    stage = stage_dir if stage_dir is not None else STAGE
    deployed = load_deployed_sources(deploy_path)
    rows: list[ModEntry] = []
    if stage is None or not stage.exists():
        return rows
    for d in sorted(stage.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir():
            continue
        paks = sorted(p.name for p in d.rglob("*.pak"))
        payload_files, payload_exts = collect_payload(d)
        name = short_name(d.name)
        chars = classify(d.name + " " + " ".join(paks) + " " + " ".join(payload_exts))
        rows.append(
            ModEntry(
                folder=d.name,
                name=name,
                characters=chars,
                character_main=chars[0],
                paks=paks,
                multi=len(paks) > 1,
                on_disk=d.name in deployed,
                stage_path=str(d),
                nexus_id=nexus_id_from_folder(d.name),
                usar=d.name in deployed,
                pak_elegido=paks[0] if len(paks) == 1 else "",
                source_kind="STAGING_VORTEX",
                # Identidad en Biblioteca siempre; instalabilidad la decide el investigador
                installable_unit=True,
                payload_files=payload_files,
                payload_exts=payload_exts,
            )
        )
    return rows
