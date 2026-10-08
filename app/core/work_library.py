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

S14 — biblioteca de trabajo propia (extraídos bajo control del gestor).
No escribe en staging Vortex. ZIP propio sigue siendo la fuente primaria.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .archive_extract import cleanup_sandbox
from .hash_cache import sha256_file
from .inventory import ModEntry, nexus_id_from_folder, short_name
from .own_archive import (
    restore_own_archive_to_sandbox,
    verify_published_own_archive,
)

INDEX_NAME = "work_index.json"
MARKER_NAME = ".sgm_work_library.json"

ProgressCb = Callable[[str, int, int], None]
CancelCb = Callable[[], bool]

PRESENCE_ARCHIVED = "ARCHIVADO"
PRESENCE_VORTEX = "EXTRAÍDO EN VORTEX"
PRESENCE_WORK = "EXTRAÍDO EN BIBLIOTECA PROPIA"
PRESENCE_INSTALLED = "INSTALADO EN JUEGO"


@dataclass
class WorkModRecord:
    mod_id: str
    folder: str
    display_name: str
    game_id: str
    archive_path: str
    work_path: str
    content_sha256: str = ""
    zip_sha256: str = ""
    variants: list[str] = field(default_factory=list)
    pak_elegido: str = ""
    nexus_id: str | None = None
    in_use: bool = False
    pinned: bool = False
    extracted_at: str = ""
    logical_bytes: int = 0
    file_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorkModRecord":
        return cls(
            mod_id=str(d.get("mod_id") or ""),
            folder=str(d.get("folder") or ""),
            display_name=str(d.get("display_name") or ""),
            game_id=str(d.get("game_id") or ""),
            archive_path=str(d.get("archive_path") or ""),
            work_path=str(d.get("work_path") or ""),
            content_sha256=str(d.get("content_sha256") or ""),
            zip_sha256=str(d.get("zip_sha256") or ""),
            variants=list(d.get("variants") or []),
            pak_elegido=str(d.get("pak_elegido") or ""),
            nexus_id=d.get("nexus_id"),
            in_use=bool(d.get("in_use")),
            pinned=bool(d.get("pinned")),
            extracted_at=str(d.get("extracted_at") or ""),
            logical_bytes=int(d.get("logical_bytes") or 0),
            file_count=int(d.get("file_count") or 0),
            last_error=str(d.get("last_error") or ""),
        )


@dataclass
class WorkLibraryIndex:
    game_id: str
    work_root: str
    updated_at: str
    mods: dict[str, WorkModRecord] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "game_id": self.game_id,
            "work_root": self.work_root,
            "updated_at": self.updated_at,
            "mods": {k: v.to_dict() for k, v in self.mods.items()},
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkLibraryIndex":
        mods = {
            k: WorkModRecord.from_dict(v) for k, v in (d.get("mods") or {}).items()
        }
        return cls(
            game_id=str(d.get("game_id") or ""),
            work_root=str(d.get("work_root") or ""),
            updated_at=str(d.get("updated_at") or ""),
            mods=mods,
            notes=list(d.get("notes") or []),
        )


@dataclass
class RestoreWorkResult:
    ok: bool
    mod_id: str = ""
    work_path: str = ""
    errors: list[str] = field(default_factory=list)
    skipped: bool = False


def resolve_work_root(
    data_dir: Path,
    *,
    configured: str = "",
    stage_dir: Path | None = None,
) -> Path:
    """Carpeta de trabajo. Nunca dentro de staging Vortex."""
    if configured.strip():
        root = Path(configured)
    else:
        root = data_dir / "work_library"
    if stage_dir and stage_dir.exists():
        try:
            root.resolve().relative_to(stage_dir.resolve())
            # forzar fuera de staging
            root = data_dir / "work_library"
        except ValueError:
            pass
    return root


