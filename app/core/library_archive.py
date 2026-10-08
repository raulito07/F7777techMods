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

S12 — preparación por lotes de biblioteca comprimida (plan + demo temp).
No borra staging ni mueve Downloads Vortex.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .archive_catalog import GameArchiveCatalog, ModArchiveEntry
from .archive_match import MatchGrade, PackageKind
from .inventory import ModEntry
from .own_archive import (
    CreateOwnArchiveResult,
    create_own_archive,
    is_archive_root_available,
)

ProgressCb = Callable[[str, int, int], None]
CancelCb = Callable[[], bool]


@dataclass
class LibraryPrepRow:
    folder: str
    name: str
    mod_id: str
    staging_logical: int
    has_original_vortex: bool
    match_grade: str
    needs_own_archive: bool
    blocked: bool
    block_reason: str
    estimated_zip: int | None = None  # None = no prometer


@dataclass
class LibraryPrepPlan:
    game_id: str
    generated_at: str
    archive_dir: str
    archive_dir_available: bool
    archive_dir_note: str
    free_bytes: int | None
    rows: list[LibraryPrepRow] = field(default_factory=list)
    total_staging_logical: int = 0
    need_own_count: int = 0
    have_original_verified: int = 0
    blocked_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "archive_dir": self.archive_dir,
            "archive_dir_available": self.archive_dir_available,
            "archive_dir_note": self.archive_dir_note,
            "free_bytes": self.free_bytes,
            "total_staging_logical": self.total_staging_logical,
            "need_own_count": self.need_own_count,
            "have_original_verified": self.have_original_verified,
            "blocked_count": self.blocked_count,
            "notes": list(self.notes),
            "rows": [asdict(r) for r in self.rows],
        }


@dataclass
class ArchiveHistoryEntry:
    at: str
    game_id: str
    mod_id: str
    folder: str
    action: str
    path: str
    ok: bool
    detail: str
    zip_size: int = 0
    logical_bytes: int = 0
    elapsed_s: float = 0.0


def prepare_library_plan(
    cat: GameArchiveCatalog,
    *,
    folders: Iterable[str] | None = None,
    archive_dir: str = "",
) -> LibraryPrepPlan:
    """Plan de preparación. No comprime. No promete ratio de compresión."""
    ok_disk, note = is_archive_root_available(archive_dir) if archive_dir else (False, "no configurada")
    free = None
    if ok_disk:
        try:
            import shutil

            free = shutil.disk_usage(str(Path(archive_dir))).free
        except OSError:
            free = None

    want = set(folders) if folders is not None else None
    plan = LibraryPrepPlan(
        game_id=cat.game_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        archive_dir=archive_dir or "",
        archive_dir_available=ok_disk,
        archive_dir_note=note,
        free_bytes=free,
        notes=[
            "S12: plan informativo. Compresión masiva real no autorizada.",
            "Demos de ARCHIVO_PROPIO solo en directorios temporales.",
            "No se promete porcentaje de compresión sin medición.",
            "Disco desconectado ≠ archivo perdido (ruta queda en catálogo).",
        ],
    )

    for entry in cat.mods:
        if want is not None and entry.folder not in want:
            continue
        grade = entry.match_grade or MatchGrade.NO_ENCONTRADA.value
        has_verified_original = (
            grade == MatchGrade.VERIFICADA.value and bool(entry.archive_path)
        )
        has_own = bool(entry.own_archive_path and Path(entry.own_archive_path).is_file())
        needs_own = not has_verified_original and not has_own
        blocked = False
        reasons: list[str] = []
        if entry.special_installer:
            blocked = True
            reasons.append("instalador especial")
        if grade == MatchGrade.AMBIGUA.value and not has_own:
            # puede crear propio; no bloquea creación propia
            pass
        if not entry.staging_files:
            blocked = True
            reasons.append("staging vacío")

        row = LibraryPrepRow(
            folder=entry.folder,
            name=entry.name,
            mod_id=entry.mod_id,
            staging_logical=entry.staging_logical_size,
            has_original_vortex=bool(entry.archive_path),
            match_grade=grade,
            needs_own_archive=needs_own and not blocked,
            blocked=blocked,
            block_reason="; ".join(reasons),
            estimated_zip=None,
        )
        plan.rows.append(row)
        plan.total_staging_logical += entry.staging_logical_size
        if row.needs_own_archive:
            plan.need_own_count += 1
        if has_verified_original:
            plan.have_original_verified += 1
        if blocked:
            plan.blocked_count += 1

    if free is not None and plan.total_staging_logical > free:
        plan.notes.append(
            f"Espacio libre ({free}) menor que staging lógico "
            f"({plan.total_staging_logical}); el lote completo no cabe sin otro volumen."
        )
    return plan


