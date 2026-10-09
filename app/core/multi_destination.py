# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S42 — destinos por tipo de componente (PAK vs Movie .emov FF7R).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DestinationKind(str, Enum):
    PAK_MODS = "pak_mods"
    FF7R_MOVIE_EMOV = "ff7r_movie_emov"
    UNSUPPORTED = "unsupported"


# Relativo a game_root (FF7 Remake)
FF7R_MOVIE_PREFIX = Path("End/Content/GameContents/Movie")
FF7R_PAK_MODS_PREFIX = Path("End/Content/Paks/~mods")

_SCENE_DIR = re.compile(r"^\d{3}-[A-Za-z0-9][A-Za-z0-9_-]*$")
_EMOV_NAME = re.compile(r"^MV_[A-Za-z0-9_\-]+\.emov$", re.I)


@dataclass(frozen=True)
class ResolvedDestination:
    kind: DestinationKind
    game_rel: str  # posix, relativo a game_root
    staging_rel: str  # posix, relativo a mod stage root


def _posix(p: Path) -> str:
    return p.as_posix().replace("\\", "/")


def validate_ff7r_movie_staging_rel(staging_rel: str) -> tuple[bool, str]:
    """Valida ruta relativa dentro del mod (sin inventar destino)."""
    rel = staging_rel.replace("\\", "/").strip("/")
    if not rel.lower().endswith(".emov"):
        return False, "no es .emov"
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False, "componente de ruta inválido"
    if len(parts) < 3:
        return False, "profundidad insuficiente (escena/MV_/archivo)"
    if not _SCENE_DIR.match(parts[0]):
        return False, f"carpeta escena no reconocida: {parts[0]}"
    if not any(seg.startswith("MV_") for seg in parts[1:-1]):
        return False, "falta carpeta MV_* intermedia"
    if not _EMOV_NAME.match(parts[-1]):
        return False, f"nombre .emov no reconocido: {parts[-1]}"
    return True, ""


def resolve_ff7r_emov(staging_rel: str) -> ResolvedDestination | None:
    ok, reason = validate_ff7r_movie_staging_rel(staging_rel)
    if not ok:
        return None
    rel = staging_rel.replace("\\", "/").strip("/")
    game_rel = _posix(FF7R_MOVIE_PREFIX / rel)
    return ResolvedDestination(
        kind=DestinationKind.FF7R_MOVIE_EMOV,
        game_rel=game_rel,
        staging_rel=rel,
    )


def game_path_for_destination(game_root: Path, dest: ResolvedDestination) -> Path:
    return game_root.joinpath(*Path(dest.game_rel).parts)
