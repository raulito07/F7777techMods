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

S49 — investigador universal de mods (solo lectura).
Reconocer un formato ≠ saber instalarlo de forma segura.
Ningún juego/formato está acoplado al núcleo: detectores y reglas se registran.
No escribe en staging, Vortex, Steam ni destinos de juego.
NO habilita Apply para formatos desconocidos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Protocol

from .adapters import get_adapter
from .content_classify import classify_mod
from .inventory import ModEntry, package_payload_summary
from .package_identity import package_folder_of
from .paths import discover_vortex_mods
from .vortex_sync import (
    find_vortex_state_backup,
    probe_vortex_enable_state,
    vortex_roaming_root,
)

# ---------------------------------------------------------------------------
# Capacidad de instalación vs identidad (independientes)
# ---------------------------------------------------------------------------


class InstallCapability(str, Enum):
    """Qué puede hacer F7777techMods con el contenido (no la identidad del mod)."""

    CONFIRMED = "INSTALACION_CONFIRMADA"
    PROBABLE = "INSTALACION_PROBABLE"
    EXTERNAL = "INSTALACION_EXTERNA"
    UNSUPPORTED = "NO_SOPORTADO"
    UNKNOWN = "DESCONOCIDO"


class EvidenceLevel(str, Enum):
    CONFIRMED = "confirmada"
    PROBABLE = "probable"
    WEAK = "debil"
    NONE = "ninguna"


class FormatFamily(str, Enum):
    """Familias detectables; no amarran a un juego concreto."""

    PAK = "pak"
    IOSTORE = "iostore"
    MEDIA_MOVIE = "media_movie"
    SCRIPT_LUA = "script_lua"
    INJECTOR_TOOL = "injector_tool"
    CONFIG_INI = "config_ini"
    RESHADE = "reshade"
    ARCHIVE_META = "archive_meta"
    BINARY_OTHER = "binary_other"
    EMPTY = "empty"
    UNKNOWN = "unknown"


SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".db"}
SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
DOC_SUFFIXES = {".md", ".txt", ".rtf", ".pdf", ".doc", ".docx"}
README_NAMES = {"readme", "readme.txt", "readme.md", "install.txt", "instructions.txt"}

MEDIA_SUFFIXES = {".emov", ".bk2", ".mp4", ".usm", ".bik", ".webm"}
IOSTORE_SUFFIXES = {".pak", ".utoc", ".ucas"}
LUA_SUFFIXES = {".lua"}
RESHADE_SUFFIXES = {".fx", ".fxh", ".hlsl"}
TOOL_SUFFIXES = {".dll", ".asi", ".exe", ".ct"}
INI_SUFFIXES = {".ini"}
META_ONLY_SUFFIXES = {".json"}


@dataclass(frozen=True)
class EvidenceItem:
    claim: str
    level: EvidenceLevel
    source: str  # staging | vortex_backup | adapter | readme | game_homolog | plugin


@dataclass
class DestinationHypothesis:
    path_hint: str
    level: EvidenceLevel
    reason: str
    confirmed: bool = False  # solo True con evidencia CONFIRMED + procedimiento F7777


