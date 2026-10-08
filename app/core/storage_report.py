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

S09 — informe de almacenamiento (tamaños lógicos; sin inventar ahorros físicos).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .install_modes import (
    InstallMethod,
    InstallMode,
    decide_install_method,
    parse_install_mode,
    probe_volume,
    same_file,
)
from .inventory import ModEntry

SKIP = {"thumbs.db", "desktop.ini", "vortex.deployment.json", "_manual_loadout.json"}


def _dir_logical_size(root: Path | None) -> tuple[int, int]:
    """(bytes, file_count). Solo lógico; no intenta clusters del FS."""
    if root is None or not root.is_dir():
        return 0, 0
    total = 0
    n = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if f.name.lower() in SKIP or f.name.lower().startswith("vortex"):
            continue
        try:
            total += f.stat().st_size
            n += 1
        except OSError:
            continue
    return total, n


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KiB", 1024), ("MiB", 1024**2), ("GiB", 1024**3), ("TiB", 1024**4)):
        if n < div * 1024 or unit == "TiB":
            return f"{n / div:.2f} {unit}"
    return f"{n} B"


@dataclass
class StorageReport:
    downloads_logical: int = 0
    downloads_files: int = 0
    downloads_path: str = ""
    staging_logical: int = 0
    staging_files: int = 0
    staging_path: str = ""
    deployed_logical: int = 0
    deployed_files: int = 0
    deployed_path: str = ""
    hardlinked_to_stage: int = 0
    hardlinked_bytes_logical: int = 0
    estimated_extra_copy: int = 0
    estimated_extra_auto: int = 0
    estimated_extra_hardlink_policy: int = 0
    estimated_savings_hardlink_vs_copy: int = 0
    notes: list[str] = field(default_factory=list)
    volume_note: str = ""

    def format(self) -> str:
        lines = [
            "=== Almacenamiento (S09) — tamaños lógicos ===",
            f"Downloads: {_fmt_bytes(self.downloads_logical)} "
            f"({self.downloads_files} archivos)"
            + (f"\n  {self.downloads_path}" if self.downloads_path else "\n  (ruta no configurada)"),
            f"Staging:   {_fmt_bytes(self.staging_logical)} "
            f"({self.staging_files} archivos)"
            + (f"\n  {self.staging_path}" if self.staging_path else ""),
            f"Desplegado:{_fmt_bytes(self.deployed_logical)} "
            f"({self.deployed_files} archivos)"
            + (f"\n  {self.deployed_path}" if self.deployed_path else ""),
            f"Enlaces hardlink destino↔staging detectados: {self.hardlinked_to_stage} "
            f"(lógico {_fmt_bytes(self.hardlinked_bytes_logical)}; "
            "no se cuentan como dos copias físicas)",
            "",
            "Espacio adicional estimado al instalar el plan activo:",
            f"  Política COPY:     +{_fmt_bytes(self.estimated_extra_copy)}",
            f"  Política AUTO:     +{_fmt_bytes(self.estimated_extra_auto)}",
            f"  Política HARDLINK: +{_fmt_bytes(self.estimated_extra_hardlink_policy)} "
            "(bloqueados → COPY)",
            f"Ahorro estimado HARDLINK/AUTO vs COPY (lógico): "
            f"{_fmt_bytes(self.estimated_savings_hardlink_vs_copy)}",
            "",
            "Los ahorros son estimaciones lógicas según elegibilidad; "
            "no se inventan mediciones de clusters/NTFS.",
        ]
        if self.volume_note:
            lines += ["", self.volume_note]
        for n in self.notes:
            lines.append(f"! {n}")
        return "\n".join(lines)


