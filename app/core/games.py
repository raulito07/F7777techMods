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

S02 — registro multijuego, sesiones y migración FF7R (sin tocar installs reales).
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .adapters import DEFAULT_ADAPTER_ID, KNOWN_ADAPTER_IDS, suggest_mods_dir
from .apply import ApplyContext
from .conflict_engine import ConflictSettings
from .priority_store import load_priorities, load_resolutions
from .paths import (
    DATA,
    GAMES_DATA_ROOT,
    GAMES_REGISTRY,
    LEGACY_FF7R_GAME_ID,
    LEGACY_FF7R_GAME_ROOT,
    LEGACY_FF7R_MODS,
    LEGACY_FF7R_STAGE,
    LEGACY_FF7R_VORTEX_ID,
    as_path_str,
    discover_steam_game,
    discover_vortex_mods,
    path_configured,
    suggest_vortex_downloads,
    suggest_vortex_mods,
    test_sandbox_active,
)

REGISTRY_VERSION = 1

LEGACY_DATA_FILES = (
    "loadout.json",
    "managed_manifest.json",
    "vortex_mod_meta.json",
    "descriptions_override.json",
    "ui_settings.json",
)


@dataclass
class GameRecord:
    id: str
    name: str
    vortex_game_id: str = ""
    game_root: str = ""
    mods_dir: str = ""
    stage_dir: str = ""
    adapter: str = DEFAULT_ADAPTER_ID
    platform: str = "manual"  # steam|epic|gog|manual|other
    data_mode: str = "isolated"  # isolated | legacy_root
    data_dir_name: str = ""
    enabled: bool = True
    notes: str = ""
    migration_status: str = "not_needed"  # not_needed|pending|complete|blocked
    migration_note: str = ""
    install_mode: str = "COPY"  # COPY | HARDLINK | AUTO (S09)
    downloads_dir: str = ""  # carpeta downloads Vortex (no es staging)
    destination_verified: bool = True  # S10: False → Apply bloqueado (perfiles pendientes)
    path_status: str = "pending"  # installed|remnant|demo_only|not_installed|pending
    archive_dir: str = ""  # S11: carpeta de archivo de paquetes (no Downloads Vortex)
    work_library_dir: str = ""  # S14: biblioteca de trabajo (no staging Vortex)
    default_mod_source: str = "STAGING_VORTEX"  # S15: STAGING_VORTEX|WORK_LIBRARY|AUTO

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "GameRecord":
        return GameRecord(
            id=str(d.get("id") or ""),
            name=str(d.get("name") or ""),
            vortex_game_id=str(d.get("vortex_game_id") or ""),
            game_root=str(d.get("game_root") or ""),
            mods_dir=str(d.get("mods_dir") or ""),
            stage_dir=str(d.get("stage_dir") or ""),
            adapter=str(d.get("adapter") or DEFAULT_ADAPTER_ID),
            platform=str(d.get("platform") or "manual"),
            data_mode=str(d.get("data_mode") or "isolated"),
            data_dir_name=str(d.get("data_dir_name") or d.get("id") or ""),
            enabled=bool(d.get("enabled", True)),
            notes=str(d.get("notes") or ""),
            migration_status=str(d.get("migration_status") or "not_needed"),
            migration_note=str(d.get("migration_note") or ""),
            install_mode=str(d.get("install_mode") or "COPY").upper(),
            downloads_dir=str(d.get("downloads_dir") or ""),
            destination_verified=bool(d["destination_verified"])
            if "destination_verified" in d
            else True,
            path_status=str(d.get("path_status") or "pending"),
            archive_dir=str(d.get("archive_dir") or ""),
            work_library_dir=str(d.get("work_library_dir") or ""),
            default_mod_source=str(
                d.get("default_mod_source") or "STAGING_VORTEX"
            ).upper(),
        )