@dataclass
class FormatHit:
    family: FormatFamily
    detector_id: str
    confidence: EvidenceLevel
    sample_files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class VortexModFacts:
    """Hechos Vortex observados (nunca inferir deploy solo por installed/enabled)."""

    mod_id: str = ""
    state: str = ""
    mod_type: str = ""
    archive_id: str = ""
    installation_path: str = ""
    installer_hint: str = ""
    attributes_mod_id: str = ""
    attributes_file_id: str = ""
    enabled_historical: bool | None = None
    enabled_verified: bool | None = None
    need_to_deploy: bool | None = None
    deployment_manifest_found: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class InvestigationReport:
    """Informe consultable desde Biblioteca; no autoriza Apply."""

    mod_folder: str
    game_id: str = ""
    vortex_game_id: str = ""
    identity_ok: bool = True
    display_name: str = ""
    capability: InstallCapability = InstallCapability.UNKNOWN
    formats: list[FormatHit] = field(default_factory=list)
    destinations: list[DestinationHypothesis] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    vortex: VortexModFacts = field(default_factory=VortexModFacts)
    payload_exts: dict[str, int] = field(default_factory=dict)
    readme_snippets: list[str] = field(default_factory=list)
    missing_steps: list[str] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    manual_confirmed: bool = False
    apply_allowed: bool = False  # S49: siempre False salvo formatos ya soportados
    f7777_installable: bool = False
    human_required: bool = False
    notes: list[str] = field(default_factory=list)

    def library_summary(self) -> str:
        """Texto para panel de detalle Biblioteca."""
        fmt = ", ".join(f.family.value for f in self.formats) or "(ninguno)"
        dest_lines = []
        for d in self.destinations[:6]:
            tag = "CONFIRMADO" if d.confirmed else d.level.value.upper()
            dest_lines.append(f"  [{tag}] {d.path_hint} — {d.reason}")
        if not dest_lines:
            dest_lines = ["  (sin destino respaldado)"]
        ev_lines = [
            f"  · [{e.level.value}] {e.claim} ({e.source})" for e in self.evidence[:10]
        ]
        if not ev_lines:
            ev_lines = ["  (sin evidencia)"]
        miss = "\n".join(f"  • {x}" for x in self.missing_steps[:8]) or "  (ninguno)"
        manual = "\n".join(f"  • {x}" for x in self.manual_steps[:8]) or "  (ninguno)"
        man_tag = (
            "confirmadas por evidencia"
            if self.manual_confirmed
            else "orientativas / no confirmadas"
        )
        v = self.vortex
        return (
            "Investigación S49 (solo lectura; no autoriza Apply)\n"
            f"Identidad: {self.display_name or self.mod_folder}\n"
            f"Capacidad instalación F7777: {self.capability.value}\n"
            f"Formatos detectados: {fmt}\n"
            f"Instalable F7777 hoy: {'SÍ' if self.f7777_installable else 'NO'}\n"
            f"Apply permitido: {'SÍ' if self.apply_allowed else 'NO'}\n"
            f"Intervención humana: {'SÍ' if self.human_required else 'no'}\n"
            f"\nVortex (hechos):\n"
            f"  state={v.state or '—'} type={v.mod_type or '(vacío)'}\n"
            f"  enabled histórico={_tri(v.enabled_historical)} "
            f"verificado={_tri(v.enabled_verified)}\n"
            f"  instalador hint={v.installer_hint or '—'}\n"
            f"  needToDeploy={_tri(v.need_to_deploy)} "
            f"manifiesto deploy={('SÍ' if v.deployment_manifest_found else 'NO')}\n"
            f"  Nota: installed/enabled ≠ desplegado al juego.\n"
            f"\nDestinos:\n" + "\n".join(dest_lines) + "\n"
            f"\nEvidencia:\n" + "\n".join(ev_lines) + "\n"
            f"\nPasos faltantes:\n{miss}\n"
            f"\nManual ({man_tag}):\n{manual}"
        )


def _tri(v: bool | None) -> str:
    if v is True:
        return "SÍ"
    if v is False:
        return "NO"
    return "no verificado"


# ---------------------------------------------------------------------------
# Detectores pluggables (núcleo sin juegos hardcodeados)
# ---------------------------------------------------------------------------


class FormatDetector(Protocol):
    id: str

    def detect(self, ctx: "InvestigationContext") -> FormatHit | None: ...


@dataclass
class InvestigationContext:
    mod: ModEntry
    stage_root: Path
    adapter_id: str
    game_id: str
    vortex_game_id: str
    files: list[Path]
    ext_counts: dict[str, int]
    relative_paths: list[str]
    game_root: Path | None = None
    mods_dest: Path | None = None
    vortex_meta: dict | None = None
    vortex_facts: VortexModFacts | None = None
    plugin_hints: dict[str, str] = field(default_factory=dict)


def _collect_files(root: Path, *, limit: int = 4000) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name in SKIP_NAMES:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _ext_counts(files: Iterable[Path]) -> dict[str, int]:
    c: dict[str, int] = {}
    for p in files:
        ext = p.suffix.lower() or "(none)"
        c[ext] = c.get(ext, 0) + 1
    return c


class PakDetector:
    id = "detector_pak"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        n = ctx.ext_counts.get(".pak", 0)
        if n <= 0:
            return None
        samples = [str(p.relative_to(ctx.stage_root)) for p in ctx.files if p.suffix.lower() == ".pak"][:6]
        return FormatHit(
            FormatFamily.PAK,
            self.id,
            EvidenceLevel.CONFIRMED,
            samples,
            [f"{n} archivo(s) .pak en staging"],
        )


class IoStoreDetector:
    id = "detector_iostore"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        has_pak = ctx.ext_counts.get(".pak", 0) > 0
        has_utoc = ctx.ext_counts.get(".utoc", 0) > 0
        has_ucas = ctx.ext_counts.get(".ucas", 0) > 0
        if not (has_utoc or has_ucas):
            return None
        level = (
            EvidenceLevel.CONFIRMED
            if has_pak and has_utoc and has_ucas
            else EvidenceLevel.PROBABLE
        )
        samples = [
            str(p.relative_to(ctx.stage_root))
            for p in ctx.files
            if p.suffix.lower() in IOSTORE_SUFFIXES
        ][:8]
        notes = []
        if not (has_pak and has_utoc and has_ucas):
            notes.append("Grupo IoStore incompleto (.pak/.utoc/.ucas)")
        return FormatHit(FormatFamily.IOSTORE, self.id, level, samples, notes)


