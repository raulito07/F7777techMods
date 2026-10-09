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

S03 — motor universal de conflictos de archivos y resolución por prioridad.

Separado de las heurísticas semánticas (conflicts.py / adaptador).
No analiza el interior de .pak/.ba2/.bsa: solo rutas/nombres externos.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .adapters import get_adapter
from .content_classify import ContentKind, classify_file
from .hash_cache import HashCache
from .inventory import ModEntry

CASE_INSENSITIVE = os.name == "nt"
PACKAGED_SUFFIXES = {".pak", ".ba2", ".bsa", ".archive", ".bun", ".far"}
SKIP_NAMES = {"thumbs.db", "desktop.ini"}
KEEP_NAMES = {"vortex.deployment.json", "_manual_loadout.json"}


class ConflictKind(str, Enum):
    DUPLICATE_IDENTICAL = "DUPLICADO IDÉNTICO"
    FILE_CONFLICT = "CONFLICTO DE ARCHIVOS"
    FOREIGN_FILE = "CONFLICTO CON ARCHIVO AJENO"
    VARIANT = "CONFLICTO DE VARIANTES"
    SEMANTIC = "CONFLICTO SEMÁNTICO"
    DOC_COLLISION = "COLISION DOCUMENTACION"
    UNKNOWN_PENDING = "PENDIENTE CLASIFICACION"
    PAK_INTERNAL = "PAK INTERNO NO ANALIZADO"


def _norm_rel(rel: str) -> str:
    s = rel.replace("\\", "/").strip("/")
    while "//" in s:
        s = s.replace("//", "/")
    return s


def dest_key(rel: str) -> str:
    n = _norm_rel(rel)
    return n.casefold() if CASE_INSENSITIVE else n


@dataclass
class FileOffer:
    dest_rel: str
    source: Path
    mod_folder: str
    mod_name: str
    priority: int | None  # None = sin prioridad explícita
    sha256: str = ""
    packaged_external: bool = False


@dataclass
class FileConflict:
    dest_rel: str
    dest_key: str
    kind: ConflictKind
    offers: list[FileOffer]
    winner_folder: str | None = None
    displaced_folders: list[str] = field(default_factory=list)
    resolved: bool = False
    note: str = ""
    hashes: dict[str, str] = field(default_factory=dict)  # folder -> sha


@dataclass
class ConflictSettings:
    priorities: dict[str, int] = field(default_factory=dict)
    resolutions: dict[str, dict] = field(default_factory=dict)
    hash_cache_path: Path | None = None
    adapter_id: str = "generic_folder"
    managed_keys: dict[str, str] = field(default_factory=dict)  # key -> canon rel
    disk_index: dict[str, str] = field(default_factory=dict)  # key -> canon rel on disk
    mods_root: Path | None = None
    stage_root: Path | None = None
    install_mode: str = "COPY"  # COPY | HARDLINK | AUTO (S09)
    destination_verified: bool = True  # S10: False → Apply bloqueado
    game_id: str = ""  # S15: requerido para validar WORK_LIBRARY
    work_root: Path | None = None  # S15: raíz biblioteca de trabajo


@dataclass
class ConflictAnalysis:
    """Resultado del análisis (archivos + variantes). Semántica aparte."""

    offers_by_dest: dict[str, list[FileOffer]]
    file_conflicts: list[FileConflict]
    variant_issues: list[FileConflict]
    desired_offers: dict[str, FileOffer]  # dest_rel canónico → oferta ganadora
    errors: list[str]
    unresolved: int
    hash_cache: HashCache


def _priority_of(folder: str, settings: ConflictSettings) -> int | None:
    if folder not in settings.priorities:
        return None
    return int(settings.priorities[folder])


