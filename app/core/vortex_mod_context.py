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

S44 — modelo inteligente: relaciones mod ↔ Vortex ↔ plan F7777 (solo lectura).
No parsea LevelDB activa; backups JSON = histórico explícito.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .apply import ApplyContext, load_manifest
from .inventory import ModEntry
from .package_identity import package_folder_of
from .vortex_sync import (
    VortexEnableSnapshot,
    VortexReliability,
    find_vortex_state_backup,
    probe_vortex_enable_state,
    vortex_roaming_root,
)


class ProvenanceKind(str, Enum):
    """Origen de un dato mostrado en UI."""

    CONFIRMED_STAGING = "confirmado_staging"
    CONFIRMED_F7777 = "confirmado_f7777"
    VORTEX_BACKUP = "vortex_backup_historico"
    VORTEX_META_CACHE = "vortex_meta_cache"
    UNKNOWN = "desconocido"


@dataclass
class VortexAuxInfo:
    """Metadatos auxiliares de Vortex (no sustituyen conflict_engine)."""

    vortex_rules: list = field(default_factory=list)
    load_order_index: int | None = None
    load_order_source: str = ""
    collection_dependency: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ModIntelligence:
    """Vista unificada de procedencia y capas de estado para un mod/componente."""

    mod_folder: str
    vortex_staging_key: str
    staging_available: bool = False
    vortex_enabled_historical: bool | None = None
    vortex_enabled_verified: bool | None = None
    in_f7777_plan: bool = False
    managed_f7777: bool = False
    on_disk_game: bool = False
    archived: bool = False
    compat_unknown: bool = True
    download_archive_id: str = ""
    nexus_mod_id: str = ""
    nexus_file_id: str = ""
    vortex_profile_name: str = ""
    backup_source: str = ""
    backup_mtime: str = ""
    aux: VortexAuxInfo = field(default_factory=VortexAuxInfo)

    def provenance_summary(self) -> str:
        lines = [
            "Procedencia (capas independientes):",
            f"  Staging Vortex: {'SÍ' if self.staging_available else 'NO'} "
            f"({ProvenanceKind.CONFIRMED_STAGING.value})",
            f"  Enabled perfil Vortex (verificado): "
            f"{self._fmt_tri(self.vortex_enabled_verified)}",
            f"  Enabled perfil Vortex (backup histórico): "
            f"{self._fmt_tri(self.vortex_enabled_historical)} "
            f"({ProvenanceKind.VORTEX_BACKUP.value})",
            f"  Plan F7777 (usar): {'SÍ' if self.in_f7777_plan else 'NO'} "
            f"({ProvenanceKind.CONFIRMED_F7777.value})",
            f"  Gestionado manifiesto F7777: {'SÍ' if self.managed_f7777 else 'NO'}",
            f"  Archivo en destino juego: {'SÍ' if self.on_disk_game else 'NO'}",
            f"  Compatibilidad interna .pak: "
            f"{'desconocida' if self.compat_unknown else 'parcialmente analizada'}",
        ]
        if self.backup_source:
            lines.append(
                f"  Snapshot Vortex: {self.backup_source} "
                f"mtime={self.backup_mtime or '?'} (histórico, no vivo)"
            )
        if self.vortex_staging_key != self.mod_folder:
            lines.append(
                f"  Clave Vortex perfil: «{self.vortex_staging_key}» "
                f"(componente S38 → paquete)"
            )
        if self.aux.vortex_rules:
            lines.append(
                f"  Reglas Vortex (aux): {len(self.aux.vortex_rules)} regla(s) "
                f"— no sustituyen análisis F7777"
            )
        if self.aux.load_order_index is not None:
            lines.append(
                f"  Load order Vortex (aux): posición {self.aux.load_order_index + 1} "
                f"({self.aux.load_order_source or 'perfil'})"
            )
        if self.aux.collection_dependency:
            lines.append("  Colección Nexus: entrada con installedAsDependency (aux)")
        for n in self.aux.notes:
            lines.append(f"  · {n}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_tri(v: bool | None) -> str:
        if v is True:
            return "SÍ"
        if v is False:
            return "NO"
        return "no verificado"


@dataclass
class _BackupSlice:
    mods: dict[str, dict]
    downloads_by_archive: dict[str, dict]
    load_order: list[str]
    ue4ss_load_order: list[str]
    profile_name: str
    path: Path
    mtime_iso: str


def _iso_mtime(path: Path) -> str:
    try:
        from datetime import datetime

        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


def _read_backup_slice(backup: Path, game_id: str) -> _BackupSlice | None:
    try:
        obj = json.loads(backup.read_text(encoding="utf-8"))
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    persistent = obj.get("persistent") or {}
    mods_game = (persistent.get("mods") or {}).get(game_id) or {}
    mods_index: dict[str, dict] = {}
    for _mid, rec in mods_game.items():
        if not isinstance(rec, dict):
            continue
        key = str(rec.get("id") or rec.get("installationPath") or _mid).replace("\\", "/")
        if "/" in key:
            key = key.rsplit("/", 1)[-1]
        mods_index[key] = rec

    dl_by_arch: dict[str, dict] = {}
    for _did, dl in (persistent.get("downloads") or {}).items():
        if not isinstance(dl, dict):
            continue
        aid = str(dl.get("archiveId") or dl.get("id") or "")
        if aid:
            dl_by_arch[aid] = dl

    profiles = persistent.get("profiles") or {}
    matched = [
        (pid, prof)
        for pid, prof in profiles.items()
        if prof.get("gameId") == game_id
    ]
    matched.sort(key=lambda x: x[1].get("lastActivated") or 0, reverse=True)
    load_order: list[str] = []
    ue4_lo: list[str] = []
    pname = ""
    if matched:
        _pid, prof = matched[0]
        pname = str(prof.get("name") or _pid)
        lo = prof.get("loadOrder") or prof.get("modLoadOrder") or []
        if isinstance(lo, list):
            load_order = [str(x) for x in lo]
        ue = prof.get("ue4ssLoadOrder") or prof.get("ue4ss_load_order") or []
        if isinstance(ue, list):
            ue4_lo = [str(x) for x in ue]

    return _BackupSlice(
        mods=mods_index,
        downloads_by_archive=dl_by_arch,
        load_order=load_order,
        ue4ss_load_order=ue4_lo,
        profile_name=pname,
        path=backup,
        mtime_iso=_iso_mtime(backup),
    )


def _vortex_key_for_mod(m: ModEntry) -> str:
    pkg = (getattr(m, "package_folder", "") or "").strip()
    if pkg:
        return pkg
    return m.folder


def _load_order_index(key: str, slice_: _BackupSlice | None) -> tuple[int | None, str]:
    if not slice_ or not key:
        return None, ""
    for i, mid in enumerate(slice_.load_order):
        if mid == key or mid.endswith("/" + key) or mid.endswith("\\" + key):
            return i, "loadOrder"
    for i, mid in enumerate(slice_.ue4ss_load_order):
        if mid == key or mid.endswith("/" + key):
            return i, "ue4ssLoadOrder"
    return None, ""


def build_mod_intelligence_map(
    mods: list[ModEntry],
    *,
    snap: VortexEnableSnapshot | None = None,
    game_id: str = "",
    roaming: Path | None = None,
    ctx: ApplyContext | None = None,
    adapter_id: str = "",
) -> dict[str, ModIntelligence]:
    """Construye intel por ``mod.folder`` (componentes S38 incluidos). Solo lectura."""
    gid = game_id or (snap.game_id if snap else "")
    if snap is None and gid:
        snap = probe_vortex_enable_state(gid, roaming=roaming, mods_dir=ctx.mods if ctx else None)

    backup_path: Path | None = None
    if snap and snap.source_path:
        backup_path = Path(snap.source_path)
    elif roaming or gid:
        backup_path = find_vortex_state_backup(roaming)

    slice_: _BackupSlice | None = None
    if backup_path and backup_path.is_file() and gid:
        slice_ = _read_backup_slice(backup_path, gid)

    managed: set[str] = set()
    if ctx is not None:
        manifest = load_manifest(ctx)
        for _rel, meta in manifest.items():
            if isinstance(meta, dict):
                mf = str(meta.get("mod_folder") or "")
                if mf:
                    managed.add(mf)
                managed.add(package_folder_of(mf) if mf else mf)

    hist_map = dict(snap.enabled_map) if snap else {}
    reliability = snap.reliability if snap else VortexReliability.UNKNOWN

    out: dict[str, ModIntelligence] = {}
    for m in mods:
        vkey = _vortex_key_for_mod(m)
        stage_ok = bool(m.stage_path and Path(m.stage_path).is_dir())
        rec = (slice_.mods.get(vkey) if slice_ else None) or {}
        attrs = rec.get("attributes") if isinstance(rec.get("attributes"), dict) else {}
        archive_id = str(rec.get("archiveId") or attrs.get("archiveId") or "")
        rules = attrs.get("rules") or rec.get("rules") or []
        if not isinstance(rules, list):
            rules = []
        coll_dep = bool(attrs.get("installedAsDependency"))
        lo_idx, lo_src = _load_order_index(vkey, slice_)

        hist_en: bool | None = None
        if reliability == VortexReliability.HISTORICAL_BACKUP and hist_map:
            if vkey in hist_map:
                hist_en = bool(hist_map[vkey])
        verified_en: bool | None = None
        if reliability == VortexReliability.CURRENT and hist_map:
            verified_en = bool(hist_map.get(vkey, False))

        compat_unknown = True
        if adapter_id in ("ue4_paks_mods", "ue5_iostore_mods", "ue5_iostore_sb"):
            compat_unknown = True  # nunca deducir interior .pak por nombre
        elif m.paks and all(p.lower().endswith(".pak") for p in m.paks):
            compat_unknown = True

        intel = ModIntelligence(
            mod_folder=m.folder,
            vortex_staging_key=vkey,
            staging_available=stage_ok,
            vortex_enabled_historical=hist_en,
            vortex_enabled_verified=verified_en,
            in_f7777_plan=bool(m.usar),
            managed_f7777=m.folder in managed
            or (getattr(m, "package_folder", "") or "") in managed,
            on_disk_game=bool(m.on_disk),
            archived=bool(getattr(m, "archived", False)),
            compat_unknown=compat_unknown,
            download_archive_id=archive_id,
            nexus_mod_id=str(attrs.get("modId") or attrs.get("nexusModId") or ""),
            nexus_file_id=str(attrs.get("fileId") or attrs.get("nexusFileId") or ""),
            vortex_profile_name=(slice_.profile_name if slice_ else "")
            or (snap.profile_name if snap else ""),
            backup_source=(slice_.path.name if slice_ else "")
            or (snap.source_kind if snap else ""),
            backup_mtime=(slice_.mtime_iso if slice_ else "")
            or (snap.source_mtime_iso if snap else ""),
            aux=VortexAuxInfo(
                vortex_rules=list(rules)[:32],
                load_order_index=lo_idx,
                load_order_source=lo_src,
                collection_dependency=coll_dep,
                notes=(
                    ["Sincronización Vortex viva pendiente (LevelDB sin lector)."]
                    if snap and snap.live_state_present and not snap.live_state_readable
                    else []
                ),
            ),
        )
        out[m.folder] = intel
    return out


def live_vortex_sync_available() -> bool:
    """False hasta existir lector LevelDB de solo lectura seguro."""
    return False
