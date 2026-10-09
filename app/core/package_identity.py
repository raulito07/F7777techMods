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

S38 — identidad estable: PAQUETE ≠ MOD ≠ ARCHIVO.
Expande colecciones independientes a entradas de Biblioteca individuales.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .component_selection import (
    INDEPENDIENTES,
    Certainty,
    classify_components,
)
from .inventory import ModEntry, classify, short_name

SEP = "::comp::"


def stable_component_id(package_folder: str, pak_filename: str) -> str:
    """Identidad estable por paquete + archivo (no por posición ni etiqueta UI)."""
    key = f"{package_folder}\0{pak_filename}".encode("utf-8", errors="replace")
    digest = hashlib.sha256(key).hexdigest()[:12]
    stem = re.sub(r"[^\w\-]+", "_", Path(pak_filename).stem)[:48].strip("_") or "pak"
    return f"{package_folder}{SEP}{stem}__{digest}"


def package_folder_of(mod_id: str) -> str:
    if SEP in mod_id:
        return mod_id.split(SEP, 1)[0]
    return mod_id


def is_component_id(mod_id: str) -> bool:
    return SEP in mod_id


def _display_name(pak: str, package_name: str) -> str:
    stem = Path(pak).stem
    # Etiqueta legible corta; paquete queda como procedencia
    pretty = re.sub(r"[_\-]+", " ", stem).strip()
    if len(pretty) > 56:
        pretty = pretty[:53] + "…"
    return pretty or package_name


def _tag_certainty(chars: list[str], pak: str) -> str:
    """Heurística de etiqueta; nunca certeza absoluta solo por nombre."""
    low = pak.lower()
    hits = [c for c in chars if c != "OTROS"]
    if not hits:
        return "AMBIGUOUS"
    # Un token de personaje explícito en el nombre → heurística fuerte
    token_map = {
        "CLOUD": "cloud",
        "TIFA": "tifa",
        "AERITH": "aerith",
        "SHIVA": "shiva",
        "BARRET": "barret",
        "YUFFIE": "yuffie",
        "SEPHIROTH": "sephiroth",
        "SCARLET": "scarlet",
    }
    for label, tok in token_map.items():
        if label in hits and tok in low:
            return "HEURISTIC"
    return "AMBIGUOUS"


def expand_independent_packages(mods: list[ModEntry]) -> list[ModEntry]:
    """
    Si un paquete es INDEPENDIENTES con certeza suficiente, sustituye la carpeta
    por una entrada por .pak. El paquete NO se lista como mod instalable extra.
    Variantes excluyentes / ambiguas se dejan como una sola entrada.
    """
    out: list[ModEntry] = []
    for m in mods:
        # Ya es componente expandido
        if is_component_id(m.folder) or getattr(m, "package_folder", ""):
            out.append(m)
            continue
        if not m.multi or len(m.paks) < 2:
            out.append(m)
            continue
        rep = classify_components(m)
        m.selection_mode = rep.mode
        if rep.mode != INDEPENDIENTES or rep.certainty == Certainty.AMBIGUOUS:
            out.append(m)
            continue
        if rep.certainty not in (Certainty.CONFIRMED, Certainty.HEURISTIC):
            out.append(m)
            continue

        siblings = [stable_component_id(m.folder, p) for p in m.paks]
        for pak in m.paks:
            cid = stable_component_id(m.folder, pak)
            chars = classify(pak + " " + m.name)
            tag_c = _tag_certainty(chars, pak)
            companions = [s for s in siblings if s != cid]
            child = ModEntry(
                folder=cid,
                name=_display_name(pak, m.name),
                characters=chars,
                character_main=chars[0],
                paks=[pak],
                multi=False,
                on_disk=m.on_disk,
                stage_path=m.stage_path,
                nexus_id=m.nexus_id,
                description=(
                    f"Origen paquete: {short_name(m.folder)} ({m.folder})\n"
                    f"Componente: {pak}\n"
                    f"Etiquetas: {', '.join(chars)} ({tag_c})\n"
                    f"Acompañamientos opcionales del mismo paquete: "
                    f"{len(companions)}"
                ),
                category=m.category or "Colección / componente",
                slots=list(m.slots),
                usar=False,
                pak_elegido=pak,
                paks_elegidos=[pak],
                selection_mode=INDEPENDIENTES,
                picture_url=m.picture_url,
                thumb_path=m.thumb_path,
                author=m.author,
                nexus_mod_name=m.nexus_mod_name,
                source_kind=m.source_kind,
                mod_id=cid,
                archive_path=m.archive_path,
                archive_content_sha256=m.archive_content_sha256,
                archive_zip_sha256=m.archive_zip_sha256,
                work_extracted=m.work_extracted,
                archived=m.archived,
                package_folder=m.folder,
                package_name=short_name(m.folder),
                companion_ids=companions,
                tag_certainty=tag_c,
                installable_unit=True,
            )
            out.append(child)
    return out


def migrate_package_loadout(
    mods: list[ModEntry],
    saved: dict[str, dict],
) -> None:
    """Aplica loadout de carpeta S37 (paks_elegidos) a componentes S38."""
    by_id = {m.folder: m for m in mods}
    # 1) claves directas de componentes
    for m in mods:
        if m.folder in saved:
            ent = saved[m.folder]
            m.usar = bool(ent.get("usar", m.usar))
            pak = ent.get("pak_elegido") or ""
            many = ent.get("paks_elegidos")
            if isinstance(many, list) and many:
                m.paks_elegidos = [str(x) for x in many]
                m.pak_elegido = m.paks_elegidos[0]
            elif pak:
                m.pak_elegido = pak
                m.paks_elegidos = [pak]
    # 2) migración desde carpeta paquete → componentes
    for pkg, ent in saved.items():
        if is_component_id(pkg):
            continue
        if not isinstance(ent, dict):
            continue
        many = ent.get("paks_elegidos")
        single = ent.get("pak_elegido") or ""
        selected: list[str] = []
        if isinstance(many, list) and many:
            selected = [str(x) for x in many]
        elif single:
            selected = [str(single)]
        if not selected and not ent.get("usar"):
            continue
        # Si usar=True en paquete sin lista, no activar todos automáticamente
        for pak in selected:
            cid = stable_component_id(pkg, pak)
            child = by_id.get(cid)
            if child is None:
                continue
            child.usar = True if ent.get("usar", True) else child.usar
            child.pak_elegido = pak
            child.paks_elegidos = [pak]