@dataclass
class GamePaths:
    """Rutas explícitas del juego activo (no mutar constantes globales)."""

    record: GameRecord
    data_dir: Path
    game_root: Path
    mods_dir: Path
    stage_dir: Path | None

    def apply_context(self) -> ApplyContext:
        stage = self.stage_dir if self.stage_dir is not None else Path(".")
        return ApplyContext(
            mods=self.mods_dir,
            deploy=self.mods_dir / "vortex.deployment.json",
            loadout_marker=self.mods_dir / "_manual_loadout.json",
            manifest=self.data_dir / "managed_manifest.json",
            backups=self.data_dir / "backups",
            stage=stage,
            data_dir=self.data_dir,
        )

    @property
    def loadout_json(self) -> Path:
        return self.data_dir / "loadout.json"

    @property
    def meta_cache(self) -> Path:
        return self.data_dir / "vortex_mod_meta.json"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def desc_override(self) -> Path:
        return self.data_dir / "descriptions_override.json"

    @property
    def priorities_json(self) -> Path:
        return self.data_dir / "mod_priorities.json"

    @property
    def resolutions_json(self) -> Path:
        return self.data_dir / "conflict_resolutions.json"

    @property
    def hash_cache_json(self) -> Path:
        return self.data_dir / "hash_cache.json"

    @property
    def operations_dir(self) -> Path:
        return self.data_dir / "operations"

    @property
    def vortex_game_id(self) -> str:
        return self.record.vortex_game_id

    @property
    def adapter_id(self) -> str:
        return self.record.adapter

    @property
    def staging_fingerprint_json(self) -> Path:
        return self.data_dir / "staging_fingerprint.json"

    def conflict_settings(self) -> ConflictSettings:
        from .work_library import resolve_work_root

        work = resolve_work_root(
            self.data_dir,
            configured=getattr(self.record, "work_library_dir", "") or "",
            stage_dir=self.stage_dir,
        )
        return ConflictSettings(
            priorities=load_priorities(self.priorities_json),
            resolutions=load_resolutions(self.resolutions_json),
            hash_cache_path=self.hash_cache_json,
            adapter_id=self.adapter_id,
            mods_root=self.mods_dir if self.record.mods_dir.strip() else None,
            stage_root=self.stage_dir,
            install_mode=str(self.record.install_mode or "COPY").upper(),
            destination_verified=bool(self.record.destination_verified),
            game_id=self.record.id,
            work_root=work,
        )