class MediaMovieDetector:
    id = "detector_media_movie"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        hits = [
            p
            for p in ctx.files
            if p.suffix.lower() in MEDIA_SUFFIXES
        ]
        if not hits:
            return None
        samples = [str(p.relative_to(ctx.stage_root)) for p in hits[:8]]
        return FormatHit(
            FormatFamily.MEDIA_MOVIE,
            self.id,
            EvidenceLevel.CONFIRMED,
            samples,
            [f"{len(hits)} archivo(s) de vídeo/medio"],
        )


class LuaScriptDetector:
    id = "detector_lua"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        n = ctx.ext_counts.get(".lua", 0)
        if n <= 0:
            return None
        samples = [
            str(p.relative_to(ctx.stage_root))
            for p in ctx.files
            if p.suffix.lower() == ".lua"
        ][:6]
        return FormatHit(
            FormatFamily.SCRIPT_LUA,
            self.id,
            EvidenceLevel.CONFIRMED,
            samples,
            ["Scripts Lua (típicamente runtime externo / UE4SS)"],
        )


class ReshadeDetector:
    id = "detector_reshade"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        n_fx = sum(ctx.ext_counts.get(s, 0) for s in RESHADE_SUFFIXES)
        if n_fx <= 0:
            return None
        samples = [
            str(p.relative_to(ctx.stage_root))
            for p in ctx.files
            if p.suffix.lower() in RESHADE_SUFFIXES
        ][:6]
        return FormatHit(
            FormatFamily.RESHADE,
            self.id,
            EvidenceLevel.CONFIRMED,
            samples,
            ["Shaders ReShade / FX"],
        )


class InjectorToolDetector:
    id = "detector_injector_tool"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        hits = [p for p in ctx.files if p.suffix.lower() in TOOL_SUFFIXES]
        if not hits:
            return None
        samples = [str(p.relative_to(ctx.stage_root)) for p in hits[:6]]
        return FormatHit(
            FormatFamily.INJECTOR_TOOL,
            self.id,
            EvidenceLevel.CONFIRMED,
            samples,
            ["Binarios / inyector / tabla CE — no van a ~mods genérico"],
        )


class ConfigIniDetector:
    id = "detector_config_ini"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        # Solo si no hay payload más fuerte (pak/media/lua/tool)
        strong = any(
            ctx.ext_counts.get(s, 0) > 0
            for s in (".pak", ".utoc", ".ucas", ".emov", ".bk2", ".lua", ".dll", ".asi", ".fx")
        )
        n = ctx.ext_counts.get(".ini", 0)
        if n <= 0 or strong:
            return None
        samples = [
            str(p.relative_to(ctx.stage_root))
            for p in ctx.files
            if p.suffix.lower() == ".ini"
        ][:4]
        return FormatHit(
            FormatFamily.CONFIG_INI,
            self.id,
            EvidenceLevel.PROBABLE,
            samples,
            ["Solo .ini / config sin payload instalable conocido"],
        )


class MetaOnlyDetector:
    id = "detector_meta_only"

    def detect(self, ctx: InvestigationContext) -> FormatHit | None:
        payload = {
            k: v
            for k, v in ctx.ext_counts.items()
            if k not in SKIP_SUFFIXES
            and k not in DOC_SUFFIXES
            and k not in META_ONLY_SUFFIXES
            and k != "(none)"
        }
        if payload:
            return None
        if ctx.ext_counts.get(".json", 0) <= 0 and not ctx.files:
            return FormatHit(
                FormatFamily.EMPTY,
                self.id,
                EvidenceLevel.CONFIRMED,
                [],
                ["Staging vacío o solo basura"],
            )
        if ctx.ext_counts.get(".json", 0) > 0:
            return FormatHit(
                FormatFamily.ARCHIVE_META,
                self.id,
                EvidenceLevel.PROBABLE,
                [str(p.relative_to(ctx.stage_root)) for p in ctx.files if p.suffix.lower() == ".json"][:4],
                ["Solo metadatos JSON (colección / marcador); sin payload"],
            )
        return None


DEFAULT_DETECTORS: list[FormatDetector] = [
    PakDetector(),
    IoStoreDetector(),
    MediaMovieDetector(),
    LuaScriptDetector(),
    ReshadeDetector(),
    InjectorToolDetector(),
    ConfigIniDetector(),
    MetaOnlyDetector(),
]


