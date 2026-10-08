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

S10 — estados visuales por mod/juego (solo lectura de rutas).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .games import GamePaths, GameRecord
from .inventory import ModEntry


def lifecycle_for_mod(m: ModEntry, *, has_download_archive: bool = False) -> str:
    """DESCARGADO / PREPARADO / SELECCIONADO / INSTALADO (prioridad visual)."""
    if m.on_disk:
        return "INSTALADO"
    if m.usar:
        return "SELECCIONADO"
    stage_ok = bool(m.stage_path and Path(m.stage_path).is_dir())
    if stage_ok:
        return "PREPARADO"
    if has_download_archive:
        return "DESCARGADO"
    return "—"


@dataclass
class GameProfileStatus:
    game_id: str
    name: str
    downloads_ok: bool
    downloads_count: int
    staging_ok: bool
    staging_mods: int
    destination_ok: bool
    destination_verified: bool
    destination_path: str
    adapter: str
    install_mode: str
    apply_allowed: bool
    path_status: str  # installed | remnant | demo_only | not_installed | pending
    notes: str


def profile_status(paths: GamePaths) -> GameProfileStatus:
    r = paths.record
    dl = Path(r.downloads_dir) if r.downloads_dir.strip() else None
    downloads_ok = bool(dl and dl.is_dir())
    downloads_count = 0
    if downloads_ok and dl is not None:
        try:
            downloads_count = sum(1 for p in dl.iterdir() if p.is_file())
        except OSError:
            downloads_count = 0

    stage = paths.stage_dir
    staging_ok = bool(stage and stage.is_dir())
    staging_mods = 0
    if staging_ok and stage is not None:
        try:
            staging_mods = sum(1 for p in stage.iterdir() if p.is_dir())
        except OSError:
            staging_mods = 0

    dest = paths.mods_dir
    destination_ok = bool(r.mods_dir.strip() and dest.is_dir())
    verified = bool(getattr(r, "destination_verified", False)) and destination_ok
    path_status = str(getattr(r, "path_status", "") or "")
    if not path_status:
        if verified:
            path_status = "installed"
        elif destination_ok:
            path_status = "remnant"
        else:
            path_status = "not_installed"

    return GameProfileStatus(
        game_id=r.id,
        name=r.name,
        downloads_ok=downloads_ok,
        downloads_count=downloads_count,
        staging_ok=staging_ok,
        staging_mods=staging_mods,
        destination_ok=destination_ok,
        destination_verified=verified,
        destination_path=str(dest) if r.mods_dir.strip() else "(pendiente)",
        adapter=r.adapter,
        install_mode=str(r.install_mode or "COPY"),
        apply_allowed=verified,
        path_status=path_status,
        notes=r.notes or "",
    )


def format_profile_status(st: GameProfileStatus) -> str:
    return (
        f"{st.name} ({st.game_id})\n"
        f"  Downloads: {'OK' if st.downloads_ok else 'no'} ({st.downloads_count} archivos)\n"
        f"  Staging: {'OK' if st.staging_ok else 'no'} ({st.staging_mods} mods)\n"
        f"  Destino: {st.destination_path}\n"
        f"  Verificado: {'SÍ' if st.destination_verified else 'NO — Apply bloqueado'}\n"
        f"  Estado ruta: {st.path_status}\n"
        f"  Adaptador: {st.adapter}  ·  Instalación: {st.install_mode}\n"
        f"  {st.notes}"
    )