def format_library_plan(plan: LibraryPrepPlan) -> str:
    def fmt(n: int) -> str:
        x = float(n)
        for u in ("B", "KiB", "MiB", "GiB", "TiB"):
            if x < 1024 or u == "TiB":
                return f"{x:.2f} {u}"
            x /= 1024
        return str(n)

    lines = [
        f"=== Preparar archivo de biblioteca — {plan.game_id} ===",
        f"Generado: {plan.generated_at}",
        f"Carpeta archivo: {plan.archive_dir or '(no)'} — "
        f"{'OK' if plan.archive_dir_available else 'NO DISPONIBLE'}: {plan.archive_dir_note}",
        f"Libre: {fmt(plan.free_bytes) if plan.free_bytes is not None else 'n/d'}",
        f"Mods en plan: {len(plan.rows)}",
        f"Staging lógico total: {fmt(plan.total_staging_logical)}",
        f"Originales VERIFICADOS: {plan.have_original_verified}",
        f"Requieren ARCHIVO_PROPIO: {plan.need_own_count}",
        f"Bloqueados: {plan.blocked_count}",
        "",
        "Tamaño comprimido esperado: no estimado (medir por demo).",
        "",
    ]
    for n in plan.notes:
        lines.append(f"! {n}")
    lines.append("")
    lines.append("Muestra (requieren propio):")
    for r in [x for x in plan.rows if x.needs_own_archive][:40]:
        lines.append(f"  • {r.name} — {fmt(r.staging_logical)} — grade={r.match_grade}")
    lines.append("")
    lines.append("Muestra (bloqueados):")
    for r in [x for x in plan.rows if x.blocked][:20]:
        lines.append(f"  ✗ {r.name} — {r.block_reason}")
    return "\n".join(lines)


def load_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("entries") or [])
    except Exception:
        return []


def append_history(path: Path, entry: ArchiveHistoryEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = load_history(path)
    entries.append(asdict(entry))
    # acotar
    entries = entries[-500:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"version": 1, "entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def create_demo_own_archives(
    *,
    game_id: str,
    mods: list[ModEntry],
    cat: GameArchiveCatalog,
    stage_root: Path,
    demo_dir: Path,
    folders: list[str] | None = None,
    limit: int = 3,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
    history_path: Path | None = None,
) -> tuple[list[CreateOwnArchiveResult], str]:
    """
    Crea ARCHIVO_PROPIO de demostración SOLO en demo_dir (temporal/local data).
    No escribe en Downloads Vortex. No borra staging.
    """
    by_folder = {m.folder: m for m in mods}
    entries_by = {e.folder: e for e in cat.mods}
    selected: list[str] = []
    if folders:
        selected = list(folders)[:limit]
    else:
        # priorizar sin original VERIFICADO
        for e in cat.mods:
            if e.special_installer:
                continue
            if e.match_grade == MatchGrade.VERIFICADA.value:
                continue
            if e.own_archive_path and Path(e.own_archive_path).is_file():
                continue
            if not e.staging_files:
                continue
            selected.append(e.folder)
            if len(selected) >= limit:
                break

    results: list[CreateOwnArchiveResult] = []
    lines = [
        f"Demo ARCHIVO_PROPIO → {demo_dir}",
        f"Límite: {limit}. Staging intacto. Vortex intacto.",
        "",
    ]
    demo_dir.mkdir(parents=True, exist_ok=True)
    n = len(selected)
    for i, folder in enumerate(selected):
        if cancel and cancel():
            lines.append("CANCELADO por el usuario.")
            break
        mod = by_folder.get(folder)
        if not mod:
            lines.append(f"SKIP {folder}: no en memoria")
            continue
        if progress:
            progress(f"mod {folder[:40]}", i + 1, n)
        t0 = time.perf_counter()
        r = create_own_archive(
            game_id=game_id,
            mod=mod,
            stage_root=stage_root,
            dest_dir=demo_dir,
            progress=None,
            cancel=cancel,
        )
        results.append(r)
        ent = entries_by.get(folder)
        if r.ok and ent is not None:
            ent.own_archive_path = r.published_path
            ent.own_archive_sha256 = r.zip_sha256
            ent.package_kind = PackageKind.ARCHIVO_PROPIO.value
            ent.mod_id = r.mod_id
            ent.lifecycle = "VERIFICADO"
            ent.recoverable = True
            ent.recoverable_note = "ARCHIVO_PROPIO verificado en sandbox (demo S12)"
        lines.append(
            f"{'OK' if r.ok else 'FAIL'} {folder}: "
            f"{r.published_path or '; '.join(r.errors[:2])} "
            f"({r.elapsed_s:.2f}s, zip={r.zip_size})"
        )
        if history_path is not None:
            append_history(
                history_path,
                ArchiveHistoryEntry(
                    at=datetime.now().isoformat(timespec="seconds"),
                    game_id=game_id,
                    mod_id=r.mod_id or (ent.mod_id if ent else ""),
                    folder=folder,
                    action="create_own_demo",
                    path=r.published_path,
                    ok=r.ok,
                    detail="; ".join(r.errors) if not r.ok else "publicado tras verify",
                    zip_size=r.zip_size,
                    logical_bytes=r.logical_bytes,
                    elapsed_s=time.perf_counter() - t0,
                ),
            )
    return results, "\n".join(lines)


def attach_own_archives_from_dir(
    cat: GameArchiveCatalog, own_dir: Path | None
) -> int:
    """Asocia ZIPs propios existentes (por mod_id.zip) sin inventar matches Vortex."""
    if own_dir is None or not own_dir.is_dir():
        return 0
    n = 0
    for entry in cat.mods:
        if not entry.mod_id:
            continue
        cand = own_dir / f"{entry.mod_id}.zip"
        if cand.is_file():
            entry.own_archive_path = str(cand)
            if not entry.package_kind:
                entry.package_kind = PackageKind.ARCHIVO_PROPIO.value
            n += 1
    return n
