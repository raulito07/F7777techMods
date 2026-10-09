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

Plan vs instalación física (solo lectura / etiquetas UI).
"""

from __future__ import annotations

from pathlib import Path

from .apply import ApplyContext, load_manifest
from .inventory import ModEntry


def enrich_installed_from_manifest(mods: list[ModEntry], ctx: ApplyContext) -> None:
    """Marca INSTALADO_REAL (on_disk) si el manifiesto gestiona un .pak presente en ~mods."""
    manifest = load_manifest(ctx)
    if not manifest:
        return
    by_folder = {m.folder: m for m in mods}
    by_pak = {}
    for m in mods:
        for p in m.paks:
            by_pak.setdefault(p.lower(), []).append(m)
    for rel, meta in manifest.items():
        if not isinstance(meta, dict):
            continue
        dest = ctx.mods / rel
        if not dest.is_file():
            continue
        folder = str(meta.get("mod_folder") or "")
        if folder in by_folder:
            by_folder[folder].on_disk = True
            continue
        # S38: componente expandido — emparejar por nombre de .pak o package_folder
        name = Path(rel).name.lower()
        for m in by_pak.get(name, []):
            pkg = getattr(m, "package_folder", "") or ""
            if not folder or folder == m.folder or folder == pkg:
                m.on_disk = True
        for m in mods:
            if getattr(m, "package_folder", "") == folder and name in {
                p.lower() for p in m.paks
            }:
                m.on_disk = True


def plan_flags_for_dest_file(
    rel: str,
    meta: dict,
    mods: list[ModEntry],
) -> tuple[bool, bool, str]:
    """(activo_en_plan, pendiente_retirar, nota_ui) para un archivo del destino."""
    folder = str(meta.get("mod_folder") or "")
    rel_name = Path(rel).name.lower()
    mod = next((m for m in mods if m.folder == folder), None)
    if mod is None:
        mod = next(
            (
                m
                for m in mods
                if (getattr(m, "package_folder", "") == folder or not folder)
                and rel_name in {p.lower() for p in m.paks}
            ),
            None,
        )
    activo = bool(mod and mod.usar)
    pendiente = bool(mod and not mod.usar)
    if activo:
        note = "ACTIVO EN PLAN · archivo también en ~mods"
    elif pendiente:
        note = "INSTALADO REAL · plan NO — sigue en el juego hasta Apply (retirar)"
    else:
        note = "GESTIONADO en manifiesto · mod no enlazado en biblioteca"
    return activo, pendiente, note