# ---------------------------------------------------------------------------
# Reglas de destino / capacidad (por adaptador + hints, no por nombre de juego)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterInstallRule:
    """Regla genérica ligada a un adapter_id, no a un título concreto."""

    adapter_id: str
    supported_families: frozenset[FormatFamily]
    dest_subdir_hint: str
    external_families: frozenset[FormatFamily] = frozenset()
    notes: str = ""


def default_adapter_rules() -> dict[str, AdapterInstallRule]:
    return {
        "ue4_paks_mods": AdapterInstallRule(
            "ue4_paks_mods",
            frozenset({FormatFamily.PAK}),
            "End/Content/Paks/~mods",
            frozenset(
                {
                    FormatFamily.MEDIA_MOVIE,
                    FormatFamily.RESHADE,
                    FormatFamily.INJECTOR_TOOL,
                    FormatFamily.SCRIPT_LUA,
                }
            ),
            "PAK → ~mods. Media/herramientas: canal aparte o externo.",
        ),
        "ue5_iostore_mods": AdapterInstallRule(
            "ue5_iostore_mods",
            frozenset({FormatFamily.PAK, FormatFamily.IOSTORE}),
            "Content/Paks/~mods",
            frozenset(
                {
                    FormatFamily.MEDIA_MOVIE,
                    FormatFamily.SCRIPT_LUA,
                    FormatFamily.INJECTOR_TOOL,
                    FormatFamily.RESHADE,
                }
            ),
            "IoStore completo → ~mods. Scripts/tools → externo.",
        ),
        "generic_folder": AdapterInstallRule(
            "generic_folder",
            frozenset({FormatFamily.PAK, FormatFamily.IOSTORE}),
            "",
            frozenset(
                {
                    FormatFamily.MEDIA_MOVIE,
                    FormatFamily.SCRIPT_LUA,
                    FormatFamily.INJECTOR_TOOL,
                    FormatFamily.RESHADE,
                }
            ),
            "Carpeta libre; sin destino confirmado automático.",
        ),
    }


# Plugin installer hints (patrones en index.js) — opcionales, solo lectura
_INSTALLER_PAT = re.compile(r"registerInstaller\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\d+)")


def read_plugin_installer_hints(vortex_game_id: str, roaming: Path | None = None) -> dict[str, str]:
    """Lee registerInstaller de plugins Vortex (RO). Claves genéricas, no títulos."""
    root = roaming if roaming is not None else vortex_roaming_root()
    if not root or not vortex_game_id:
        return {}
    plugins = root / "plugins"
    if not plugins.is_dir():
        return {}
    out: dict[str, str] = {}
    # Carpeta exacta, substring gameId, o id compactado dentro del nombre legible del plugin
    candidates = [plugins / vortex_game_id]
    gid_compact = re.sub(r"[^a-z0-9]", "", vortex_game_id.lower())
    try:
        for d in plugins.iterdir():
            if not d.is_dir():
                continue
            name_l = d.name.lower()
            folder_compact = re.sub(r"[^a-z0-9]", "", name_l)
            if vortex_game_id.lower() in name_l:
                candidates.append(d)
            elif gid_compact and len(gid_compact) >= 6 and gid_compact in folder_compact:
                candidates.append(d)
    except OSError:
        pass
    for d in candidates:
        idx = d / "index.js"
        if not idx.is_file():
            continue
        try:
            text = idx.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _INSTALLER_PAT.finditer(text):
            out[m.group(1)] = f"prio={m.group(2)}"
        # Señales de path
        if "queryModPath" in text:
            out["_queryModPath"] = "present"
        if "IO_STORE" in text or "ioStore" in text:
            out["_io_store"] = "present"
        if ".emov" in text.lower():
            out["_emov_ref"] = "present"
        break
    return out


def _read_readmes(root: Path, *, max_files: int = 3, max_chars: int = 400) -> list[str]:
    snippets: list[str] = []
    if not root.is_dir():
        return snippets
    found: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower() in README_NAMES or (
            p.suffix.lower() in DOC_SUFFIXES and "readme" in p.name.lower()
        ):
            found.append(p)
        if len(found) >= max_files:
            break
    for p in found:
        try:
            text = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            snippets.append(f"{p.name}: {text[:max_chars]}")
    return snippets


def _homolog_in_game(rel_name: str, game_root: Path | None) -> bool:
    """Presencia de homólogo por nombre en el árbol del juego (evidencia débil)."""
    if not game_root or not game_root.is_dir() or not rel_name:
        return False
    # Búsqueda limitada por nombre base (no copia por similitud)
    base = Path(rel_name).name
    if not base or len(base) < 4:
        return False
    try:
        for p in game_root.rglob(base):
            if p.is_file():
                return True
    except OSError:
        return False
    return False


