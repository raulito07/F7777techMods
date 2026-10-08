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

S11 — catálogo de paquetes comprimidos ↔ staging (solo lectura de rutas reales).
No inventa correspondencias; estados ambiguos/no encontrados explícitos.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .hash_cache import sha256_file
from .inventory import ModEntry, nexus_id_from_folder, short_name

ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz"}
SKIP_STAGE = {"thumbs.db", "desktop.ini", ".ds_store"}


class ArchiveLinkStatus(str, Enum):
    VERIFIED = "ARCHIVO VERIFICADO"
    NOT_FOUND = "ARCHIVO NO ENCONTRADO"
    AMBIGUOUS = "CORRESPONDENCIA AMBIGUA"
    STAGING_ONLY = "SOLO STAGING"
    DOWNLOAD_ONLY = "SOLO DESCARGA"
    SPECIAL_INSTALLER = "REQUIERE INSTALADOR ESPECIAL"


@dataclass
class PackagedFile:
    path: str
    name: str
    suffix: str
    size: int
    sha256: str = ""
    nexus_id: str | None = None


@dataclass
class ModArchiveEntry:
    folder: str
    name: str
    nexus_id: str | None
    archive_path: str = ""
    archive_format: str = ""
    archive_sha256: str = ""
    archive_size: int = 0
    staging_files: list[str] = field(default_factory=list)
    staging_logical_size: int = 0
    status: str = ArchiveLinkStatus.STAGING_ONLY.value
    variants: list[str] = field(default_factory=list)
    pak_elegido: str = ""
    match_reason: str = ""
    recoverable: bool | None = None
    recoverable_note: str = ""
    special_installer: bool = False
    # S12
    package_kind: str = ""  # ORIGINAL_VORTEX | ARCHIVO_PROPIO
    match_grade: str = ""  # VERIFICADA | PROBABLE | AMBIGUA | NO ENCONTRADA
    own_archive_path: str = ""
    own_archive_sha256: str = ""
    mod_id: str = ""
    lifecycle: str = "EXTRAIDO"  # COMPRIMIDO|VERIFICADO|ARCHIVADO|EXTRAIDO|NO DISPONIBLE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameArchiveCatalog:
    game_id: str
    generated_at: str
    downloads_dir: str
    stage_dir: str
    archive_root_config: str = ""
    packages: list[PackagedFile] = field(default_factory=list)
    mods: list[ModArchiveEntry] = field(default_factory=list)
    download_only: list[PackagedFile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "downloads_dir": self.downloads_dir,
            "stage_dir": self.stage_dir,
            "archive_root_config": self.archive_root_config,
            "packages": [asdict(p) for p in self.packages],
            "mods": [m.to_dict() for m in self.mods],
            "download_only": [asdict(p) for p in self.download_only],
            "notes": list(self.notes),
            "counts": {
                "packages": len(self.packages),
                "mods": len(self.mods),
                "verified": sum(
                    1 for m in self.mods if m.status == ArchiveLinkStatus.VERIFIED.value
                ),
                "ambiguous": sum(
                    1 for m in self.mods if m.status == ArchiveLinkStatus.AMBIGUOUS.value
                ),
                "staging_only": sum(
                    1 for m in self.mods if m.status == ArchiveLinkStatus.STAGING_ONLY.value
                ),
                "special": sum(
                    1
                    for m in self.mods
                    if m.status == ArchiveLinkStatus.SPECIAL_INSTALLER.value
                ),
                "download_only": len(self.download_only),
            },
        }


def _nexus_from_name(name: str) -> str | None:
    return nexus_id_from_folder(name) or nexus_id_from_folder(Path(name).stem)


def _norm_key(s: str) -> str:
    s = short_name(Path(s).stem if "." in Path(s).name else s)
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return s


def list_download_packages(downloads_dir: Path | None) -> list[PackagedFile]:
    out: list[PackagedFile] = []
    if downloads_dir is None or not downloads_dir.is_dir():
        return out
    for f in sorted(downloads_dir.iterdir(), key=lambda p: p.name.lower()):
        if not f.is_file():
            continue
        suf = f.suffix.lower()
        if suf not in ARCHIVE_SUFFIXES:
            continue
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        out.append(
            PackagedFile(
                path=str(f),
                name=f.name,
                suffix=suf,
                size=size,
                nexus_id=_nexus_from_name(f.name),
            )
        )
    return out


def _staging_file_list(stage_path: Path) -> tuple[list[str], int]:
    files: list[str] = []
    total = 0
    if not stage_path.is_dir():
        return files, 0
    for f in stage_path.rglob("*"):
        if not f.is_file():
            continue
        if f.name.lower() in SKIP_STAGE or f.name.lower().startswith("vortex"):
            continue
        try:
            rel = f.relative_to(stage_path).as_posix()
            total += f.stat().st_size
            files.append(rel)
        except OSError:
            continue
    return sorted(files), total