def collect_offers(
    mods: list[ModEntry],
    settings: ConflictSettings,
) -> tuple[dict[str, list[FileOffer]], list[FileConflict], list[str]]:
    """Recoge ofertas instalables por destino; variantes sin elegir → issues.

    S08: ue4_paks_mods solo ofrece .pak clasificados como INSTALABLE.
    Documentación y desconocidos no entran en el plan de copia.
    """
    by_key: dict[str, list[FileOffer]] = defaultdict(list)
    variants: list[FileConflict] = []
    errors: list[str] = []
    adapter_id = settings.adapter_id or "generic_folder"
    ad = get_adapter(adapter_id)

    for m in mods:
        if not m.usar:
            continue
        src_dir = Path(m.stage_path)
        if not src_dir.exists():
            errors.append(f"No está en staging: {m.name}")
            continue

        pak_list = [p.name for p in src_dir.rglob("*.pak")]
        from .component_selection import (
            VARIANTES_EXCLUYENTES,
            classify_components,
            selected_paks,
            selection_pending,
        )

        rep = classify_components(m)
        m.selection_mode = rep.mode
        selected = selected_paks(m)
        multi = m.multi or len(pak_list) > 1
        if multi and selection_pending(m, rep):
            variants.append(
                FileConflict(
                    dest_rel="(componentes)",
                    dest_key=f"variant::{m.folder}",
                    kind=ConflictKind.VARIANT,
                    offers=[],
                    resolved=False,
                    note=(
                        f"{m.name}: falta seleccionar componente(s) "
                        f"[{rep.mode}]"
                    ),
                )
            )
            errors.append(f"{m.name}: falta seleccionar componente(s) .pak")
            continue
        # Resolver nombres canónicos de staging
        selected_canon: list[str] = []
        for ch in selected:
            match = next((p for p in pak_list if p.lower() == ch.lower()), None)
            if not match:
                errors.append(f"{m.name}: '{ch}' no existe. Opciones: {pak_list}")
                continue
            selected_canon.append(match)
        if multi and not selected_canon:
            errors.append(f"{m.name}: selección de componentes vacía")
            continue
        if not multi and pak_list and not selected_canon:
            selected_canon = [pak_list[0]]
        chosen_set = {x.lower() for x in selected_canon}
        # Compat: chosen_pak = primero (clasificador legacy)
        chosen = selected_canon[0] if selected_canon else None

        prio = _priority_of(m.folder, settings)

        for f in src_dir.rglob("*"):
            if not f.is_file() or f.name.lower() in SKIP_NAMES:
                continue
            if f.name.lower().startswith("vortex"):
                continue

            # Para multi-selección, pedir clasificación con este .pak como elegido
            # (classify_file marca los no elegidos como VARIANT_ALT).
            per_chosen = f.name if f.suffix.lower() == ".pak" and f.name.lower() in chosen_set else (chosen or None)
            fc = classify_file(
                f,
                src_dir,
                adapter_id=adapter_id,
                chosen_pak=per_chosen,
                pak_names=pak_list,
            )
            if f.suffix.lower() == ".pak" and pak_list:
                if f.name.lower() not in chosen_set:
                    continue
                # Forzar instalable si el usuario lo seleccionó explícitamente
                if fc.kind == ContentKind.VARIANT_ALT:
                    fc = type(fc)(
                        fc.path,
                        fc.rel,
                        ContentKind.INSTALLABLE,
                        dest_rel=f.name,
                        note="componente seleccionado",
                    )
            if fc.kind != ContentKind.INSTALLABLE:
                continue
            dest_rel = fc.dest_rel or (
                _norm_rel(f.name)
                if f.suffix.lower() == ".pak"
                else _norm_rel(f.relative_to(src_dir).as_posix())
            )
            if f.suffix.lower() == ".pak":
                dest_rel = _norm_rel(f.name)

            if Path(dest_rel).name.lower() in {k.lower() for k in KEEP_NAMES}:
                errors.append(f"{m.name}: destino reservado no instalable ({dest_rel})")
                continue

            packaged = f.suffix.lower() in PACKAGED_SUFFIXES
            offer = FileOffer(
                dest_rel=dest_rel,
                source=f,
                mod_folder=m.folder,
                mod_name=m.name,
                priority=prio,
                packaged_external=packaged,
            )
            by_key[dest_key(dest_rel)].append(offer)

    return by_key, variants, errors


def _hash_offers(offers: list[FileOffer], cache: HashCache) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for o in offers:
        dig = cache.get(o.source) or ""
        o.sha256 = dig
        hashes[o.mod_folder] = dig
    return hashes


def _pick_by_priority(
    offers: list[FileOffer],
) -> tuple[FileOffer | None, str]:
    """Devuelve (ganador, motivo). None si no resoluble por prioridad."""
    with_prio = [o for o in offers if o.priority is not None]
    if len(with_prio) != len(offers):
        # algún mod sin prioridad → no auto-resolver por prioridad
        if not with_prio:
            return None, "Sin prioridad explícita en los mods implicados."
        return None, "Hay mods sin prioridad; el conflicto permanece pendiente."
    best = max(o.priority for o in with_prio)  # type: ignore[arg-type]
    winners = [o for o in with_prio if o.priority == best]
    if len(winners) != 1:
        return None, f"Empate de prioridad ({best}); no se elige ganador."
    return winners[0], f"Prioridad {best} prevalece."