def load_vortex_mods_index(
    vortex_game_id: str,
    roaming: Path | None = None,
) -> dict[str, dict]:
    """Índice persistent.mods[gameId] desde backup (una lectura)."""
    root = roaming if roaming is not None else vortex_roaming_root()
    backup = find_vortex_state_backup(root) if root else None
    if not backup or not backup.is_file():
        return {}
    try:
        data = json.loads(backup.read_text(encoding="utf-8"))
    except Exception:
        return {}
    mods = ((data.get("persistent") or {}).get("mods") or {}).get(vortex_game_id) or {}
    return dict(mods) if isinstance(mods, dict) else {}


def build_vortex_facts(
    *,
    vortex_game_id: str,
    mod_folder: str,
    plugin_hints: dict[str, str] | None = None,
    roaming: Path | None = None,
    mods_dest: Path | None = None,
    mods_index: dict[str, dict] | None = None,
    enabled_map: dict[str, bool] | None = None,
) -> VortexModFacts:
    pkg = package_folder_of(mod_folder)
    if mods_index is None:
        mods_index = load_vortex_mods_index(vortex_game_id, roaming=roaming)
    entry = dict(mods_index.get(pkg) or {})
    attrs = entry.get("attributes") or {}
    enabled_h = None
    if enabled_map is not None:
        enabled_h = enabled_map.get(pkg)
    else:
        snap = (
            probe_vortex_enable_state(vortex_game_id, roaming=roaming)
            if vortex_game_id
            else None
        )
        if snap and snap.has_historical_map:
            enabled_h = snap.enabled_map.get(pkg)
    facts = VortexModFacts(
        mod_id=str(entry.get("id") or pkg),
        state=str(entry.get("state") or ""),
        mod_type=str(entry.get("type") or ""),
        archive_id=str(entry.get("archiveId") or ""),
        installation_path=str(entry.get("installationPath") or ""),
        attributes_mod_id=str(attrs.get("modId") or attrs.get("fileId") or ""),
        attributes_file_id=str(attrs.get("fileId") or ""),
        enabled_historical=enabled_h,
        enabled_verified=None,  # LevelDB no leído
        need_to_deploy=None,
        deployment_manifest_found=False,
    )
    # Instalador: solo si plugin declara soporte explícito del formato
    hints = plugin_hints or {}
    if hints:
        # Heurística: primer installer con prio < 100
        named = [k for k in hints if not k.startswith("_")]
        if named:
            facts.installer_hint = f"{named[0]} ({hints[named[0]]})"
        if hints.get("_emov_ref") == "present":
            facts.notes.append("Plugin menciona .emov")
        else:
            facts.notes.append("Plugin sin referencia .emov observada")
    # Deploy manifest en destino ~mods (si se conoce)
    if mods_dest and mods_dest.is_dir():
        for name in ("vortex.deployment.json", "__vortex_deployment.json"):
            if (mods_dest / name).is_file():
                facts.deployment_manifest_found = True
                break
    if facts.state == "installed":
        facts.notes.append("state=installed ≠ archivos en destino del juego")
    if enabled_h is True:
        facts.notes.append("enabled en backup histórico ≠ deploy verificado")
    return facts