def _looks_special_installer(staging_files: list[str], folder: str) -> bool:
    blob = " ".join(staging_files).lower() + " " + folder.lower()
    hints = (
        "setup.exe",
        "installer",
        "fomod",
        "modorganizer",
        ".exe",
        "reshade",
        "3dmigoto",
        "d3dx.ini",
        "ffviihook",
    )
    return any(h in blob for h in hints)


def _candidate_packages(
    mod: ModEntry, packages: list[PackagedFile]
) -> list[tuple[PackagedFile, str]]:
    """Candidatos con motivo; no inventa si no hay señal fuerte."""
    cands: list[tuple[PackagedFile, str]] = []
    nid = mod.nexus_id or nexus_id_from_folder(mod.folder)
    folder_key = _norm_key(mod.folder)
    name_key = _norm_key(mod.name)
    for p in packages:
        if nid and p.nexus_id and p.nexus_id == nid:
            cands.append((p, f"nexus_id={nid}"))
            continue
        stem_key = _norm_key(p.name)
        if stem_key and stem_key == folder_key:
            cands.append((p, "stem==folder"))
            continue
        if stem_key and name_key and stem_key == name_key and len(name_key) >= 8:
            cands.append((p, "stem==short_name"))
    # dedupe by path
    seen: set[str] = set()
    uniq: list[tuple[PackagedFile, str]] = []
    for p, reason in cands:
        if p.path in seen:
            continue
        seen.add(p.path)
        uniq.append((p, reason))
    return uniq


def build_catalog(
    *,
    game_id: str,
    mods: list[ModEntry],
    downloads_dir: Path | None,
    stage_dir: Path | None,
    archive_root_config: str = "",
    hash_packages: bool = False,
) -> GameArchiveCatalog:
    """Construye catálogo. hash_packages=True calcula SHA de cada ZIP (más lento)."""
    packages = list_download_packages(downloads_dir)
    if hash_packages:
        for p in packages:
            try:
                p.sha256 = sha256_file(Path(p.path))
            except OSError:
                p.sha256 = ""

    cat = GameArchiveCatalog(
        game_id=game_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        downloads_dir=str(downloads_dir or ""),
        stage_dir=str(stage_dir or ""),
        archive_root_config=archive_root_config,
        packages=packages,
        notes=[
            "Correspondencias solo por nexus_id / stem exacto; no por similitud difusa.",
            "ARCHIVO VERIFICADO / match VERIFICADA requieren comprobación de contenido.",
            "PROBABLE nunca se eleva a VERIFICADA sin prueba (S12).",
            "ORIGINAL_VORTEX vs ARCHIVO_PROPIO son orígenes distintos.",
            "No se han movido ni borrado archivos reales.",
        ],
    )

    from .own_archive import make_mod_id  # import local evita ciclo al cargar

    matched_paths: set[str] = set()
    for m in mods:
        files, logical = _staging_file_list(Path(m.stage_path))
        entry = ModArchiveEntry(
            folder=m.folder,
            name=m.name,
            nexus_id=m.nexus_id or nexus_id_from_folder(m.folder),
            staging_files=files,
            staging_logical_size=logical,
            variants=list(m.paks),
            pak_elegido=m.pak_elegido or "",
            mod_id=make_mod_id(game_id, m.folder),
            lifecycle="EXTRAIDO",
            match_grade="NO ENCONTRADA",
        )
        if _looks_special_installer(files, m.folder):
            entry.special_installer = True

        cands = _candidate_packages(m, packages)
        if not cands:
            entry.status = (
                ArchiveLinkStatus.SPECIAL_INSTALLER.value
                if entry.special_installer
                else ArchiveLinkStatus.STAGING_ONLY.value
            )
            entry.match_reason = "sin paquete candidato verificable"
            entry.match_grade = "NO ENCONTRADA"
        elif len(cands) > 1:
            entry.status = ArchiveLinkStatus.AMBIGUOUS.value
            entry.match_grade = "AMBIGUA"
            entry.match_reason = "candidatos: " + "; ".join(
                f"{Path(p.path).name} ({r})" for p, r in cands[:5]
            )
            # no asignar archive_path hasta desambiguar
        else:
            pkg, reason = cands[0]
            entry.archive_path = pkg.path
            entry.archive_format = pkg.suffix
            entry.archive_size = pkg.size
            entry.archive_sha256 = pkg.sha256
            entry.match_reason = reason
            entry.package_kind = "ORIGINAL_VORTEX"
            # provisional PROBABLE; verify/content → VERIFICADA
            entry.status = ArchiveLinkStatus.NOT_FOUND.value
            entry.match_grade = "PROBABLE"
            matched_paths.add(pkg.path)
            if entry.special_installer:
                entry.status = ArchiveLinkStatus.SPECIAL_INSTALLER.value
                entry.match_grade = "NO ENCONTRADA"

        cat.mods.append(entry)

    for p in packages:
        if p.path not in matched_paths:
            # ¿alguien lo reclamó en ambiguous? no contar como matched
            claimed = any(m.archive_path == p.path for m in cat.mods)
            if not claimed:
                cat.download_only.append(p)

    return cat


def save_catalog(cat: GameArchiveCatalog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cat.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_catalog(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