def ensure_work_root(work_root: Path, *, game_id: str) -> None:
    work_root.mkdir(parents=True, exist_ok=True)
    marker = work_root / MARKER_NAME
    payload = {
        "game_id": game_id,
        "kind": "sgm_work_library",
        "note": (
            "Biblioteca de trabajo F7777techMods. "
            "No es staging Vortex. No modificar Downloads Vortex."
        ),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(marker)


def index_path(work_root: Path) -> Path:
    return work_root / INDEX_NAME


def load_index(work_root: Path, *, game_id: str) -> WorkLibraryIndex:
    p = index_path(work_root)
    if p.is_file():
        try:
            idx = WorkLibraryIndex.from_dict(json.loads(p.read_text(encoding="utf-8")))
            if idx.game_id and idx.game_id != game_id:
                idx.notes.append(
                    f"índice pertenecía a {idx.game_id}; se reetiqueta a {game_id}"
                )
            idx.game_id = game_id
            idx.work_root = str(work_root)
            return idx
        except Exception:
            pass
    return WorkLibraryIndex(
        game_id=game_id,
        work_root=str(work_root),
        updated_at=datetime.now().isoformat(timespec="seconds"),
        notes=[
            "ZIP propio = fuente primaria. Extraídos solo bajo demanda.",
            "No duplicar permanentemente todo el staging.",
        ],
    )


def save_index(idx: WorkLibraryIndex) -> None:
    root = Path(idx.work_root)
    root.mkdir(parents=True, exist_ok=True)
    idx.updated_at = datetime.now().isoformat(timespec="seconds")
    p = index_path(root)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(idx.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def restore_archive_to_work(
    *,
    game_id: str,
    archive_path: Path,
    work_root: Path,
    idx: WorkLibraryIndex,
    force: bool = False,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
) -> RestoreWorkResult:
    """
    Restaura ARCHIVO_PROPIO a biblioteca de trabajo.
    No toca staging Vortex. No sobrescribe si ya existe (salvo force).
    """
    res = RestoreWorkResult(ok=False)
    archive_path = Path(archive_path)
    if cancel and cancel():
        res.errors.append("cancelado")
        return res

    if progress:
        progress("verificando ZIP", 0, 1)
    vr = verify_published_own_archive(archive_path, expect_game_id=game_id)
    if not vr.ok:
        res.errors.extend(vr.errors or ["ZIP no verificable"])
        return res

    from .own_archive import read_own_manifest

    man, errs = read_own_manifest(archive_path)
    if man is None:
        res.errors.extend(errs)
        return res

    mod_id = man.mod_id
    dest = work_root / mod_id
    if dest.is_dir() and not force:
        # ya extraído — revalidar presencia
        existing = idx.mods.get(mod_id)
        if existing and Path(existing.work_path).is_dir():
            res.ok = True
            res.skipped = True
            res.mod_id = mod_id
            res.work_path = existing.work_path
            return res

    ensure_work_root(work_root, game_id=game_id)
    tmp_parent = Path(tempfile.mkdtemp(prefix="sgm_work_rs_", dir=str(work_root)))
    try:
        if progress:
            progress("extrayendo", 0, 1)
        if cancel and cancel():
            res.errors.append("cancelado")
            return res
        rs = restore_own_archive_to_sandbox(
            archive_path,
            sandbox_parent=tmp_parent,
            expect_game_id=game_id,
            expect_mod_id=mod_id,
        )
        if not rs.ok or rs.sandbox is None:
            res.errors.extend(rs.errors or ["extracción falló"])
            return res
        content = rs.sandbox / "content"
        if not content.is_dir():
            res.errors.append("contenido ausente tras extracción")
            return res

        # publicar: reemplazar destino solo tras OK
        if dest.exists():
            if force:
                shutil.rmtree(dest, ignore_errors=True)
            else:
                res.errors.append("destino work ya existe")
                return res
        # mover content → dest (estructura del mod en raíz work/mod_id)
        shutil.move(str(content), str(dest))

        # verificación post-publicación (muestra hashes del manifiesto)
        for ent in man.files:
            got = dest / ent.path
            if not got.is_file() or sha256_file(got) != ent.sha256:
                shutil.rmtree(dest, ignore_errors=True)
                res.errors.append(f"integridad post-publicación falló: {ent.path}")
                return res

        rec = WorkModRecord(
            mod_id=mod_id,
            folder=man.folder,
            display_name=man.display_name,
            game_id=game_id,
            archive_path=str(archive_path),
            work_path=str(dest),
            content_sha256=man.content_sha256,
            zip_sha256=vr.zip_sha256,
            variants=list(man.variants),
            pak_elegido=man.pak_elegido,
            nexus_id=man.nexus_id,
            in_use=False,
            pinned=False,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            logical_bytes=man.total_bytes,
            file_count=man.total_files,
        )
        idx.mods[mod_id] = rec
        save_index(idx)
        res.ok = True
        res.mod_id = mod_id
        res.work_path = str(dest)
        if progress:
            progress("restaurado", 1, 1)
    finally:
        cleanup_sandbox(tmp_parent)
    return res


def restore_many_to_work(
    *,
    game_id: str,
    archives: list[Path],
    work_root: Path,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
) -> tuple[list[RestoreWorkResult], WorkLibraryIndex]:
    ensure_work_root(work_root, game_id=game_id)
    idx = load_index(work_root, game_id=game_id)
    results: list[RestoreWorkResult] = []
    n = len(archives)
    for i, arch in enumerate(archives):
        if cancel and cancel():
            break
        if progress:
            progress(arch.name, i + 1, n)
        results.append(
            restore_archive_to_work(
                game_id=game_id,
                archive_path=arch,
                work_root=work_root,
                idx=idx,
                progress=None,
                cancel=cancel,
            )
        )
        idx = load_index(work_root, game_id=game_id)
    return results, load_index(work_root, game_id=game_id)


def work_record_to_mod_entry(rec: WorkModRecord, *, usar: bool = False) -> ModEntry:
    """ModEntry apuntando a biblioteca propia (no Vortex staging)."""
    paks = list(rec.variants) or sorted(
        p.name for p in Path(rec.work_path).rglob("*.pak")
    ) if Path(rec.work_path).is_dir() else []
    return ModEntry(
        folder=rec.folder,
        name=rec.display_name or short_name(rec.folder),
        characters=["OTROS"],
        character_main="OTROS",
        paks=paks,
        multi=len(paks) > 1,
        on_disk=False,
        stage_path=rec.work_path,
        nexus_id=rec.nexus_id or nexus_id_from_folder(rec.folder),
        usar=usar or rec.in_use,
        pak_elegido=rec.pak_elegido or (paks[0] if len(paks) == 1 else ""),
        source_kind="WORK_LIBRARY",
        mod_id=rec.mod_id,
        archive_path=rec.archive_path,
        archive_content_sha256=rec.content_sha256,
        archive_zip_sha256=rec.zip_sha256,
        work_extracted=True,
        archived=bool(rec.archive_path),
    )


def mark_in_use(
    idx: WorkLibraryIndex,
    mod_ids: Iterable[str],
    *,
    in_use: bool = True,
) -> None:
    for mid in mod_ids:
        if mid in idx.mods:
            idx.mods[mid].in_use = in_use
    save_index(idx)


def pin_mod(idx: WorkLibraryIndex, mod_id: str, *, pinned: bool = True) -> None:
    if mod_id in idx.mods:
        idx.mods[mod_id].pinned = pinned
        save_index(idx)


def _hardlinks_toward(work_path: Path, mods_dir: Path | None) -> int:
    """Cuenta archivos work con hardlink hacia destino de juego (mismo inode)."""
    if mods_dir is None or not mods_dir.is_dir() or not work_path.is_dir():
        return 0
    n = 0
    try:
        from .install_modes import same_file

        for f in work_path.rglob("*"):
            if not f.is_file():
                continue
            dest = mods_dir / f.name
            if dest.is_file() and same_file(f, dest):
                n += 1
    except OSError:
        return n
    return n


def cleanup_work_library(
    idx: WorkLibraryIndex,
    *,
    only_unused: bool = True,
    active_mod_ids: set[str] | None = None,
    mods_dir: Path | None = None,
    force_linked: bool = False,
) -> tuple[int, list[str]]:
    """
    Elimina extraídos de la biblioteca propia (no ZIP, no Vortex).
    Bloquea in_use, pinned, active_mod_ids y hardlinks a destino (salvo force_linked).
    """
    removed = 0
    notes: list[str] = []
    active_mod_ids = active_mod_ids or set()
    to_del: list[str] = []
    for mid, rec in list(idx.mods.items()):
        if only_unused and (rec.in_use or rec.pinned or mid in active_mod_ids):
            notes.append(f"retenido (en uso/pin): {rec.display_name}")
            continue
        wp = Path(rec.work_path)
        hl = _hardlinks_toward(wp, mods_dir)
        if hl > 0 and not force_linked:
            notes.append(
                f"retenido ({hl} hardlink(s) a destino — "
                f"no limpiar origen enlazado sin advertencia): {rec.display_name}"
            )
            continue
        if wp.is_dir():
            shutil.rmtree(wp, ignore_errors=True)
            removed += 1
            notes.append(f"limpiado: {rec.display_name}")
        to_del.append(mid)
    for mid in to_del:
        idx.mods.pop(mid, None)
    save_index(idx)
    return removed, notes


def classify_presence(
    *,
    has_own_archive: bool,
    vortex_stage_exists: bool,
    work_extracted: bool,
    installed_in_game: bool,
) -> list[str]:
    """Estados de presencia (pueden coexistir)."""
    tags: list[str] = []
    if has_own_archive:
        tags.append(PRESENCE_ARCHIVED)
    if vortex_stage_exists:
        tags.append(PRESENCE_VORTEX)
    if work_extracted:
        tags.append(PRESENCE_WORK)
    if installed_in_game:
        tags.append(PRESENCE_INSTALLED)
    return tags or ["DESCONOCIDO"]


def estimate_work_bytes(idx: WorkLibraryIndex) -> int:
    total = 0
    for rec in idx.mods.values():
        wp = Path(rec.work_path)
        if not wp.is_dir():
            continue
        for f in wp.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    return total


def format_work_library_status(idx: WorkLibraryIndex) -> str:
    lines = [
        f"=== Biblioteca de trabajo — {idx.game_id} ===",
        f"Raíz: {idx.work_root}",
        f"Mods extraídos: {len(idx.mods)}",
        f"En uso: {sum(1 for m in idx.mods.values() if m.in_use)}",
        f"Fijados: {sum(1 for m in idx.mods.values() if m.pinned)}",
        f"Bytes lógicos en work≈ {estimate_work_bytes(idx)}",
        "",
        "ZIP propio = fuente primaria. No es staging Vortex.",
        "",
    ]
    for rec in list(idx.mods.values())[:40]:
        flags = []
        if rec.in_use:
            flags.append("EN_USO")
        if rec.pinned:
            flags.append("PIN")
        lines.append(
            f"  • {rec.display_name} [{', '.join(flags) or 'idle'}] — {rec.work_path}"
        )
    return "\n".join(lines)