def count_hardlinks_to_stage(mods_dir: Path, stage_dir: Path | None) -> tuple[int, int]:
    """Cuenta archivos en destino que son el mismo inode que algún archivo de staging."""
    if not mods_dir.is_dir() or stage_dir is None or not stage_dir.is_dir():
        return 0, 0
    # Indexar inodes de staging (dev, ino) → size
    stage_inodes: dict[tuple[int, int], int] = {}
    for f in stage_dir.rglob("*"):
        if not f.is_file() or f.is_symlink():
            continue
        try:
            st = f.stat()
            stage_inodes[(st.st_dev, st.st_ino)] = st.st_size
        except OSError:
            continue
    n = 0
    logical = 0
    for f in mods_dir.rglob("*"):
        if not f.is_file() or f.name in SKIP:
            continue
        try:
            st = f.stat()
            key = (st.st_dev, st.st_ino)
            if key in stage_inodes:
                n += 1
                logical += st.st_size
        except OSError:
            continue
    return n, logical


def build_storage_report(
    *,
    mods_dir: Path,
    stage_dir: Path | None,
    downloads_dir: Path | None = None,
    plan_sources: list[tuple[Path, Path, str]] | None = None,
    # list of (source, dest, dest_rel)
    install_mode: str = "COPY",
) -> StorageReport:
    rep = StorageReport()
    if downloads_dir and downloads_dir.is_dir():
        rep.downloads_logical, rep.downloads_files = _dir_logical_size(downloads_dir)
        rep.downloads_path = str(downloads_dir)
    if stage_dir:
        rep.staging_logical, rep.staging_files = _dir_logical_size(stage_dir)
        rep.staging_path = str(stage_dir)
    rep.deployed_logical, rep.deployed_files = _dir_logical_size(mods_dir)
    rep.deployed_path = str(mods_dir)
    rep.hardlinked_to_stage, rep.hardlinked_bytes_logical = count_hardlinks_to_stage(
        mods_dir, stage_dir
    )

    vm = probe_volume(mods_dir)
    rep.volume_note = (
        f"Volumen destino: FS={vm.fs_name} hardlinks="
        f"{'sí' if vm.supports_hardlinks else ('no' if vm.supports_hardlinks is False else '?')}"
    )

    if not plan_sources:
        return rep

    extra_copy = 0
    extra_auto = 0
    extra_hl = 0
    for source, dest, rel in plan_sources:
        try:
            size = source.stat().st_size
        except OSError:
            size = 0
        # Si ya samefile, espacio adicional 0
        if dest.exists() and same_file(source, dest):
            continue
        extra_copy += size
        d_auto = decide_install_method(
            source, dest, InstallMode.AUTO, stage_root=stage_dir, mods_root=mods_dir, dest_rel=rel
        )
        d_hl = decide_install_method(
            source,
            dest,
            InstallMode.HARDLINK,
            stage_root=stage_dir,
            mods_root=mods_dir,
            dest_rel=rel,
        )
        if d_auto.method == InstallMethod.HARDLINK:
            # hardlink: espacio adicional lógico ~0 (mismo inode)
            pass
        else:
            extra_auto += size
        if d_hl.method == InstallMethod.HARDLINK and not d_hl.blocked:
            pass
        else:
            extra_hl += size

    rep.estimated_extra_copy = extra_copy
    rep.estimated_extra_auto = extra_auto
    rep.estimated_extra_hardlink_policy = extra_hl
    # Ahorro vs COPY usando AUTO como referencia práctica
    mode = parse_install_mode(install_mode)
    if mode == InstallMode.COPY:
        used = extra_copy
    elif mode == InstallMode.HARDLINK:
        used = extra_hl
    else:
        used = extra_auto
    rep.estimated_savings_hardlink_vs_copy = max(0, extra_copy - used)
    return rep


def plan_sources_from_desired(
    desired_meta: dict,
    mods_root: Path,
) -> list[tuple[Path, Path, str]]:
    out: list[tuple[Path, Path, str]] = []
    for rel, meta in desired_meta.items():
        src = Path(meta.source)
        dst = mods_root / Path(rel)
        out.append((src, dst, rel))
    return out
