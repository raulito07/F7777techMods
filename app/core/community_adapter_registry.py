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

S50 — registro de adaptadores comunitarios + conflictos.
Los adaptadores oficiales (app.core.adapters) no se modifican.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .adapters import ADAPTERS, KNOWN_ADAPTER_IDS, get_adapter
from .community_adapter_api import CommunityAdapterSpec, RecognitionLayer
from .community_adapter_loader import LoadResult, load_community_adapters_dir
from .community_adapter_security import resolve_community_root


@dataclass
class AdapterConflict:
    kind: str
    adapter_a: str
    adapter_b: str
    detail: str


@dataclass
class CommunityRegistry:
    specs: dict[str, CommunityAdapterSpec] = field(default_factory=dict)
    load_errors: list[LoadResult] = field(default_factory=list)
    conflicts: list[AdapterConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_game_id(self, game_id: str) -> list[CommunityAdapterSpec]:
        gid = (game_id or "").strip()
        return [s for s in self.specs.values() if gid in s.game_ids]

    def get(self, adapter_id: str) -> CommunityAdapterSpec | None:
        return self.specs.get(adapter_id)


def detect_conflicts(specs: list[CommunityAdapterSpec]) -> list[AdapterConflict]:
    out: list[AdapterConflict] = []
    by_id: dict[str, CommunityAdapterSpec] = {}
    for s in specs:
        if s.adapter_id in by_id:
            out.append(
                AdapterConflict(
                    "duplicate_adapter_id",
                    s.adapter_id,
                    by_id[s.adapter_id].adapter_id,
                    "mismo adapter_id en dos documentos",
                )
            )
        by_id[s.adapter_id] = s
        # Conflicto con oficial si mismo id
        if s.adapter_id in KNOWN_ADAPTER_IDS:
            out.append(
                AdapterConflict(
                    "overrides_official_id",
                    s.adapter_id,
                    s.adapter_id,
                    "no puede reutilizar id de adaptador oficial",
                )
            )

    # Mismo game_id + mismo format id con destinos distintos
    for i, a in enumerate(specs):
        for b in specs[i + 1 :]:
            shared_games = set(a.game_ids) & set(b.game_ids)
            if not shared_games:
                continue
            a_fmts = {f.id: f for f in a.formats}
            b_fmts = {f.id: f for f in b.formats}
            for fid in set(a_fmts) & set(b_fmts):
                a_dest = {
                    d.relative_path
                    for d in a.destinations
                    if fid in d.format_ids or not d.format_ids
                }
                b_dest = {
                    d.relative_path
                    for d in b.destinations
                    if fid in d.format_ids or not d.format_ids
                }
                if a_dest and b_dest and a_dest != b_dest:
                    out.append(
                        AdapterConflict(
                            "format_destination_mismatch",
                            a.adapter_id,
                            b.adapter_id,
                            f"game(s) {sorted(shared_games)} formato '{fid}' "
                            f"destinos {sorted(a_dest)} vs {sorted(b_dest)}",
                        )
                    )
    return out


def build_community_registry(root: Path | None = None) -> CommunityRegistry:
    base = resolve_community_root(root)
    reg = CommunityRegistry()
    results = load_community_adapters_dir(base)
    accepted: list[CommunityAdapterSpec] = []
    for lr in results:
        if not lr.ok or lr.spec is None:
            reg.load_errors.append(lr)
            continue
        # Conflicto con oficial → rechazar
        if lr.spec.adapter_id in KNOWN_ADAPTER_IDS:
            lr.errors.append("id colisiona con adaptador oficial")
            reg.load_errors.append(lr)
            continue
        accepted.append(lr.spec)
        reg.warnings.extend(lr.warnings)

    conflicts = detect_conflicts(accepted)
    reg.conflicts = conflicts
    conflict_ids = {c.adapter_a for c in conflicts} | {c.adapter_b for c in conflicts}
    # Ante conflicto de id duplicado / destino, no registrar ninguno de la pareja conflictiva de destino
    # Política: registrar solo specs sin conflicto hard
    hard = {"duplicate_adapter_id", "overrides_official_id", "format_destination_mismatch"}
    blocked = set()
    for c in conflicts:
        if c.kind in hard:
            blocked.add(c.adapter_a)
            blocked.add(c.adapter_b)

    for s in accepted:
        if s.adapter_id in blocked:
            reg.warnings.append(f"adaptador '{s.adapter_id}' bloqueado por conflicto")
            continue
        reg.specs[s.adapter_id] = s
    return reg


def official_adapter_ids() -> frozenset[str]:
    return frozenset(ADAPTERS.keys())


def game_has_official_adapter(adapter_id: str) -> bool:
    return bool(adapter_id) and adapter_id in KNOWN_ADAPTER_IDS


def describe_support_gap(
    *,
    game_id: str,
    official_adapter_id: str,
    registry: CommunityRegistry | None = None,
    formats_present: list[str] | None = None,
    game_installed: bool = True,
) -> dict[str, object]:
    """Resumen para UI / contribución cuando falta soporte."""
    reg = registry or CommunityRegistry()
    community = reg.by_game_id(game_id)
    official_ok = game_has_official_adapter(official_adapter_id)
    layers = {layer.value: False for layer in RecognitionLayer}
    layers[RecognitionLayer.GAME_RECOGNIZED.value] = official_ok or bool(community)
    layers[RecognitionLayer.MOD_RECOGNIZED.value] = bool(formats_present)
    if community and formats_present:
        snap = community[0].recognition_snapshot(formats_present=formats_present)
        for k, v in snap.items():
            layers[k.value] = v
    layers[RecognitionLayer.AUTO_INSTALL_COMPATIBLE.value] = False
    if official_ok and not formats_present:
        # PAK path still via official — not decided here
        pass
    return {
        "game_id": game_id,
        "game_installed": game_installed,
        "official_adapter": official_adapter_id if official_ok else "",
        "community_adapters": [s.adapter_id for s in community],
        "recognition": layers,
        "missing_for_auto_install": [
            "instalador F7777 revisado",
            "destino verificado con pruebas",
            "aprobación de seguridad (Apply)",
        ],
        "contribution_hint": (
            "Puede aportar un JSON en community_adapters/ siguiendo "
            "GAME_ADAPTER_GUIDE.md (sin datos personales ni ejecución de código)."
        ),
    }


# Reexport get_adapter for callers that need official behavior unchanged
__all__ = [
    "CommunityRegistry",
    "AdapterConflict",
    "build_community_registry",
    "detect_conflicts",
    "describe_support_gap",
    "official_adapter_ids",
    "game_has_official_adapter",
    "get_adapter",
]