@dataclass
class GamesRegistry:
    version: int = REGISTRY_VERSION
    active_game_id: str = ""
    games: dict[str, GameRecord] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "active_game_id": self.active_game_id,
            "games": {gid: g.to_dict() for gid, g in self.games.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> "GamesRegistry":
        games = {}
        for gid, gd in (d.get("games") or {}).items():
            rec = GameRecord.from_dict(gd if isinstance(gd, dict) else {})
            if not rec.id:
                rec.id = str(gid)
            games[rec.id] = rec
        return GamesRegistry(
            version=int(d.get("version") or REGISTRY_VERSION),
            active_game_id=str(d.get("active_game_id") or ""),
            games=games,
        )


def _norm_path_key(p: Path | str) -> str:
    try:
        return str(Path(p).resolve()).casefold()
    except OSError:
        return str(Path(p)).replace("\\", "/").casefold()


def slugify_id(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return (s or f"game_{uuid.uuid4().hex[:8]}")[:64]


def resolve_data_dir(record: GameRecord, data_root: Path | None = None) -> Path:
    root = data_root or DATA
    if record.data_mode == "legacy_root":
        return root
    name = record.data_dir_name or record.id
    return (data_root or GAMES_DATA_ROOT.parent) / "games" / name if data_root is None else data_root / "games" / name


def game_paths_for(
    record: GameRecord,
    *,
    app_data: Path | None = None,
) -> GamePaths:
    app_data = app_data or DATA
    if record.data_mode == "legacy_root":
        data_dir = app_data
    else:
        data_dir = app_data / "games" / (record.data_dir_name or record.id)
    stage = Path(record.stage_dir) if record.stage_dir.strip() else None
    return GamePaths(
        record=record,
        data_dir=data_dir,
        game_root=Path(record.game_root) if record.game_root else Path("."),
        mods_dir=Path(record.mods_dir),
        stage_dir=stage,
    )


def validate_game_paths(record: GameRecord) -> list[str]:
    """Errores de validación (rutas). No crea ni borra nada.

    S10: se permite perfil sin destino si ``destination_verified`` es False
    (Apply permanecerá bloqueado).
    """
    errors: list[str] = []
    if not record.name.strip():
        errors.append("El nombre visible es obligatorio.")
    if not record.mods_dir.strip():
        if record.destination_verified:
            errors.append(
                "Destino marcado como verificado pero falta la carpeta de mods."
            )
        # pendiente de instalación: OK registrar sin destino
    else:
        mods = Path(record.mods_dir)
        if not mods.exists():
            # Ruta declarada pero ausente → error (aunque Apply esté bloqueado)
            errors.append(f"La carpeta de mods no existe: {mods}")
        elif not mods.is_dir():
            errors.append(f"La ruta de mods no es un directorio: {mods}")
    if record.game_root.strip():
        gr = Path(record.game_root)
        if not gr.exists():
            errors.append(f"La carpeta raíz del juego no existe: {gr}")
    if record.stage_dir.strip():
        st = Path(record.stage_dir)
        if not st.exists():
            errors.append(f"El staging no existe: {st}")
        elif not st.is_dir():
            errors.append(f"El staging no es un directorio: {st}")
    if record.adapter not in KNOWN_ADAPTER_IDS:
        errors.append(f"Adaptador desconocido: {record.adapter}")
    return errors


def find_mods_dir_owners(
    registry: GamesRegistry,
    mods_dir: str | Path,
    *,
    exclude_id: str = "",
) -> list[GameRecord]:
    key = _norm_path_key(mods_dir)
    out: list[GameRecord] = []
    for g in registry.games.values():
        if exclude_id and g.id == exclude_id:
            continue
        if not g.mods_dir.strip():
            continue
        if _norm_path_key(g.mods_dir) == key:
            out.append(g)
    return out


def destination_conflict_message(
    registry: GamesRegistry,
    record: GameRecord,
) -> str | None:
    owners = find_mods_dir_owners(registry, record.mods_dir, exclude_id=record.id)
    if not owners:
        return None
    names = ", ".join(f"{o.name} ({o.id})" for o in owners)
    return (
        f"El destino de mods ya está asignado a otro perfil: {names}.\n"
        f"Ruta: {record.mods_dir}\n"
        "No se permite que dos perfiles gestionen el mismo destino."
    )


def load_registry(path: Path | None = None) -> GamesRegistry:
    path = path or GAMES_REGISTRY
    if not path.exists():
        return GamesRegistry()
    try:
        return GamesRegistry.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return GamesRegistry()


def save_registry(registry: GamesRegistry, path: Path | None = None) -> None:
    path = path or GAMES_REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(registry.to_dict(), ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def detect_legacy_ff7r_data(app_data: Path | None = None) -> list[str]:
    """Archivos legacy presentes en data/ (sin leer propiedad de ~mods)."""
    app_data = app_data or DATA
    found: list[str] = []
    for name in LEGACY_DATA_FILES:
        if name == "ui_settings.json":
            continue  # global UI ok to share
        p = app_data / name
        if p.exists():
            found.append(name)
    if (app_data / "backups").is_dir() and any((app_data / "backups").iterdir()):
        found.append("backups/")
    if (app_data / "thumbs").is_dir() and any((app_data / "thumbs").iterdir()):
        found.append("thumbs/")
    return found


def make_ff7r_legacy_record(app_data: Path | None = None) -> GameRecord:
    legacy = detect_legacy_ff7r_data(app_data)
    pending = bool(legacy)
    note = ""
    if pending:
        note = (
            "Datos legacy detectados en data/. Migración a carpeta aislada "
            "preparada pero NO ejecutada automáticamente (S02). "
            f"Archivos: {', '.join(legacy)}"
        )
    vortex_dl = suggest_vortex_downloads(LEGACY_FF7R_VORTEX_ID)
    return GameRecord(
        id=LEGACY_FF7R_GAME_ID,
        name="FINAL FANTASY VII REMAKE",
        vortex_game_id=LEGACY_FF7R_VORTEX_ID,
        game_root=as_path_str(LEGACY_FF7R_GAME_ROOT),
        mods_dir=as_path_str(LEGACY_FF7R_MODS),
        stage_dir=as_path_str(LEGACY_FF7R_STAGE),
        adapter="ue4_paks_mods",
        platform="steam",
        data_mode="legacy_root",
        data_dir_name=LEGACY_FF7R_GAME_ID,
        migration_status="pending" if pending else "not_needed",
        migration_note=note,
        install_mode="COPY",
        downloads_dir=as_path_str(vortex_dl),
        destination_verified=path_configured(LEGACY_FF7R_MODS)
        and LEGACY_FF7R_MODS.is_dir(),
        path_status=(
            "installed"
            if path_configured(LEGACY_FF7R_GAME_ROOT) and LEGACY_FF7R_GAME_ROOT.is_dir()
            else "not_installed"
        ),
    )


def make_ff7_rebirth_record() -> GameRecord:
    """Perfil aislado FF7 Rebirth (S10). No modifica datos de Remake."""
    root = discover_steam_game("FINAL FANTASY VII REBIRTH")
    mods = (
        root / "End" / "Content" / "Paks" / "~mods"
        if path_configured(root)
        else Path()
    )
    stage = discover_vortex_mods("finalfantasy7rebirth")
    downloads = suggest_vortex_downloads("finalfantasy7rebirth")
    installed = (
        path_configured(root)
        and root.is_dir()
        and (root / "End" / "Content" / "Paks").is_dir()
    )
    remnant = False
    if mods.is_dir():
        try:
            remnant = any(mods.iterdir())
        except OSError:
            remnant = False
    notes = (
        "UE5 IoStore (.pak/.utoc/.ucas). Sin slots semánticos de Remake. "
        "Rutas descubiertas por Steam/APPDATA (sin hardcode de usuario)."
    )
    if remnant:
        notes += " Restos detectados en ~mods (no adoptados automáticamente)."
    return GameRecord(
        id="ff7_rebirth",
        name="FINAL FANTASY VII REBIRTH",
        vortex_game_id="finalfantasy7rebirth",
        game_root=as_path_str(root) if installed else "",
        mods_dir=as_path_str(mods) if installed and mods.is_dir() else "",
        stage_dir=as_path_str(stage),
        adapter="ue5_iostore_mods",
        platform="steam",
        data_mode="isolated",
        data_dir_name="ff7_rebirth",
        install_mode="COPY",
        downloads_dir=as_path_str(downloads),
        destination_verified=bool(installed and mods.is_dir()),
        path_status="remnant" if (installed and remnant) else (
            "installed" if installed else "not_installed"
        ),
        notes=notes,
        migration_status="not_needed",
    )


def make_stellar_blade_record() -> GameRecord:
    """Perfil aislado Stellar Blade (S10). Destino solo si juego completo verificado."""
    stage = discover_vortex_mods("stellarblade")
    if not path_configured(stage):
        stage = suggest_vortex_mods("stellarblade")
    downloads = suggest_vortex_downloads("stellarblade")
    demo = discover_steam_game("StellarBladeDemo")
    full = discover_steam_game("StellarBlade")
    if not path_configured(full):
        full = discover_steam_game("Stellar Blade")
    full = full if path_configured(full) else None
    # Demo no aporta Content/Paks usable → no verificar como destino
    notes = (
        "Staging/downloads Vortex presentes. "
        "Adaptador UE5 IoStore genérico (sin semántica FF7R). "
        "No extraer archives automáticamente."
    )
    if full:
        # Destino sugerido solo si existe árbol Paks (no inventar)
        mods = full / "SB" / "Content" / "Paks" / "~mods"
        if not mods.parent.is_dir():
            mods = full / "Content" / "Paks" / "~mods"
        verified = mods.is_dir() or mods.parent.is_dir()
        if verified and not mods.is_dir():
            # padre Paks existe pero ~mods no: aún no crear ~mods (no escribir)
            notes += " Instalación completa detectada; ~mods aún no existe (Apply bloqueado)."
            return GameRecord(
                id="stellar_blade",
                name="Stellar Blade",
                vortex_game_id="stellarblade",
                game_root=str(full),
                mods_dir="",
                stage_dir=as_path_str(stage),
                adapter="ue5_iostore_mods",
                platform="steam",
                data_mode="isolated",
                data_dir_name="stellar_blade",
                install_mode="COPY",
                downloads_dir=as_path_str(downloads),
                destination_verified=False,
                path_status="installed",
                notes=notes,
            )
        return GameRecord(
            id="stellar_blade",
            name="Stellar Blade",
            vortex_game_id="stellarblade",
            game_root=str(full),
            mods_dir=str(mods) if mods.is_dir() else "",
            stage_dir=as_path_str(stage),
            adapter="ue5_iostore_mods",
            platform="steam",
            data_mode="isolated",
            data_dir_name="stellar_blade",
            install_mode="COPY",
            downloads_dir=as_path_str(downloads),
            destination_verified=mods.is_dir(),
            path_status="installed",
            notes=notes,
        )

    if path_configured(demo) and demo.is_dir():
        notes += (
            f" Solo se encontró StellarBladeDemo en {demo} "
            "(sin Content/Paks). No usar demo como destino del juego completo."
        )
    else:
        notes += " Juego completo no encontrado en Steam."

    return GameRecord(
        id="stellar_blade",
        name="Stellar Blade",
        vortex_game_id="stellarblade",
        game_root="",
        mods_dir="",
        stage_dir=as_path_str(stage),
        adapter="ue5_iostore_mods",
        platform="steam",
        data_mode="isolated",
        data_dir_name="stellar_blade",
        install_mode="COPY",
        downloads_dir=as_path_str(downloads),
        destination_verified=False,
        path_status=(
            "demo_only"
            if path_configured(demo) and demo.is_dir()
            else "not_installed"
        ),
        notes=notes,
    )


def ensure_s10_profiles(registry: GamesRegistry) -> bool:
    """Añade Rebirth/Stellar y completa campos S10 de Remake. No toca Steam/Vortex.

    Conserva rutas/datos existentes de Remake. Devuelve True si hubo cambios.
    """
    if test_sandbox_active():
        # S29: no inyectar perfiles reales de Steam/Vortex en modo prueba.
        return False
    changed = False
    remake = registry.games.get(LEGACY_FF7R_GAME_ID)
    if remake:
        if not remake.downloads_dir:
            dl = suggest_vortex_downloads(LEGACY_FF7R_VORTEX_ID)
            if path_configured(dl):
                remake.downloads_dir = as_path_str(dl)
                changed = True
        if not remake.destination_verified and Path(remake.mods_dir).is_dir():
            remake.destination_verified = True
            remake.path_status = "installed"
            changed = True
        if not remake.path_status or remake.path_status == "pending":
            remake.path_status = "installed" if Path(remake.game_root).is_dir() else remake.path_status
            changed = True

    if "ff7_rebirth" not in registry.games:
        registry.games["ff7_rebirth"] = make_ff7_rebirth_record()
        changed = True
    if "stellar_blade" not in registry.games:
        registry.games["stellar_blade"] = make_stellar_blade_record()
        changed = True
    return changed


def ensure_registry(
    path: Path | None = None,
    *,
    app_data: Path | None = None,
) -> GamesRegistry:
    """Carga o crea registro. Si no hay juegos, inserta perfil FF7R compatible.

    S10: asegura perfiles Rebirth/Stellar sin alterar datos aislados de Remake.
    """
    path = path or GAMES_REGISTRY
    reg = load_registry(path)
    dirty = False
    if not reg.games:
        if test_sandbox_active():
            # Perfil vacío: el launcher S29 escribe games.json sintético.
            return reg
        ff7 = make_ff7r_legacy_record(app_data)
        reg.games[ff7.id] = ff7
        reg.active_game_id = ff7.id
        dirty = True
    if ensure_s10_profiles(reg):
        dirty = True
    if not reg.active_game_id or reg.active_game_id not in reg.games:
        reg.active_game_id = next(iter(reg.games))
        dirty = True
    if dirty:
        save_registry(reg, path)
    return reg


def active_game_paths(
    registry: GamesRegistry | None = None,
    *,
    app_data: Path | None = None,
    registry_path: Path | None = None,
) -> GamePaths | None:
    reg = registry or ensure_registry(registry_path, app_data=app_data)
    gid = reg.active_game_id
    if not gid or gid not in reg.games:
        return None
    return game_paths_for(reg.games[gid], app_data=app_data)


@dataclass
class MigrationPlan:
    game_id: str
    source_data: Path
    target_data: Path
    files_to_copy: list[str]
    blocked: bool
    reason: str
    reversible_note: str


def prepare_ff7r_migration(
    registry: GamesRegistry,
    *,
    app_data: Path | None = None,
) -> MigrationPlan:
    """Prepara copia aislada. No escribe en staging ni en ~mods del juego."""
    app_data = app_data or DATA
    rec = registry.games.get(LEGACY_FF7R_GAME_ID)
    if not rec:
        return MigrationPlan(
            LEGACY_FF7R_GAME_ID,
            app_data,
            app_data / "games" / LEGACY_FF7R_GAME_ID,
            [],
            True,
            "No existe el perfil FF7 Remake en el registro.",
            "",
        )
    target = app_data / "games" / (rec.data_dir_name or LEGACY_FF7R_GAME_ID)
    files = detect_legacy_ff7r_data(app_data)
    if rec.data_mode == "isolated" and rec.migration_status == "complete":
        return MigrationPlan(
            rec.id,
            app_data,
            target,
            [],
            True,
            "La migración ya está marcada como complete.",
            "Los originales en data/ no se borran automáticamente.",
        )
    if not files:
        return MigrationPlan(
            rec.id,
            app_data,
            target,
            [],
            False,
            "No hay archivos legacy que migrar; se puede pasar a modo isolated vacío.",
            "Reversible: volver data_mode=legacy_root en games.json.",
        )
    # Bloqueo automático: no ejecutar si target ya tiene manifiesto/loadout distintos
    conflict = []
    for name in files:
        if name.endswith("/"):
            continue
        t = target / name
        s = app_data / name
        if t.exists() and s.exists():
            try:
                if t.read_bytes() != s.read_bytes():
                    conflict.append(name)
            except OSError:
                conflict.append(name)
    if conflict:
        return MigrationPlan(
            rec.id,
            app_data,
            target,
            files,
            True,
            "BLOQUEO: el destino aislado ya tiene archivos distintos a los legacy "
            f"({', '.join(conflict)}). No se migra automáticamente para no perder datos.",
            "Resolver a mano o borrar el destino aislado vacío/incorrecto, luego reintentar.",
        )
    return MigrationPlan(
        rec.id,
        app_data,
        target,
        files,
        False,
        "Listo para copiar (sin borrar originales).",
        "Reversible: mantener data_mode=legacy_root; los originales permanecen en data/.",
    )


def execute_ff7r_migration_copy(
    registry: GamesRegistry,
    plan: MigrationPlan,
    *,
    registry_path: Path | None = None,
) -> GamesRegistry:
    """Copia datos a carpeta aislada. NO borra originales. NO toca Steam/Vortex."""
    if plan.blocked:
        raise RuntimeError(plan.reason)
    plan.target_data.mkdir(parents=True, exist_ok=True)
    for name in plan.files_to_copy:
        src = plan.source_data / name.rstrip("/")
        dst = plan.target_data / name.rstrip("/")
        if name.endswith("/"):
            if src.is_dir():
                if dst.exists():
                    continue
                shutil.copytree(src, dst)
            continue
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    rec = registry.games[plan.game_id]
    rec.data_mode = "isolated"
    rec.migration_status = "complete"
    rec.migration_note = (
        f"Migrado por copia el {datetime.now().isoformat(timespec='seconds')}. "
        "Originales en data/ conservados."
    )
    registry.games[plan.game_id] = rec
    save_registry(registry, registry_path)
    return registry


def add_game(registry: GamesRegistry, record: GameRecord) -> list[str]:
    errors = validate_game_paths(record)
    if not record.id:
        record.id = slugify_id(record.name)
    if record.id in registry.games:
        errors.append(f"Ya existe un juego con id '{record.id}'.")
    msg = destination_conflict_message(registry, record)
    if msg:
        errors.append(msg)
    if errors:
        return errors
    if not record.data_dir_name:
        record.data_dir_name = record.id
    record.data_mode = "isolated"
    registry.games[record.id] = record
    if not registry.active_game_id:
        registry.active_game_id = record.id
    return []


def update_game(registry: GamesRegistry, record: GameRecord) -> list[str]:
    if record.id not in registry.games:
        return [f"No existe el juego '{record.id}'."]
    errors = validate_game_paths(record)
    msg = destination_conflict_message(registry, record)
    if msg:
        errors.append(msg)
    if errors:
        return errors
    # Conservar migración/data_mode si no se fuerza
    prev = registry.games[record.id]
    if not record.data_dir_name:
        record.data_dir_name = prev.data_dir_name or record.id
    if record.data_mode not in ("isolated", "legacy_root"):
        record.data_mode = prev.data_mode
    if not record.migration_status:
        record.migration_status = prev.migration_status
        record.migration_note = prev.migration_note
    registry.games[record.id] = record
    return []


def remove_game(registry: GamesRegistry, game_id: str) -> list[str]:
    """Quita del registro; no borra archivos de datos ni del juego."""
    if game_id not in registry.games:
        return [f"No existe '{game_id}'."]
    del registry.games[game_id]
    if registry.active_game_id == game_id:
        registry.active_game_id = next(iter(registry.games), "")
    return []


def set_active_game(registry: GamesRegistry, game_id: str) -> list[str]:
    if game_id not in registry.games:
        return [f"No existe '{game_id}'."]
    rec = registry.games[game_id]
    msg = destination_conflict_message(registry, rec)
    if msg:
        return [msg]
    # Si otro perfil activo distinto compartiera destino — ya cubierto
    registry.active_game_id = game_id
    return []


def ensure_game_data_dir(paths: GamePaths) -> None:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    (paths.data_dir / "backups").mkdir(parents=True, exist_ok=True)
    (paths.data_dir / "thumbs").mkdir(parents=True, exist_ok=True)


def default_record_from_root(
    name: str,
    game_root: str,
    *,
    adapter: str = DEFAULT_ADAPTER_ID,
    platform: str = "manual",
    vortex_game_id: str = "",
    stage_dir: str = "",
) -> GameRecord:
    root = Path(game_root)
    mods = suggest_mods_dir(root, adapter) if game_root else Path("")
    gid = slugify_id(name)
    return GameRecord(
        id=gid,
        name=name,
        vortex_game_id=vortex_game_id,
        game_root=str(root) if game_root else "",
        mods_dir=str(mods) if game_root else "",
        stage_dir=stage_dir,
        adapter=adapter,
        platform=platform,
        data_mode="isolated",
        data_dir_name=gid,
    )
