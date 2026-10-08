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

S13 — trabajo de archivado REAL por lotes (persistente, reanudable).
No borra staging. No toca Vortex/Downloads.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .archive_catalog import GameArchiveCatalog, ModArchiveEntry
from .inventory import ModEntry
from .library_archive import ArchiveHistoryEntry, append_history
from .own_archive import (
    create_own_archive,
    is_archive_root_available,
    make_mod_id,
    validate_archive_destination,
    verify_published_own_archive,
)

LIBRARY_MARKER = ".sgm_library.json"
JOB_FILENAME = "archive_job.json"

ProgressCb = Callable[[str, int, int], None]
CancelCb = Callable[[], bool]

STATUS_PENDING = "PENDIENTE"
STATUS_COMPRESSING = "COMPRIMIENDO"
STATUS_VERIFYING = "VERIFICANDO"
STATUS_OK = "ARCHIVADO VERIFICADO"
STATUS_ERROR = "ERROR"
STATUS_BLOCKED = "BLOQUEADO"


@dataclass
class JobItem:
    folder: str
    name: str
    mod_id: str
    status: str = STATUS_PENDING
    path: str = ""
    zip_sha256: str = ""
    content_sha256: str = ""
    zip_size: int = 0
    logical_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JobItem":
        return cls(
            folder=str(d.get("folder") or ""),
            name=str(d.get("name") or ""),
            mod_id=str(d.get("mod_id") or ""),
            status=str(d.get("status") or STATUS_PENDING),
            path=str(d.get("path") or ""),
            zip_sha256=str(d.get("zip_sha256") or ""),
            content_sha256=str(d.get("content_sha256") or ""),
            zip_size=int(d.get("zip_size") or 0),
            logical_bytes=int(d.get("logical_bytes") or 0),
            errors=list(d.get("errors") or []),
            elapsed_s=float(d.get("elapsed_s") or 0),
            updated_at=str(d.get("updated_at") or ""),
        )


@dataclass
class RealArchiveJob:
    job_id: str
    game_id: str
    archive_dir: str
    library_id: str
    created_at: str
    updated_at: str
    items: dict[str, JobItem] = field(default_factory=dict)
    bytes_done: int = 0
    note: str = (
        "Archivo propio ≠ paquete Nexus. Vortex puede no gestionar estos ZIP como originales."
    )

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "job_id": self.job_id,
            "game_id": self.game_id,
            "archive_dir": self.archive_dir,
            "library_id": self.library_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "bytes_done": self.bytes_done,
            "note": self.note,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "counts": self.counts(),
        }

    def counts(self) -> dict[str, int]:
        c = {
            STATUS_PENDING: 0,
            STATUS_COMPRESSING: 0,
            STATUS_VERIFYING: 0,
            STATUS_OK: 0,
            STATUS_ERROR: 0,
            STATUS_BLOCKED: 0,
        }
        for it in self.items.values():
            c[it.status] = c.get(it.status, 0) + 1
        return c

    @classmethod
    def from_dict(cls, d: dict) -> "RealArchiveJob":
        items = {
            k: JobItem.from_dict(v) for k, v in (d.get("items") or {}).items()
        }
        return cls(
            job_id=str(d.get("job_id") or ""),
            game_id=str(d.get("game_id") or ""),
            archive_dir=str(d.get("archive_dir") or ""),
            library_id=str(d.get("library_id") or ""),
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or ""),
            items=items,
            bytes_done=int(d.get("bytes_done") or 0),
            note=str(d.get("note") or ""),
        )


