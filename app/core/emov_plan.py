# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S42 — planificación EMOV FF7R (sin Apply PAK).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .apply import ApplyPlan
from .apply_confirm import plan_has_apply_work
from .hash_cache import sha256_file
from .inventory import ModEntry
from .multi_destination import resolve_ff7r_emov, game_path_for_destination


def game_root_from_mods_dir(mods_dest: Path) -> Path | None:
    p = mods_dest.resolve()
    for _ in range(10):
        if (p / "End" / "Content" / "GameContents" / "Movie").is_dir():
            return p
        if p.parent == p:
            return None
        p = p.parent
    return None
from .path_safety import check_fs_path, check_relative_path


@dataclass
class EmovReplaceOp:
    mod_folder: str
    mod_name: str
    staging_rel: str
    game_rel: str
    source: Path
    destination: Path
    vanilla_sha256: str
    vanilla_size: int
    requires_overwrite_confirm: bool = True


@dataclass
class EmovPlan:
    to_replace: list[EmovReplaceOp] = field(default_factory=list)
    to_restore: list[str] = field(default_factory=list)  # game_rel gestionados
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return bool(self.to_replace or self.to_restore)


def discover_emov_files(stage_root: Path) -> list[str]:
    if not stage_root.is_dir():
        return []
    out: list[str] = []
    for p in stage_root.rglob("*.emov"):
        if not p.is_file():
            continue
        try:
            out.append(p.relative_to(stage_root).as_posix())
        except ValueError:
            continue
    return sorted(out)


def plan_ff7r_emov_replace(
    mods: list[ModEntry],
    *,
    game_root: Path,
    adapter_id: str,
    managed_game_rels: set[str] | None = None,
) -> EmovPlan:
    """Solo FF7R + regla Movie; destino debe existir (vanilla) para reemplazo."""
    plan = EmovPlan()
    if adapter_id != "ue4_paks_mods":
        return plan
    if not game_root.is_dir():
        plan.errors.append("game_root no accesible")
        return plan

    dest_map: dict[str, EmovReplaceOp] = {}
    managed = managed_game_rels or set()

    for m in mods:
        if not m.usar:
            continue
        root = Path(m.stage_path) if m.stage_path else Path()
        for staging_rel in discover_emov_files(root):
            for iss in check_relative_path(staging_rel):
                if iss.confirmed:
                    plan.errors.append(f"{m.folder}: {iss.message}")
                    continue
            resolved = resolve_ff7r_emov(staging_rel)
            if resolved is None:
                plan.errors.append(
                    f"{m.folder}: ruta .emov ambigua o no admitida: {staging_rel}"
                )
                continue
            src = root / staging_rel
            for iss in check_fs_path(src, root=root):
                if iss.confirmed:
                    plan.errors.append(f"{m.folder}: origen inseguro: {iss.message}")
                    continue
            if not src.is_file():
                plan.errors.append(f"{m.folder}: origen ausente: {staging_rel}")
                continue
            dst = game_path_for_destination(game_root, resolved)
            for iss in check_fs_path(dst, root=game_root):
                if iss.confirmed:
                    plan.errors.append(f"{m.folder}: destino inseguro: {iss.message}")
                    continue
            if not dst.is_file():
                plan.errors.append(
                    f"{m.folder}: destino vanilla ausente (no se inventa): {resolved.game_rel}"
                )
                continue
            try:
                vhash = sha256_file(dst)
                vsize = dst.stat().st_size
            except OSError as e:
                plan.errors.append(f"{m.folder}: no se pudo leer vanilla: {e}")
                continue

            op = EmovReplaceOp(
                mod_folder=m.folder,
                mod_name=m.name,
                staging_rel=resolved.staging_rel,
                game_rel=resolved.game_rel,
                source=src,
                destination=dst,
                vanilla_sha256=vhash,
                vanilla_size=vsize,
            )
            prev = dest_map.get(resolved.game_rel)
            if prev is not None and prev.mod_folder != m.folder:
                plan.conflicts.append(
                    f"Conflicto clip {resolved.game_rel}: "
                    f"{prev.mod_folder} vs {m.folder}"
                )
                continue
            dest_map[resolved.game_rel] = op

    plan.to_replace = list(dest_map.values())
    return plan


def coordinated_apply_blocked(
    pak_plan: ApplyPlan | None, emov_plan: EmovPlan | None
) -> tuple[bool, list[str]]:
    """True = bloqueado (mezcla PAK+EMOV sin transacción única)."""
    pak_work = pak_plan is not None and plan_has_apply_work(pak_plan)
    emov_work = emov_plan is not None and emov_plan.has_work
    if pak_work and emov_work:
        return True, [
            "Operación mixta PAK + EMOV bloqueada: requiere transacción coordinada "
            "(S42 — no implementada en Apply unificado)."
        ]
    if emov_plan and emov_plan.conflicts:
        return True, list(emov_plan.conflicts)
    if emov_plan and emov_plan.errors:
        return True, emov_plan.errors[:20]
    return False, []


def library_emov_hints(
    mod: ModEntry, *, game_root: Path | None, adapter_id: str
) -> list[str]:
    lines: list[str] = []
    root = Path(mod.stage_path) if mod.stage_path else Path()
    emovs = discover_emov_files(root)
    if not emovs:
        return lines
    lines.append("Formato: EMOV (cinemática)")
    lines.append("Destino: End/Content/GameContents/Movie/<ruta relativa>")
    lines.append("Sustituye archivo vanilla existente (backup obligatorio)")
    lines.append("Compatibilidad en juego: pendiente de validar (S41)")
    if adapter_id != "ue4_paks_mods":
        lines.append("Regla EMOV: solo adaptador ue4_paks_mods / FF7 Remake")
        return lines
    if game_root and game_root.is_dir():
        preview = plan_ff7r_emov_replace([mod], game_root=game_root, adapter_id=adapter_id)
        if preview.to_replace:
            lines.append(f"Preparado (sandbox/plan): {len(preview.to_replace)} clip(s)")
        if preview.errors:
            lines.append(f"Bloqueos: {preview.errors[0][:80]}")
        if preview.conflicts:
            lines.append(f"Conflictos: {preview.conflicts[0][:80]}")
    return lines
