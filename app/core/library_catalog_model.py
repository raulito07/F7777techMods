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

S46 — modelo visual genérico de mod para Biblioteca (sin acoplar a un juego).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .inventory import ModEntry
from .library_status import ModStatusView, status_badges_text

TAG_FILTER_ALL = "TODAS"


@dataclass(frozen=True)
class ModCapabilities:
    can_toggle_plan: bool = True
    can_pick_components: bool = False
    can_simulate: bool = True
    can_review_structure: bool = True


@dataclass
class CatalogModItem:
    game_id: str
    mod_id: str
    display_name: str
    preview_path: str
    tags: list[str]
    category: str
    source: str
    state_label: str
    state_tag: str
    plan_active: bool
    on_disk: bool
    capabilities: ModCapabilities = field(default_factory=ModCapabilities)
    warnings: list[str] = field(default_factory=list)
    status_flags_text: str = ""


def tags_for_mod(m: ModEntry) -> list[str]:
    """Etiquetas extensibles; no asume PAK ni personajes FF7."""
    out: list[str] = []
    cat = (m.category or "").strip()
    if cat:
        out.append(cat)
    for t in m.characters or []:
        s = str(t).strip()
        if s and s.upper() != "OTROS":
            out.append(s)
    sk = (getattr(m, "source_kind", "") or "STAGING").upper()
    if "WORK" in sk:
        out.append("WORK")
    else:
        out.append("STAGING")
    if getattr(m, "archived", False):
        out.append("ARCHIVADO")
    if m.multi:
        out.append("MULTI_COMPONENTE")
    payload = getattr(m, "payload_files", None) or []
    payload_exts = getattr(m, "payload_exts", None) or []
    if m.paks or payload:
        out.append("CON_ARCHIVOS")
    else:
        out.append("SIN_ARCHIVOS")
    # S49 — identidad aunque el formato no sea instalable F7777
    if not m.paks and payload_exts:
        known_install = {".pak", ".utoc", ".ucas"}
        if not any(e in known_install for e in payload_exts):
            out.append("FORMATO_NO_INSTALABLE")
    # dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def mod_matches_tag(m: ModEntry, tag: str) -> bool:
    if not tag or tag == TAG_FILTER_ALL:
        return True
    want = tag.casefold()
    return any(t.casefold() == want for t in tags_for_mod(m))


def collect_tags_from_mods(mods: list[ModEntry]) -> list[str]:
    bag: set[str] = set()
    for m in mods:
        bag.update(tags_for_mod(m))
    return sorted(bag, key=lambda s: s.casefold())


def build_catalog_item(
    m: ModEntry,
    *,
    game_id: str,
    status: ModStatusView,
    state_tag: str,
    state_label: str,
    warnings: list[str] | None = None,
) -> CatalogModItem:
    preview = (getattr(m, "thumb_path", "") or "").strip()
    src = (getattr(m, "source_kind", "") or "STAGING").upper()
    if "WORK" in src:
        source = "WORK"
    elif "VORTEX" in src or src == "STAGING":
        source = "STAGING"
    else:
        source = src or "DESCONOCIDO"
    caps = ModCapabilities(
        can_toggle_plan=True,
        can_pick_components=bool(m.multi),
        can_simulate=True,
        can_review_structure=True,
    )
    return CatalogModItem(
        game_id=game_id,
        mod_id=m.folder,
        display_name=m.nexus_mod_name or m.name,
        preview_path=preview,
        tags=tags_for_mod(m),
        category=(m.category or "").strip() or "—",
        source=source,
        state_label=state_label,
        state_tag=state_tag,
        plan_active=bool(m.usar),
        on_disk=bool(m.on_disk),
        capabilities=caps,
        warnings=list(warnings or []),
        status_flags_text=status_badges_text(status),
    )


def build_catalog_map(
    mods: list[ModEntry],
    *,
    game_id: str,
    status_by_folder: dict[str, ModStatusView],
    visual_by_folder: dict[str, tuple[str, str]],
) -> dict[str, CatalogModItem]:
    out: dict[str, CatalogModItem] = {}
    for m in mods:
        st = status_by_folder.get(m.folder)
        if st is None:
            from .library_status import compute_mod_status

            st = compute_mod_status(m)
        tag, lab = visual_by_folder.get(m.folder, ("off", st.row_label))
        out[m.folder] = build_catalog_item(
            m,
            game_id=game_id,
            status=st,
            state_tag=tag,
            state_label=lab,
        )
    return out
