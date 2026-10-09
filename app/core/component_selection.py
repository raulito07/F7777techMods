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

S37 — componentes de colección: independientes vs variantes excluyentes.
Varios .pak en la misma carpeta NO implican exclusión automática.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .inventory import ModEntry

INDEPENDIENTES = "INDEPENDIENTES"
VARIANTES_EXCLUYENTES = "VARIANTES_EXCLUYENTES"
GRUPOS_OBLIGATORIOS = "GRUPOS_OBLIGATORIOS"
REVISION_MANUAL = "REVISION_MANUAL"

_EXCLUSIVE_FAMILY = [
    re.compile(r"(?i)(?:^|[-_\s.])fov[-_]?\d{2,3}(?:$|[-_\s.])"),
    re.compile(r"(?i)(?:^|[-_\s.])(performance|quality)(?:$|[-_\s.])"),
    re.compile(r"(?i)(?:^|[-_\s.])([24]k)(?:$|[-_\s.])"),
    re.compile(r"(?i)(?:^|[-_\s.])(default|alternative|optional)(?:$|[-_\s.])"),
    re.compile(r"(?i)(?:^|[-_\s.])(brighter|brightest|bright)(?:$|[-_\s.])"),
]

_CHAR_TOKENS = (
    "cloud",
    "tifa",
    "aerith",
    "barret",
    "yuffie",
    "jessie",
    "shiva",
    "sephiroth",
    "scarlet",
    "roche",
    "redxiii",
    "cid",
)


class Certainty(str, Enum):
    CONFIRMED = "CONFIRMED"
    HEURISTIC = "HEURISTIC"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ComponentInfo:
    filename: str
    rel_path: str = ""
    group: str = ""
    dest_rel: str = ""
    note: str = ""


@dataclass
class SelectionReport:
    mode: str
    certainty: Certainty
    components: list[ComponentInfo] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    needs_manual_review: bool = False
    explanation: str = ""


def _chars_in_name(name: str) -> set[str]:
    low = name.lower()
    return {c for c in _CHAR_TOKENS if c in low}


def _stem_family(names: list[str]) -> bool:
    """True si los nombres parecen la misma familia con distinto sufijo de opción."""
    if len(names) < 2:
        return False
    stems = []
    for n in names:
        s = Path(n).stem.lower()
        for rx in _EXCLUSIVE_FAMILY:
            s = rx.sub("", s)
        s = re.sub(r"[-_\s]+", "", s)
        stems.append(s)
    # Si al quitar tokens de opción quedan casi iguales → familia excluyente
    base = stems[0]
    if not base:
        return False
    return all(abs(len(x) - len(base)) <= 4 and (base[:6] in x or x[:6] in base) for x in stems[1:])


