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

S04/S05 — historial de operaciones y restauración coherente (archivos + manifiesto).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .apply import (
    ApplyContext,
    ApplyError,
    _atomic_write_json,
    _copy_replace,
    _key,
    _norm_rel,
    _prune_empty_dirs,
    load_manifest,
    prepare_manifest_backup,
    recover_incomplete_transactions,
    safe_resolve_under,
    write_manifest_payload,
)
from .hash_cache import HashCache
from .provenance import Provenance, scan_destination


@dataclass
class OperationRecord:
    id: str
    op_type: str
    at: str
    backup_id: str = ""
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    adopted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "success"
    note: str = ""
    post_hashes: dict[str, str] = field(default_factory=dict)
    has_pre_manifest: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "op_type": self.op_type,
            "at": self.at,
            "backup_id": self.backup_id,
            "added": self.added,
            "updated": self.updated,
            "removed": self.removed,
            "adopted": self.adopted,
            "errors": self.errors,
            "status": self.status,
            "note": self.note,
            "post_hashes": self.post_hashes,
            "has_pre_manifest": self.has_pre_manifest,
        }

    @staticmethod
    def from_dict(d: dict) -> "OperationRecord":
        return OperationRecord(
            id=str(d.get("id") or ""),
            op_type=str(d.get("op_type") or ""),
            at=str(d.get("at") or ""),
            backup_id=str(d.get("backup_id") or ""),
            added=list(d.get("added") or []),
            updated=list(d.get("updated") or []),
            removed=list(d.get("removed") or []),
            adopted=list(d.get("adopted") or []),
            errors=list(d.get("errors") or []),
            status=str(d.get("status") or ""),
            note=str(d.get("note") or ""),
            post_hashes=dict(d.get("post_hashes") or {}),
            has_pre_manifest=bool(d.get("has_pre_manifest", False)),
        )


def operations_dir(data_dir: Path) -> Path:
    return data_dir / "operations"