def _classify_capability(
    hits: list[FormatHit],
    rule: AdapterInstallRule | None,
    mc_has_installable: bool,
    adapter_id: str,
) -> tuple[InstallCapability, bool, bool, list[str], list[str]]:
    """
    Returns: capability, f7777_installable, apply_allowed, missing, manual
    apply_allowed solo True si ya hay instalables del adaptador (PAK/IoStore).
    """
    missing: list[str] = []
    manual: list[str] = []
    families = {h.family for h in hits}

    if not hits or families == {FormatFamily.EMPTY}:
        missing.append("Sin contenido analizable en staging")
        return InstallCapability.UNKNOWN, False, False, missing, manual

    if FormatFamily.ARCHIVE_META in families and len(families) == 1:
        missing.append("Solo metadatos; falta payload del mod")
        return InstallCapability.UNKNOWN, False, False, missing, manual

    supported = set(rule.supported_families) if rule else set()
    external = set(rule.external_families) if rule else set()

    # Instalables ya reconocidos por content_classify → confirmado para Apply existente
    if mc_has_installable and (FormatFamily.PAK in families or FormatFamily.IOSTORE in families):
        incomplete = any(
            h.family == FormatFamily.IOSTORE and h.confidence != EvidenceLevel.CONFIRMED
            for h in hits
        )
        if incomplete:
            missing.append("Completar trio IoStore .pak+.utoc+.ucas")
            return InstallCapability.PROBABLE, False, False, missing, manual
        return InstallCapability.CONFIRMED, True, True, missing, manual

    # Solo media
    if FormatFamily.MEDIA_MOVIE in families and not (
        FormatFamily.PAK in families or FormatFamily.IOSTORE in families
    ):
        if adapter_id == "ue4_paks_mods":
            # S42 existe plan EMOV separado; Apply PAK no aplica
            missing.append("Validar destino Movie con evidencia de homólogos / S42")
            manual.append(
                "Revisar informe EMOV/multidestino; no usar Apply PAK para .emov"
            )
            return InstallCapability.UNSUPPORTED, False, False, missing, manual
        if FormatFamily.MEDIA_MOVIE in external or True:
            missing.append("Sin instalador F7777 seguro para este medio en el adaptador actual")
            manual.append("Desplegar con la herramienta que gestione ese tipo de medio")
            return InstallCapability.EXTERNAL, False, False, missing, manual

    if FormatFamily.SCRIPT_LUA in families or FormatFamily.RESHADE in families:
        missing.append("Requiere runtime/herramienta externa (no Apply F7777)")
        manual.append("Instalar/activar con la herramienta externa identificada (p. ej. UE4SS / ReShade)")
        return InstallCapability.EXTERNAL, False, False, missing, manual

    if FormatFamily.INJECTOR_TOOL in families and FormatFamily.PAK not in families:
        missing.append("Destino de inyector no automatizado de forma segura")
        manual.append("Seguir README del autor; no sobrescribir binarios del juego sin backup")
        return InstallCapability.EXTERNAL, False, False, missing, manual

    if FormatFamily.CONFIG_INI in families:
        missing.append("Confirmar ruta exacta del .ini en el juego")
        return InstallCapability.PROBABLE, False, False, missing, manual

    if supported & families:
        missing.append("Formato parcialmente reconocido; falta procedimiento F7777")
        return InstallCapability.UNSUPPORTED, False, False, missing, manual

    missing.append("Faltan evidencias de destino y procedimiento")
    return InstallCapability.UNKNOWN, False, False, missing, manual


