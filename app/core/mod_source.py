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

S15 — procedencia de mods (STAGING_VORTEX | WORK_LIBRARY) y revalidación pre-Apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .hash_cache import sha256_file
from .inventory import ModEntry
from .own_archive import read_own_manifest
from .work_library import WorkLibraryIndex

SOURCE_STAGING_VORTEX = "STAGING_VORTEX"
SOURCE_WORK_LIBRARY = "WORK_LIBRARY"
VALID_SOURCES = frozenset({SOURCE_STAGING_VORTEX, SOURCE_WORK_LIBRARY})


@dataclass
class SourceValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_source(kind: str | None) -> str:
    k = (kind or SOURCE_STAGING_VORTEX).strip().upper()
    if k not in VALID_SOURCES:
        return SOURCE_STAGING_VORTEX
    return k


def annotate_staging_mods(mods: list[ModEntry]) -> None:
    """Marca mods escaneados de staging Vortex (no mezcla work)."""
    for m in mods:
        if not getattr(m, "source_kind", None) or m.source_kind not in VALID_SOURCES:
            m.source_kind = SOURCE_STAGING_VORTEX
        if not m.mod_id:
            # mod_id estable opcional desde folder+ruta
            from .own_archive import make_mod_id

            # game_id desconocido aquí → solo folder hash parcial vía path
            m.mod_id = m.mod_id or ""


def enrich_from_work_index(
    mods: list[ModEntry],
    idx: WorkLibraryIndex | None,
    *,
    stage_root: Path | None,
) -> list[ModEntry]:
    """
    Enriquece mods Vortex con estado work/archivo y añade mods solo-work.
    No cambia silenciosamente stage_path de un mod Vortex a work.
    """
    if idx is None:
        return mods
    by_folder = {m.folder: m for m in mods}
    out = list(mods)
    for rec in idx.mods.values():
        wp = Path(rec.work_path)
        if not wp.is_dir():
            continue
        if rec.folder in by_folder:
            m = by_folder[rec.folder]
            # metadatos de archivo; no sustituir stage_path salvo que ya sea WORK
            m.archive_path = m.archive_path or rec.archive_path
            m.archive_content_sha256 = m.archive_content_sha256 or rec.content_sha256
            m.archive_zip_sha256 = m.archive_zip_sha256 or rec.zip_sha256
            m.mod_id = m.mod_id or rec.mod_id
            m.work_extracted = True
            if m.source_kind == SOURCE_WORK_LIBRARY:
                m.stage_path = rec.work_path
            continue
        # solo en work — nuevo ModEntry
        from .work_library import work_record_to_mod_entry

        wm = work_record_to_mod_entry(rec, usar=False)
        out.append(wm)
    return out


def switch_mod_to_work_source(m: ModEntry, idx: WorkLibraryIndex) -> list[str]:
    """Cambia explícitamente un mod a fuente WORK_LIBRARY si está extraído."""
    errs: list[str] = []
    rec = None
    for r in idx.mods.values():
        if r.folder == m.folder or (m.mod_id and r.mod_id == m.mod_id):
            rec = r
            break
    if rec is None:
        return ["mod no extraído en biblioteca de trabajo"]
    if not Path(rec.work_path).is_dir():
        return ["ruta work inexistente"]
    m.source_kind = SOURCE_WORK_LIBRARY
    m.stage_path = rec.work_path
    m.mod_id = rec.mod_id
    m.archive_path = rec.archive_path
    m.archive_content_sha256 = rec.content_sha256
    m.archive_zip_sha256 = rec.zip_sha256
    m.work_extracted = True
    if rec.pak_elegido:
        m.pak_elegido = rec.pak_elegido
    if rec.variants:
        m.paks = list(rec.variants)
        m.multi = len(m.paks) > 1
    return errs