def ensure_library_marker(archive_dir: Path, *, game_id: str, library_id: str) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    marker = archive_dir / LIBRARY_MARKER
    payload = {
        "library_id": library_id,
        "game_id": game_id,
        "product": "F7777techMods",
        "package_kind": "ARCHIVO_PROPIO",
        "note": "Biblioteca de archivos propios. No es Downloads Vortex/Nexus.",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if marker.is_file():
        try:
            old = json.loads(marker.read_text(encoding="utf-8"))
            if old.get("library_id"):
                payload["library_id"] = old["library_id"]
        except Exception:
            pass
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(marker)


def read_library_marker(archive_dir: Path) -> dict | None:
    marker = archive_dir / LIBRARY_MARKER
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return None


def relink_archive_library(job: RealArchiveJob, new_archive_dir: Path) -> list[str]:
    """
    Revincula rutas cuando cambia la letra de unidad.
    Busca marker con mismo library_id; actualiza paths de items OK.
    """
    notes: list[str] = []
    new_archive_dir = Path(new_archive_dir)
    marker = read_library_marker(new_archive_dir)
    if not marker:
        notes.append("destino sin .sgm_library.json")
        return notes
    if marker.get("library_id") and marker["library_id"] != job.library_id:
        notes.append(
            f"library_id distinto ({marker.get('library_id')} ≠ {job.library_id})"
        )
        return notes
    job.archive_dir = str(new_archive_dir)
    for it in job.items.values():
        if it.status != STATUS_OK or not it.mod_id:
            continue
        cand = new_archive_dir / f"{it.mod_id}.zip"
        if cand.is_file():
            it.path = str(cand)
            notes.append(f"revinculado {it.folder}")
        else:
            it.status = STATUS_ERROR
            it.errors = list(it.errors) + ["ZIP no encontrado tras revinculación"]
            notes.append(f"faltante tras relink: {it.folder}")
    job.updated_at = datetime.now().isoformat(timespec="seconds")
    return notes


def job_path(data_dir: Path) -> Path:
    return data_dir / JOB_FILENAME


def save_job(job: RealArchiveJob, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    job.updated_at = datetime.now().isoformat(timespec="seconds")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_job(path: Path) -> RealArchiveJob | None:
    if not path.is_file():
        return None
    try:
        return RealArchiveJob.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def build_or_update_job(
    *,
    game_id: str,
    archive_dir: Path,
    mods: list[ModEntry],
    cat: GameArchiveCatalog | None,
    folders: list[str] | None,
    data_dir: Path,
    existing: RealArchiveJob | None = None,
) -> RealArchiveJob:
    """Crea o amplía job. No comprime."""
    now = datetime.now().isoformat(timespec="seconds")
    by_folder = {m.folder: m for m in mods}
    entries = {e.folder: e for e in (cat.mods if cat else [])}
    selected = folders if folders is not None else [m.folder for m in mods]

    if existing and existing.game_id == game_id:
        job = existing
        job.archive_dir = str(archive_dir)
    else:
        lib_id = str(uuid.uuid4())
        job = RealArchiveJob(
            job_id=str(uuid.uuid4()),
            game_id=game_id,
            archive_dir=str(archive_dir),
            library_id=lib_id,
            created_at=now,
            updated_at=now,
        )

    ensure_library_marker(archive_dir, game_id=game_id, library_id=job.library_id)
    marker = read_library_marker(archive_dir)
    if marker and marker.get("library_id"):
        job.library_id = str(marker["library_id"])

    for folder in selected:
        m = by_folder.get(folder)
        if not m:
            continue
        mid = make_mod_id(game_id, folder)
        if folder in job.items and job.items[folder].status == STATUS_OK:
            # no repetir verificados
            continue
        if folder not in job.items:
            ent = entries.get(folder)
            job.items[folder] = JobItem(
                folder=folder,
                name=m.name,
                mod_id=mid,
                status=STATUS_BLOCKED if (ent and ent.special_installer) else STATUS_PENDING,
                logical_bytes=ent.staging_logical_size if ent else 0,
                errors=["instalador especial"] if (ent and ent.special_installer) else [],
            )
        else:
            it = job.items[folder]
            if it.status in (STATUS_ERROR, STATUS_COMPRESSING, STATUS_VERIFYING):
                # reanudable
                it.status = STATUS_PENDING
                it.errors = []
    save_job(job, job_path(data_dir))
    return job


def run_archive_job(
    job: RealArchiveJob,
    *,
    mods: list[ModEntry],
    stage_root: Path,
    data_dir: Path,
    game_root: Path | None = None,
    mods_dir: Path | None = None,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
    pause: CancelCb | None = None,
    history_path: Path | None = None,
    limit: int | None = None,
) -> RealArchiveJob:
    """
    Ejecuta/reanuda archivado real. Omite ARCHIVADO VERIFICADO.
    limit: máximo de mods a procesar en esta sesión (tests / control).
    """
    by_folder = {m.folder: m for m in mods}
    dest = Path(job.archive_dir)
    dest_errs = validate_archive_destination(
        dest, stage_root=stage_root, game_root=game_root, mods_dir=mods_dir
    )
    if dest_errs:
        for it in job.items.values():
            if it.status == STATUS_PENDING:
                it.status = STATUS_BLOCKED
                it.errors = list(dest_errs)
        save_job(job, job_path(data_dir))
        return job

    # Solo PENDIENTE (build_or_update_job pasa ERROR→PENDIENTE al reanudar)
    pending = [it for it in job.items.values() if it.status == STATUS_PENDING]
    if limit is not None:
        pending = pending[:limit]

    total = len(pending)
    for idx, it in enumerate(pending):
        if cancel and cancel():
            break
        ok_d, note_d = is_archive_root_available(dest)
        if not ok_d:
            it.status = STATUS_ERROR
            it.errors = [f"disco desconectado: {note_d}"]
            it.updated_at = datetime.now().isoformat(timespec="seconds")
            save_job(job, job_path(data_dir))
            break

        mod = by_folder.get(it.folder)
        if not mod:
            it.status = STATUS_ERROR
            it.errors = ["mod no encontrado en inventario"]
            save_job(job, job_path(data_dir))
            continue

        # ya existe ZIP verificado → saltar
        existing = dest / f"{it.mod_id}.zip"
        if existing.is_file():
            import tempfile

            sb = Path(tempfile.mkdtemp(prefix="sgm_job_vr_", dir=str(data_dir)))
            vr = verify_published_own_archive(
                existing, expect_game_id=job.game_id, sandbox_parent=sb
            )
            from .archive_extract import cleanup_sandbox

            cleanup_sandbox(sb)
            if vr.ok:
                it.status = STATUS_OK
                it.path = vr.published_path
                it.zip_sha256 = vr.zip_sha256
                it.content_sha256 = vr.content_sha256
                it.zip_size = vr.zip_size
                it.logical_bytes = vr.logical_bytes
                it.updated_at = datetime.now().isoformat(timespec="seconds")
                job.bytes_done += vr.zip_size
                save_job(job, job_path(data_dir))
                if progress:
                    progress(it.name, idx + 1, total)
                continue
            # ZIP presente pero inválido: no sobrescribir
            it.status = STATUS_BLOCKED
            it.errors = ["ZIP existente inválido; no se sobrescribe"] + vr.errors
            save_job(job, job_path(data_dir))
            continue

        it.status = STATUS_COMPRESSING
        it.updated_at = datetime.now().isoformat(timespec="seconds")
        save_job(job, job_path(data_dir))
        if progress:
            progress(f"{it.name}", idx + 1, total)

        def item_progress(phase: str, cur: int, tot: int) -> None:
            if phase.startswith("verific"):
                it.status = STATUS_VERIFYING
            elif phase.startswith("comprim"):
                it.status = STATUS_COMPRESSING
            if progress:
                progress(f"{it.name}: {phase}", idx + 1, total)

        r = create_own_archive(
            game_id=job.game_id,
            mod=mod,
            stage_root=stage_root,
            dest_dir=dest,
            progress=item_progress,
            cancel=cancel,
            pause=pause,
            game_root=game_root,
            mods_dir=mods_dir,
        )
        it.status = r.status if r.status else (STATUS_OK if r.ok else STATUS_ERROR)
        it.path = r.published_path
        it.zip_sha256 = r.zip_sha256
        it.content_sha256 = r.content_sha256
        it.zip_size = r.zip_size
        it.logical_bytes = r.logical_bytes
        it.errors = list(r.errors)
        it.elapsed_s = r.elapsed_s
        it.mod_id = r.mod_id or it.mod_id
        it.updated_at = datetime.now().isoformat(timespec="seconds")
        if r.ok:
            job.bytes_done += r.zip_size
            # actualizar catálogo en memoria si se pasó aparte (caller)
        save_job(job, job_path(data_dir))
        if history_path is not None:
            append_history(
                history_path,
                ArchiveHistoryEntry(
                    at=it.updated_at,
                    game_id=job.game_id,
                    mod_id=it.mod_id,
                    folder=it.folder,
                    action="real_archive",
                    path=it.path,
                    ok=r.ok,
                    detail="; ".join(r.errors) if not r.ok else "ARCHIVADO VERIFICADO",
                    zip_size=r.zip_size,
                    logical_bytes=r.logical_bytes,
                    elapsed_s=r.elapsed_s,
                ),
            )

    save_job(job, job_path(data_dir))
    return job


def format_job_report(job: RealArchiveJob) -> str:
    c = job.counts()
    lines = [
        f"=== Trabajo de archivado real — {job.game_id} ===",
        f"Job: {job.job_id}",
        f"Carpeta: {job.archive_dir}",
        f"Library ID: {job.library_id}",
        f"Bytes ZIP publicados (sesión acumulada): {job.bytes_done}",
        "",
        f"ARCHIVADO VERIFICADO: {c.get(STATUS_OK, 0)}",
        f"PENDIENTE: {c.get(STATUS_PENDING, 0)}",
        f"ERROR: {c.get(STATUS_ERROR, 0)}",
        f"BLOQUEADO: {c.get(STATUS_BLOCKED, 0)}",
        "",
        job.note,
        "",
        "Liberar staging: NO DISPONIBLE (S13 solo prepara).",
        "",
    ]
    for it in list(job.items.values())[:60]:
        lines.append(
            f"  [{it.status}] {it.name} — zip={it.zip_size} — "
            f"{it.path or '; '.join(it.errors[:1])}"
        )
    if len(job.items) > 60:
        lines.append(f"  … +{len(job.items) - 60} más")
    return "\n".join(lines)


def apply_job_to_catalog(job: RealArchiveJob, cat: GameArchiveCatalog) -> int:
    """Sincroniza entradas OK del job al catálogo en memoria."""
    n = 0
    by = {e.folder: e for e in cat.mods}
    for folder, it in job.items.items():
        ent = by.get(folder)
        if not ent or it.status != STATUS_OK:
            continue
        ent.own_archive_path = it.path
        ent.own_archive_sha256 = it.zip_sha256
        ent.package_kind = "ARCHIVO_PROPIO"
        ent.mod_id = it.mod_id
        ent.lifecycle = "ARCHIVADO"
        ent.recoverable = True
        ent.recoverable_note = "ARCHIVO_PROPIO verificado (S13)"
        n += 1
    return n


def free_space(archive_dir: Path) -> int | None:
    try:
        return shutil.disk_usage(str(archive_dir)).free
    except OSError:
        return None