def investigate_mod(
    mod: ModEntry,
    *,
    adapter_id: str = "generic_folder",
    game_id: str = "",
    vortex_game_id: str = "",
    game_root: Path | None = None,
    mods_dest: Path | None = None,
    detectors: list[FormatDetector] | None = None,
    adapter_rules: dict[str, AdapterInstallRule] | None = None,
    plugin_hints: dict[str, str] | None = None,
    vortex_roaming: Path | None = None,
    load_vortex: bool = True,
    mods_index: dict[str, dict] | None = None,
    enabled_map: dict[str, bool] | None = None,
    check_homolog: bool = True,
) -> InvestigationReport:
    """Investiga un mod (solo lectura). Nunca muta disco ni habilita Apply nuevo."""
    stage = Path(mod.stage_path) if mod.stage_path else Path()
    payload_rels = list(getattr(mod, "payload_files", None) or [])
    # Preferir payload del inventario (S49) para no re-rglob en lotes grandes
    if payload_rels and stage.is_dir():
        files = [stage / rel for rel in payload_rels]
        files = [p for p in files if p.is_file()]
        rels = list(payload_rels)
        exts: dict[str, int] = {}
        for e in getattr(mod, "payload_exts", None) or []:
            exts[e] = exts.get(e, 0) + 1
        if not exts:
            exts = _ext_counts(files)
        # Contar .pak del inventario aunque collect_payload los incluya
        if mod.paks and ".pak" not in exts:
            exts[".pak"] = len(mod.paks)
    else:
        files = _collect_files(stage) if stage.is_dir() else []
        exts = _ext_counts(files)
        if not exts and getattr(mod, "payload_exts", None):
            for e in mod.payload_exts:
                exts[e] = exts.get(e, 0) + 1
        if mod.paks and ".pak" not in exts:
            exts[".pak"] = len(mod.paks)
        rels = []
        for p in files:
            try:
                rels.append(str(p.relative_to(stage)))
            except ValueError:
                rels.append(p.name)

    hints = plugin_hints
    if hints is None and vortex_game_id:
        hints = read_plugin_installer_hints(vortex_game_id, roaming=vortex_roaming)

    facts = VortexModFacts()
    if load_vortex and vortex_game_id:
        facts = build_vortex_facts(
            vortex_game_id=vortex_game_id,
            mod_folder=mod.folder,
            plugin_hints=hints,
            roaming=vortex_roaming,
            mods_dest=mods_dest,
            mods_index=mods_index,
            enabled_map=enabled_map,
        )

    ctx = InvestigationContext(
        mod=mod,
        stage_root=stage,
        adapter_id=adapter_id,
        game_id=game_id,
        vortex_game_id=vortex_game_id,
        files=files,
        ext_counts=exts,
        relative_paths=rels,
        game_root=game_root,
        mods_dest=mods_dest,
        vortex_facts=facts,
        plugin_hints=hints or {},
    )

    hits: list[FormatHit] = []
    for det in detectors or DEFAULT_DETECTORS:
        hit = det.detect(ctx)
        if hit is not None:
            hits.append(hit)
    if not hits:
        hits.append(
            FormatHit(
                FormatFamily.UNKNOWN,
                "detector_fallback",
                EvidenceLevel.WEAK,
                rels[:6],
                ["Ningún detector registró formato conocido"],
            )
        )

    rules = adapter_rules or default_adapter_rules()
    rule = rules.get(adapter_id) or rules.get("generic_folder")
    ad = get_adapter(adapter_id)

    mc = classify_mod(mod, adapter_id)
    cap, f7777_ok, apply_ok, missing, manual = _classify_capability(
        hits, rule, mc.has_installable, adapter_id
    )

    evidence: list[EvidenceItem] = []
    destinations: list[DestinationHypothesis] = []

    for h in hits:
        evidence.append(
            EvidenceItem(
                f"Formato {h.family.value} vía {h.detector_id}",
                h.confidence,
                "staging",
            )
        )

    # Destino PAK/IoStore desde adaptador (confirmado solo si apply_ok)
    if f7777_ok and (FormatFamily.PAK in {h.family for h in hits} or FormatFamily.IOSTORE in {h.family for h in hits}):
        hint = ad.suggest_mods_subdir or (rule.dest_subdir_hint if rule else "")
        destinations.append(
            DestinationHypothesis(
                hint or "(mods_dir de sesión)",
                EvidenceLevel.CONFIRMED,
                "Adaptador F7777 + archivos instalables clasificados",
                confirmed=True,
            )
        )
        evidence.append(
            EvidenceItem(
                "Instalables del adaptador presentes",
                EvidenceLevel.CONFIRMED,
                "adapter",
            )
        )

    # Media: destino probable solo con homólogo o plugin; nunca confirmed automático
    if FormatFamily.MEDIA_MOVIE in {h.family for h in hits}:
        media_files = [p for p in files if p.suffix.lower() in MEDIA_SUFFIXES]
        homolog = False
        if check_homolog and game_root is not None:
            for p in media_files[:5]:
                if _homolog_in_game(p.name, game_root):
                    homolog = True
                    evidence.append(
                        EvidenceItem(
                            f"Homólogo en juego: {p.name}",
                            EvidenceLevel.PROBABLE,
                            "game_homolog",
                        )
                    )
                    break
        if homolog:
            destinations.append(
                DestinationHypothesis(
                    "(carpeta Movies del juego — probable)",
                    EvidenceLevel.PROBABLE,
                    "Nombre homólogo en instalación; no confirma procedimiento F7777",
                    confirmed=False,
                )
            )
        elif check_homolog:
            missing.append("Sin homólogo observable en game_root para archivos media")
        if (hints or {}).get("_emov_ref") != "present":
            evidence.append(
                EvidenceItem(
                    "Extensión Vortex del juego no declara soporte .emov",
                    EvidenceLevel.CONFIRMED,
                    "plugin",
                )
            )

    if FormatFamily.SCRIPT_LUA in {h.family for h in hits}:
        destinations.append(
            DestinationHypothesis(
                "(runtime UE4SS / Mods — externo)",
                EvidenceLevel.PROBABLE,
                "Scripts Lua requieren herramienta externa",
                confirmed=False,
            )
        )

    readmes = _read_readmes(stage) if stage.is_dir() else []
    for sn in readmes:
        evidence.append(
            EvidenceItem("README presente", EvidenceLevel.WEAK, "readme")
        )

    # Manual confirmado solo con evidencia CONFIRMED suficiente + pasos claros
    manual_confirmed = False
    if cap == InstallCapability.EXTERNAL and any(
        e.level == EvidenceLevel.CONFIRMED for e in evidence
    ):
        # pasos manuales siguen orientativos salvo README + tool id
        manual_confirmed = bool(readmes) and cap == InstallCapability.EXTERNAL
        if not manual_confirmed:
            manual = [
                x + " (no confirmado: falta README/procedimiento verificable)"
                for x in manual
            ]

    # Vortex facts → evidencia
    if facts.state:
        evidence.append(
            EvidenceItem(
                f"Vortex state={facts.state}",
                EvidenceLevel.PROBABLE,
                "vortex_backup",
            )
        )
    for n in facts.notes:
        evidence.append(EvidenceItem(n, EvidenceLevel.WEAK, "vortex_backup"))

    human = cap in (
        InstallCapability.UNKNOWN,
        InstallCapability.UNSUPPORTED,
        InstallCapability.EXTERNAL,
        InstallCapability.PROBABLE,
    ) or bool(missing)

    # Seguridad: nunca promover probable→confirmed aquí
    for d in destinations:
        if d.level != EvidenceLevel.CONFIRMED:
            d.confirmed = False

    # Apply: solo lo ya soportado por adaptador PAK/IoStore
    if not f7777_ok:
        apply_ok = False

    # payload summary from inventory helper
    _, ext_list = package_payload_summary(mod)

    return InvestigationReport(
        mod_folder=mod.folder,
        game_id=game_id,
        vortex_game_id=vortex_game_id,
        identity_ok=True,
        display_name=mod.nexus_mod_name or mod.name or mod.folder,
        capability=cap,
        formats=hits,
        destinations=destinations,
        evidence=evidence,
        vortex=facts,
        payload_exts=exts,
        readme_snippets=readmes,
        missing_steps=missing,
        manual_steps=manual,
        manual_confirmed=manual_confirmed,
        apply_allowed=apply_ok,
        f7777_installable=f7777_ok,
        human_required=human,
        notes=[
            "Identidad del mod ≠ capacidad de instalación.",
            "S49 no altera Apply ni destinos reales.",
        ]
        + ([f"exts inventario: {','.join(ext_list)}"] if ext_list else []),
    )