def list_operations(data_dir: Path) -> list[OperationRecord]:
    root = operations_dir(data_dir)
    if not root.exists():
        return []
    out: list[OperationRecord] = []
    for p in sorted(root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(OperationRecord.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def save_operation(data_dir: Path, record: OperationRecord) -> Path:
    root = operations_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{record.id}.json"
    _atomic_write_json(path, record.to_dict())
    return path


def new_operation_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


@dataclass
class RestorePlan:
    ok: bool
    errors: list[str]
    operation: OperationRecord | None = None
    backup_dir: Path | None = None
    to_restore: list[str] = field(default_factory=list)
    to_delete: list[str] = field(default_factory=list)
    will_restore_manifest: bool = False
    pre_manifest_files: int = 0


def plan_restore(
    data_dir: Path,
    ctx: ApplyContext,
    operation_id: str,
    *,
    hash_cache_path: Path | None = None,
) -> RestorePlan:
    recover_incomplete_transactions(ctx)

    ops = {o.id: o for o in list_operations(data_dir)}
    op = ops.get(operation_id)
    if not op:
        return RestorePlan(False, [f"Operación no encontrada: {operation_id}"])
    if not op.backup_id:
        return RestorePlan(False, ["La operación no tiene backup asociado; no restaurable."])
    bdir = ctx.backups / op.backup_id
    if not bdir.is_dir() or not (bdir / "meta.json").exists():
        return RestorePlan(False, [f"Backup ausente o incompleto: {op.backup_id}"])

    try:
        meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
    except Exception as e:
        return RestorePlan(False, [f"No se pudo leer meta del backup: {e}"])

    pre_path = bdir / "pre_manifest.json"
    has_pre = pre_path.is_file()
    if not has_pre:
        return RestorePlan(
            False,
            [
                "Backup sin snapshot de manifiesto (pre_manifest.json). "
                "No se puede restaurar de forma coherente archivos + manifiesto."
            ],
            operation=op,
            backup_dir=bdir,
        )

    try:
        pre_payload = json.loads(pre_path.read_text(encoding="utf-8"))
        pre_files = pre_payload.get("files") if isinstance(pre_payload, dict) else {}
        if not isinstance(pre_files, dict):
            raise ValueError("files inválido")
    except Exception as e:
        return RestorePlan(
            False,
            [f"Snapshot de manifiesto ilegible: {e}"],
            operation=op,
            backup_dir=bdir,
        )

    saved = meta.get("saved") or {}
    created_new = list(meta.get("created_new") or [])
    errors: list[str] = []
    cache = HashCache(hash_cache_path)
    manifest = load_manifest(ctx)
    inv = scan_destination(
        ctx.mods,
        manifest=manifest,
        deploy_path=ctx.deploy,
        hash_cache=cache,
        compute_hashes=True,
    )
    by_key = {_key(f.rel): f for f in inv.files}

    to_restore = sorted(saved.keys())
    to_delete = sorted({_norm_rel(x) for x in created_new})

    for rel in to_restore:
        k = _key(rel)
        info = by_key.get(k)
        if info is None:
            continue
        if info.provenance in (Provenance.EXTERNO, Provenance.DESCONOCIDO):
            errors.append(
                f"Restaurar «{rel}» sobrescribiría un archivo {info.provenance.value}."
            )
            continue
        if info.provenance == Provenance.VORTEX:
            errors.append(f"Restaurar «{rel}» afectaría un archivo VORTEX.")
            continue
        expected_post = op.post_hashes.get(_norm_rel(rel)) or op.post_hashes.get(rel)
        if expected_post and info.sha256 and info.sha256 != expected_post:
            errors.append(
                f"«{rel}» fue modificado tras la operación (hash distinto al registrado). "
                "Sin confirmación + estrategia segura, la restauración está bloqueada."
            )

    for rel in to_delete:
        k = _key(rel)
        info = by_key.get(k)
        if info is None:
            continue
        if info.provenance != Provenance.GESTIONADO:
            errors.append(
                f"No se eliminará «{rel}» en restauración: procedencia {info.provenance.value}."
            )
        expected_post = op.post_hashes.get(_norm_rel(rel)) or op.post_hashes.get(rel)
        if expected_post and info.sha256 and info.sha256 != expected_post:
            errors.append(
                f"«{rel}» (a eliminar en restore) fue modificado externamente; bloqueado."
            )

    if errors:
        return RestorePlan(
            False,
            errors,
            operation=op,
            backup_dir=bdir,
            to_restore=to_restore,
            to_delete=to_delete,
            will_restore_manifest=True,
            pre_manifest_files=len(pre_files),
        )
    return RestorePlan(
        True,
        [],
        operation=op,
        backup_dir=bdir,
        to_restore=to_restore,
        to_delete=to_delete,
        will_restore_manifest=True,
        pre_manifest_files=len(pre_files),
    )


def _prepare_restore_journal(
    ctx: ApplyContext,
    *,
    to_restore: list[str],
    to_delete: list[str],
    source_backup_id: str,
) -> Path:
    """Journal con estado actual (manifiesto + archivos que se tocarán) antes del restore."""
    journal = prepare_manifest_backup(
        ctx, note=f"restore_journal_from={source_backup_id}"
    )
    files_dir = journal / "files"
    saved: dict[str, dict] = {}
    touch = sorted(set(to_restore) | set(to_delete))
    for rel in touch:
        try:
            src = safe_resolve_under(ctx.mods, rel)
        except ApplyError:
            continue
        if not src.is_file():
            continue
        dest = files_dir.joinpath(*Path(_norm_rel(rel)).parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _copy_replace(src, dest)
        saved[_norm_rel(rel)] = {"action": "restore_journal", "existed": True}

    meta = json.loads((journal / "meta.json").read_text(encoding="utf-8"))
    meta["saved"] = saved
    meta["kind"] = "restore_journal"
    meta["source_backup_id"] = source_backup_id
    meta["status"] = "prepared"
    meta["transaction"] = {
        "phase": "prepared",
        "to_restore": list(to_restore),
        "to_delete": list(to_delete),
    }
    _atomic_write_json(journal / "meta.json", meta)
    (journal / "IN_PROGRESS").write_text("restore\n", encoding="utf-8")
    return journal


def execute_restore(
    plan: RestorePlan,
    ctx: ApplyContext,
    data_dir: Path,
    *,
    confirm: bool,
    hash_cache_path: Path | None = None,
) -> None:
    if not confirm:
        raise ApplyError("Restauración cancelada.")
    if not plan.ok or not plan.backup_dir or not plan.operation:
        raise ApplyError("Plan de restauración inválido.\n" + "\n".join(plan.errors))

    recover_incomplete_transactions(ctx)

    fresh = plan_restore(
        data_dir,
        ctx,
        plan.operation.id,
        hash_cache_path=hash_cache_path,
    )
    if not fresh.ok:
        raise ApplyError(
            "Revalidación de restauración fallida.\n" + "\n".join(fresh.errors)
        )

    bdir = fresh.backup_dir
    assert bdir is not None
    meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
    saved = meta.get("saved") or {}
    files_dir = bdir / "files"
    pre_path = bdir / "pre_manifest.json"
    if not pre_path.is_file():
        raise ApplyError("Falta pre_manifest.json en el backup; restauración abortada.")

    journal = _prepare_restore_journal(
        ctx,
        to_restore=list(fresh.to_restore),
        to_delete=list(fresh.to_delete),
        source_backup_id=bdir.name,
    )

    try:
        managed_keys = {_key(r) for r in load_manifest(ctx)}
        for rel in fresh.to_delete:
            if _key(rel) not in managed_keys:
                continue
            p = safe_resolve_under(ctx.mods, rel)
            if p.is_file():
                p.unlink()

        for rel in list(fresh.to_restore):
            hit = rel if rel in saved else next(
                (k for k in saved if _key(k) == _key(rel)), None
            )
            if not hit:
                continue
            bak = files_dir.joinpath(*Path(_norm_rel(hit)).parts)
            if not bak.is_file():
                raise ApplyError(f"Falta archivo en backup: {hit}")
            dst = safe_resolve_under(ctx.mods, hit)
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copy_replace(bak, dst)

        pre_payload = json.loads(pre_path.read_text(encoding="utf-8"))
        write_manifest_payload(ctx, pre_payload)

        _prune_empty_dirs(ctx.mods)

        jmeta = json.loads((journal / "meta.json").read_text(encoding="utf-8"))
        jmeta["status"] = "success"
        jmeta["transaction"] = {**(jmeta.get("transaction") or {}), "phase": "success"}
        _atomic_write_json(journal / "meta.json", jmeta)
        (journal / "IN_PROGRESS").unlink(missing_ok=True)

        man_after = load_manifest(ctx)
        post_h: dict[str, str] = {}
        for rel, meta in man_after.items():
            sha = str(meta.get("sha256") or "")
            if sha:
                post_h[_norm_rel(rel)] = sha

        save_operation(
            data_dir,
            OperationRecord(
                id=new_operation_id(),
                op_type="restore",
                at=datetime.now().isoformat(timespec="seconds"),
                backup_id=journal.name,
                status="success",
                has_pre_manifest=True,
                note=(
                    f"restored_from={fresh.operation.id if fresh.operation else ''};"
                    f"manifest_files={fresh.pre_manifest_files}"
                ),
                post_hashes=post_h,
            ),
        )
    except Exception as e:
        # Recuperación vía journal IN_PROGRESS
        try:
            recover_incomplete_transactions(ctx)
        except Exception:
            pass
        raise ApplyError(f"Fallo en restauración: {e}") from e