def classify_components(mod: ModEntry) -> SelectionReport:
    """Clasifica relación entre .pak de un mod/colección (solo lectura)."""
    root = Path(mod.stage_path) if mod.stage_path else Path()
    paks = list(mod.paks) or (
        sorted(p.name for p in root.rglob("*.pak")) if root.is_dir() else []
    )
    comps: list[ComponentInfo] = []
    for p in paks:
        rel = p
        if root.is_dir():
            hits = list(root.rglob(p))
            if hits:
                try:
                    rel = hits[0].relative_to(root).as_posix()
                except ValueError:
                    rel = p
        comps.append(
            ComponentInfo(
                filename=p,
                rel_path=rel,
                dest_rel=p,
                group=Path(rel).parent.as_posix() if "/" in rel.replace("\\", "/") else "(raíz)",
            )
        )

    if len(paks) <= 1:
        return SelectionReport(
            mode=INDEPENDIENTES,
            certainty=Certainty.CONFIRMED,
            components=comps,
            evidence=["Un solo .pak instalable"],
            explanation="Componente único; no hay elección de variantes.",
        )

    evidence: list[str] = []
    collection_json = root / "collection.json" if root.is_dir() else None
    bundled = root / "bundled" if root.is_dir() else None
    has_collection = bool(collection_json and collection_json.is_file())
    has_bundled = bool(bundled and bundled.is_dir())
    if has_collection:
        evidence.append("collection.json presente (colección Vortex)")
        try:
            obj = json.loads(collection_json.read_text(encoding="utf-8"))
            mods_meta = obj.get("mods") or []
            if isinstance(mods_meta, list) and len(mods_meta) >= 2:
                evidence.append(f"collection.json lista {len(mods_meta)} entradas de mods")
        except Exception:
            pass
    if has_bundled:
        evidence.append("subcarpeta bundled/ con paquetes separados")

    char_sets = [_chars_in_name(p) for p in paks]
    distinct_chars = {next(iter(s)) for s in char_sets if len(s) == 1}
    if len(distinct_chars) >= 2:
        evidence.append(
            "nombres apuntan a personajes/targets distintos: "
            + ", ".join(sorted(distinct_chars))
        )

    # IoStore: si hay .utoc/.ucas junto a .pak → grupos obligatorios por stem
    iostore = False
    if root.is_dir():
        sufs = {p.suffix.lower() for p in root.rglob("*") if p.is_file()}
        if ".utoc" in sufs or ".ucas" in sufs:
            iostore = True
            evidence.append("sidecars IoStore detectados (.utoc/.ucas)")

    exclusive_hint = _stem_family(paks) and any(
        rx.search(n) for n in paks for rx in _EXCLUSIVE_FAMILY
    )
    if exclusive_hint:
        evidence.append("patrón de nombre tipo FOV/calidad/opción (heurística)")

    # Reglas (certeza)
    if iostore:
        return SelectionReport(
            mode=GRUPOS_OBLIGATORIOS,
            certainty=Certainty.CONFIRMED,
            components=comps,
            evidence=evidence,
            explanation="Componentes IoStore (.pak+.utoc+.ucas) van juntos por stem.",
        )

    if has_collection or has_bundled or len(distinct_chars) >= 2:
        return SelectionReport(
            mode=INDEPENDIENTES,
            certainty=Certainty.CONFIRMED if (has_collection or has_bundled) else Certainty.HEURISTIC,
            components=comps,
            evidence=evidence,
            explanation=(
                "Colección / paquetes distintos: cada .pak puede activarse por separado. "
                "No se asume incompatibilidad por compartir carpeta."
            ),
        )

    if exclusive_hint:
        return SelectionReport(
            mode=VARIANTES_EXCLUYENTES,
            certainty=Certainty.HEURISTIC,
            components=comps,
            evidence=evidence,
            needs_manual_review=True,
            explanation=(
                "Indicio de variantes excluyentes por nombre. "
                "Confirma UNA opción; no es prueba absoluta de incompatibilidad."
            ),
        )

    return SelectionReport(
        mode=REVISION_MANUAL,
        certainty=Certainty.AMBIGUOUS,
        components=comps,
        evidence=evidence or ["varios .pak sin evidencia de exclusión"],
        needs_manual_review=True,
        explanation=(
            "Relación ambigua. Selecciona explícitamente qué componentes instalar; "
            "no se fuerza exclusión automática."
        ),
    )


def selected_paks(mod: ModEntry) -> list[str]:
    """Lista de .pak que el plan debe ofrecer (orden estable)."""
    chosen = [p for p in (getattr(mod, "paks_elegidos", None) or []) if p]
    if chosen:
        return list(chosen)
    if mod.pak_elegido:
        return [mod.pak_elegido]
    if not mod.multi and mod.paks:
        return list(mod.paks[:1])
    return []


def selection_pending(mod: ModEntry, report: SelectionReport | None = None) -> bool:
    if not mod.usar:
        return False
    if len(mod.paks) <= 1:
        return False
    rep = report or classify_components(mod)
    sel = selected_paks(mod)
    if rep.mode == VARIANTES_EXCLUYENTES:
        return len(sel) != 1
    if rep.mode in (INDEPENDIENTES, REVISION_MANUAL, GRUPOS_OBLIGATORIOS):
        return len(sel) < 1
    return len(sel) < 1


def set_selected_paks(mod: ModEntry, names: list[str], *, exclusive: bool = False) -> None:
    clean = []
    seen = set()
    allowed = {p.lower(): p for p in mod.paks}
    for n in names:
        key = n.lower()
        if key not in allowed or key in seen:
            continue
        clean.append(allowed[key])
        seen.add(key)
    if exclusive and clean:
        clean = clean[:1]
    mod.paks_elegidos = clean
    mod.pak_elegido = clean[0] if clean else ""