def analyze_file_conflicts(
    mods: list[ModEntry],
    settings: ConflictSettings,
) -> ConflictAnalysis:
    cache = HashCache(settings.hash_cache_path)
    by_key, variants, errors = collect_offers(mods, settings)
    file_conflicts: list[FileConflict] = []
    desired: dict[str, FileOffer] = {}

    for dkey, offers in sorted(by_key.items(), key=lambda x: x[0]):
        # Canonizar dest_rel: preferir el de la primera oferta
        # (casefold puede unificar Cloud.pak / cloud.pak)
        canonical_rel = offers[0].dest_rel
        unique_folders = list(dict.fromkeys(o.mod_folder for o in offers))

        # Conflicto con archivo ajeno
        foreign = False
        if dkey in settings.disk_index and dkey not in settings.managed_keys:
            foreign = True

        if len(unique_folders) == 1 and not foreign:
            # Sin colisión entre mods
            desired[canonical_rel] = offers[0]
            continue

        if len(unique_folders) == 1 and foreign:
            o = offers[0]
            fc = FileConflict(
                dest_rel=settings.disk_index.get(dkey, canonical_rel),
                dest_key=dkey,
                kind=ConflictKind.FOREIGN_FILE,
                offers=offers,
                resolved=False,
                note=(
                    "El destino ya tiene un archivo no gestionado. "
                    "La prioridad no puede sobrescribirlo."
                ),
            )
            if o.packaged_external:
                fc.note += " (contenedor externo; no se analizó el interior)."
            file_conflicts.append(fc)
            errors.append(
                f"CONFLICTO CON ARCHIVO AJENO: '{fc.dest_rel}' ← {o.mod_name}"
            )
            continue

        # Varios mods → hashear (solo en colisión)
        hashes = _hash_offers(offers, cache)
        unique_hashes = {h for h in hashes.values() if h}
        if len(unique_hashes) == 1:
            kind = ConflictKind.DUPLICATE_IDENTICAL
        else:
            kind = ConflictKind.FILE_CONFLICT

        fc = FileConflict(
            dest_rel=canonical_rel,
            dest_key=dkey,
            kind=kind,
            offers=offers,
            hashes=hashes,
            note="",
        )
        if any(o.packaged_external for o in offers):
            fc.note = (
                "Conflicto de ruta/nombre externo de contenedor "
                "(.pak/.ba2/.bsa…). No se analizó el contenido interno."
            )

        # Resolución
        winner: FileOffer | None = None
        reason = ""

        # 1) Manual
        res = settings.resolutions.get(dkey)
        if res and res.get("winner_folder"):
            wf = res["winner_folder"]
            winner = next((o for o in offers if o.mod_folder == wf), None)
            if winner:
                reason = f"Resolución manual → {winner.mod_name}"
            else:
                reason = "Resolución manual obsoleta (mod no activo)."

        # 2) Duplicado idéntico → cualquier oferta (preferir mayor prioridad si hay)
        if winner is None and kind == ConflictKind.DUPLICATE_IDENTICAL:
            picked, reason = _pick_by_priority(offers)
            if picked:
                winner = picked
            else:
                # idénticos: seguro elegir el primero sin “sobrescritura” de contenido distinto
                winner = offers[0]
                reason = "Contenido idéntico (SHA-256); se conserva una copia."

        # 3) Prioridad (solo FILE_CONFLICT)
        if winner is None and kind == ConflictKind.FILE_CONFLICT:
            picked, reason = _pick_by_priority(offers)
            winner = picked

        if winner is None:
            fc.resolved = False
            fc.note = (fc.note + " " + reason).strip()
            if not reason:
                fc.note = (fc.note + " Conflicto sin resolución.").strip()
            file_conflicts.append(fc)
            names = " vs ".join(
                f"{o.mod_name}[p={o.priority}]" for o in offers
            )
            errors.append(
                f"{kind.value}: '{canonical_rel}' — {names}. {fc.note}"
            )
            continue

        # Foreign + multi-mod shouldn't happen above; still guard
        if foreign:
            fc.kind = ConflictKind.FOREIGN_FILE
            fc.resolved = False
            fc.note = "No se puede resolver por prioridad: archivo ajeno en destino."
            file_conflicts.append(fc)
            errors.append(fc.note + f" ({canonical_rel})")
            continue

        fc.winner_folder = winner.mod_folder
        fc.displaced_folders = [
            o.mod_folder for o in offers if o.mod_folder != winner.mod_folder
        ]
        fc.resolved = True
        fc.note = (fc.note + " " + reason).strip()
        file_conflicts.append(fc)
        desired[winner.dest_rel] = winner
        # Unificar clave case: si otras ofertas usaban otro casing, desired usa winner.dest_rel

    # Destinos únicos sin conflicto ya añadidos; ofertas solitarias
    # (ya cubierto en el bucle)

    unresolved = sum(1 for c in file_conflicts if not c.resolved) + sum(
        1 for v in variants if not v.resolved
    )
    try:
        cache.save()
    except Exception:
        pass

    return ConflictAnalysis(
        offers_by_dest=dict(by_key),
        file_conflicts=file_conflicts,
        variant_issues=variants,
        desired_offers=desired,
        errors=errors,
        unresolved=unresolved,
        hash_cache=cache,
    )


def semantic_enabled(adapter_id: str) -> bool:
    return bool(get_adapter(adapter_id).semantic_slots)