def validate_mod_source(
    m: ModEntry,
    *,
    game_id: str,
    stage_root: Path | None,
    work_root: Path | None,
) -> SourceValidation:
    """Valida procedencia y correspondencia ZIP↔work antes de instalar."""
    v = SourceValidation(ok=True)
    kind = normalize_source(getattr(m, "source_kind", None))
    m.source_kind = kind
    root = Path(m.stage_path) if m.stage_path else None
    if root is None or not root.is_dir():
        v.ok = False
        v.errors.append(f"{m.folder}: origen inexistente ({m.stage_path})")
        return v

    if kind == SOURCE_STAGING_VORTEX:
        if stage_root and stage_root.exists():
            try:
                root.resolve().relative_to(stage_root.resolve())
            except ValueError:
                v.ok = False
                v.errors.append(
                    f"{m.folder}: marcado STAGING_VORTEX pero ruta fuera de staging"
                )
        if work_root and work_root.exists():
            try:
                root.resolve().relative_to(work_root.resolve())
                v.ok = False
                v.errors.append(
                    f"{m.folder}: ruta está en WORK_LIBRARY pero fuente=STAGING_VORTEX "
                    "(mezcla silenciosa bloqueada)"
                )
            except ValueError:
                pass
        return v

    # WORK_LIBRARY
    if work_root and work_root.exists():
        try:
            root.resolve().relative_to(work_root.resolve())
        except ValueError:
            v.ok = False
            v.errors.append(
                f"{m.folder}: marcado WORK_LIBRARY pero ruta fuera de work_library"
            )
            return v
    if stage_root and stage_root.exists():
        try:
            root.resolve().relative_to(stage_root.resolve())
            v.ok = False
            v.errors.append(
                f"{m.folder}: ruta en staging Vortex con fuente WORK_LIBRARY "
                "(mezcla silenciosa bloqueada)"
            )
            return v
        except ValueError:
            pass

    arch = Path(m.archive_path) if m.archive_path else None
    if not arch or not arch.is_file():
        v.ok = False
        v.errors.append(
            f"{m.folder}: WORK_LIBRARY sin ARCHIVO_PROPIO accesible — "
            "revalidar/restaurar desde ZIP"
        )
        return v

    man, errs = read_own_manifest(arch)
    if man is None:
        v.ok = False
        v.errors.append(f"{m.folder}: manifiesto ZIP inválido: {'; '.join(errs[:2])}")
        return v
    if man.game_id != game_id:
        v.ok = False
        v.errors.append(
            f"{m.folder}: ZIP de otro juego ({man.game_id} ≠ {game_id})"
        )
        return v
    if m.mod_id and man.mod_id != m.mod_id:
        v.ok = False
        v.errors.append(f"{m.folder}: mod_id no coincide con ZIP")
        return v

    try:
        cur_zip = sha256_file(arch)
    except OSError as e:
        v.ok = False
        v.errors.append(f"{m.folder}: no se pudo hashear ZIP: {e}")
        return v
    if m.archive_zip_sha256 and cur_zip != m.archive_zip_sha256:
        v.ok = False
        v.errors.append(
            f"{m.folder}: ZIP modificado desde el registro — "
            "bloquear instalación hasta nueva verificación"
        )
        return v
    if m.archive_content_sha256 and man.content_sha256 != m.archive_content_sha256:
        v.ok = False
        v.errors.append(
            f"{m.folder}: content_sha256 del ZIP no coincide con el registro"
        )
        return v

    # correspondencia contenido work ↔ manifiesto (archivos críticos)
    for ent in man.files:
        if not ent.path.lower().endswith((".pak", ".utoc", ".ucas", ".ini", ".txt")):
            continue
        got = root / ent.path
        if not got.is_file():
            v.ok = False
            v.errors.append(f"{m.folder}: falta en work: {ent.path}")
            continue
        try:
            if sha256_file(got) != ent.sha256:
                v.ok = False
                v.errors.append(
                    f"{m.folder}: hash distinto en work vs ZIP: {ent.path}"
                )
        except OSError as e:
            v.ok = False
            v.errors.append(f"{m.folder}: no se pudo hashear {ent.path}: {e}")

    # actualizar sha zip actual si faltaba
    if not m.archive_zip_sha256:
        m.archive_zip_sha256 = cur_zip
    if not m.archive_content_sha256:
        m.archive_content_sha256 = man.content_sha256
    if not m.mod_id:
        m.mod_id = man.mod_id
    return v


def validate_mods_for_apply(
    mods: list[ModEntry],
    *,
    game_id: str,
    stage_root: Path | None,
    work_root: Path | None,
    only_usar: bool = True,
) -> SourceValidation:
    """Revalida todos los mods del plan (usar=True por defecto)."""
    agg = SourceValidation(ok=True)
    seen_paths: dict[str, str] = {}
    for m in mods:
        if only_usar and not m.usar:
            continue
        kind = normalize_source(getattr(m, "source_kind", None))
        key = str(Path(m.stage_path).resolve()) if m.stage_path else ""
        if key and key in seen_paths and seen_paths[key] != kind:
            agg.ok = False
            agg.errors.append(
                f"mezcla de fuentes en la misma ruta: {key} "
                f"({seen_paths[key]} vs {kind})"
            )
        if key:
            seen_paths[key] = kind
        one = validate_mod_source(
            m, game_id=game_id, stage_root=stage_root, work_root=work_root
        )
        if not one.ok:
            agg.ok = False
            agg.errors.extend(one.errors)
        agg.warnings.extend(one.warnings)
    return agg