def investigate_mods(
    mods: list[ModEntry],
    **kwargs,
) -> dict[str, InvestigationReport]:
    """Investiga un lote reutilizando índice Vortex y mapa enable (RO)."""
    vortex_game_id = kwargs.get("vortex_game_id") or ""
    roaming = kwargs.get("vortex_roaming")
    load_vortex = kwargs.get("load_vortex", True)
    mods_index = kwargs.pop("mods_index", None)
    enabled_map = kwargs.pop("enabled_map", None)
    if load_vortex and vortex_game_id and mods_index is None:
        mods_index = load_vortex_mods_index(vortex_game_id, roaming=roaming)
    if load_vortex and vortex_game_id and enabled_map is None:
        snap = probe_vortex_enable_state(vortex_game_id, roaming=roaming)
        enabled_map = dict(snap.enabled_map) if snap and snap.has_historical_map else {}
    if kwargs.get("plugin_hints") is None and vortex_game_id:
        kwargs["plugin_hints"] = read_plugin_installer_hints(
            vortex_game_id, roaming=roaming
        )
    out: dict[str, InvestigationReport] = {}
    for m in mods:
        exts = set(getattr(m, "payload_exts", None) or [])
        has_media = bool(exts & MEDIA_SUFFIXES)
        out[m.folder] = investigate_mod(
            m,
            mods_index=mods_index,
            enabled_map=enabled_map,
            check_homolog=has_media,
            **kwargs,
        )
    return out


def is_f7777_unknown(report: InvestigationReport) -> bool:
    """True si F7777 no puede instalar de forma confirmada (sigue siendo inventariable)."""
    return report.capability != InstallCapability.CONFIRMED


def summarize_by_game(
    reports: dict[str, InvestigationReport],
) -> dict[str, dict[str, int]]:
    """Agrega conteos por game_id y capability."""
    out: dict[str, dict[str, int]] = {}
    for r in reports.values():
        g = r.game_id or r.vortex_game_id or "?"
        bucket = out.setdefault(g, {c.value: 0 for c in InstallCapability})
        bucket["total"] = bucket.get("total", 0) + 1
        bucket[r.capability.value] = bucket.get(r.capability.value, 0) + 1
        if is_f7777_unknown(r):
            bucket["desconocidos_o_no_confirmados"] = (
                bucket.get("desconocidos_o_no_confirmados", 0) + 1
            )
    return out


def scan_vortex_game_staging(
    vortex_game_id: str,
    *,
    adapter_id: str = "generic_folder",
    game_id: str = "",
    game_root: Path | None = None,
    mods_dest: Path | None = None,
    only_unknown: bool = False,
) -> list[InvestigationReport]:
    """Inventario RO de un staging Vortex + investigación. No escribe nada."""
    from .inventory import scan_staging

    stage = discover_vortex_mods(vortex_game_id)
    if not stage.is_dir():
        return []
    mods = scan_staging(stage)
    hints = read_plugin_installer_hints(vortex_game_id)
    reports = []
    for m in mods:
        rep = investigate_mod(
            m,
            adapter_id=adapter_id,
            game_id=game_id or vortex_game_id,
            vortex_game_id=vortex_game_id,
            game_root=game_root,
            mods_dest=mods_dest,
            plugin_hints=hints,
        )
        if only_unknown and not is_f7777_unknown(rep):
            continue
        reports.append(rep)
    return reports
