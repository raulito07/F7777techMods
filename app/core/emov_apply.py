# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S42 — Apply EMOV en sandbox: backup verificado, sustitución atómica, rollback.
No modifica apply.py del motor PAK.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .apply import ApplyError, _atomic_write_json, _copy_replace
from .emov_plan import EmovPlan, EmovReplaceOp
from .hash_cache import sha256_file
OP_RESTAURAR_ORIGINAL = "RESTAURAR_ORIGINAL"
OP_EMOV_REPLACE = "emov_replace"

EMOV_MANIFEST_VERSION = 1


@dataclass
class EmovApplyContext:
    game_root: Path
    data_dir: Path
    backups: Path

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "emov_managed_manifest.json"


def load_emov_manifest(ctx: EmovApplyContext) -> dict[str, dict]:
    p = ctx.manifest_path
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    files = raw.get("files") if isinstance(raw, dict) else None
    return dict(files) if isinstance(files, dict) else {}


def write_emov_manifest(ctx: EmovApplyContext, files: dict[str, dict]) -> None:
    payload = {
        "version": EMOV_MANIFEST_VERSION,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(ctx.manifest_path, payload)


def _backup_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]


def prepare_emov_backup(plan: EmovPlan, ctx: EmovApplyContext) -> Path:
    """Copia vanilla con verificación SHA-256 antes de cualquier sustitución."""
    if not plan.to_replace:
        raise ApplyError("Plan EMOV vacío")
    ctx.backups.mkdir(parents=True, exist_ok=True)
    bid = _backup_id()
    bdir = ctx.backups / bid
    if bdir.exists():
        raise ApplyError(f"Backup EMOV ya existe: {bdir}")
    bdir.mkdir()
    files_dir = bdir / "files"
    files_dir.mkdir()
    saved: dict[str, dict] = {}

    for op in plan.to_replace:
        dst = op.destination
        if not dst.is_file():
            raise ApplyError(f"Vanilla ausente en backup: {op.game_rel}")
        live_hash = sha256_file(dst)
        if live_hash != op.vanilla_sha256:
            raise ApplyError(
                f"Vanilla cambió desde el plan ({op.game_rel}); recalcule."
            )
        rel_key = op.game_rel.replace("\\", "/")
        dest_b = files_dir.joinpath(*Path(rel_key).parts)
        dest_b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, dest_b)
        if not dest_b.is_file() or dest_b.stat().st_size != op.vanilla_size:
            raise ApplyError(f"Backup EMOV incompleto: {op.game_rel}")
        bhash = sha256_file(dest_b)
        if bhash != op.vanilla_sha256:
            raise ApplyError(f"Backup EMOV corrupto (hash): {op.game_rel}")
        saved[rel_key] = {
            "action": "replace",
            "vanilla_sha256": op.vanilla_sha256,
            "vanilla_size": op.vanilla_size,
            "mod_folder": op.mod_folder,
            "backup_sha256": bhash,
        }

    pre = {"version": EMOV_MANIFEST_VERSION, "files": load_emov_manifest(ctx)}
    _atomic_write_json(bdir / "pre_emov_manifest.json", pre)
    meta = {
        "kind": "emov",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "saved": saved,
        "status": "prepared",
    }
    _atomic_write_json(bdir / "meta.json", meta)
    (bdir / "IN_PROGRESS").write_text("prepared\n", encoding="utf-8")
    return bdir


def execute_emov_plan(
    plan: EmovPlan,
    ctx: EmovApplyContext,
    *,
    user_confirmed_overwrite: bool,
) -> str:
    """Ejecuta sustitución; exige confirmación explícita. Devuelve backup_id."""
    if not user_confirmed_overwrite:
        raise ApplyError("Sustitución EMOV requiere confirmación explícita del usuario.")
    if plan.errors or plan.conflicts:
        raise ApplyError("Plan EMOV con bloqueos; no se ejecuta.")
    bdir = prepare_emov_backup(plan, ctx)
    bid = bdir.name
    manifest = load_emov_manifest(ctx)

    try:
        for op in plan.to_replace:
            live_hash = sha256_file(op.destination)
            if live_hash != op.vanilla_sha256:
                raise ApplyError(f"Destino modificado externamente: {op.game_rel}")
            _copy_replace(op.source, op.destination)
            post = sha256_file(op.destination)
            manifest[op.game_rel] = {
                "scope": "ff7r_movie",
                "mod_folder": op.mod_folder,
                "mod_sha256": post,
                "replaced_vanilla_sha256": op.vanilla_sha256,
                "backup_id": bid,
            }
        write_emov_manifest(ctx, manifest)
        meta_path = bdir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "completed"
        _atomic_write_json(meta_path, meta)
        (bdir / "IN_PROGRESS").unlink(missing_ok=True)
    except Exception:
        rollback_emov_backup(bdir, ctx)
        raise
    return bid


def rollback_emov_backup(bdir: Path, ctx: EmovApplyContext) -> None:
    """Restaura archivos desde backup EMOV verificado."""
    meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
    saved = meta.get("saved") or {}
    files_dir = bdir / "files"
    for game_rel, ent in saved.items():
        if not isinstance(ent, dict):
            continue
        src_b = files_dir.joinpath(*Path(game_rel).parts)
        if not src_b.is_file():
            raise ApplyError(f"Backup file missing: {game_rel}")
        expected = str(ent.get("backup_sha256") or ent.get("vanilla_sha256") or "")
        if expected and sha256_file(src_b) != expected:
            raise ApplyError(f"Backup corrupto en rollback: {game_rel}")
        dst = ctx.game_root.joinpath(*Path(game_rel).parts)
        _copy_replace(src_b, dst)
    pre_path = bdir / "pre_emov_manifest.json"
    if pre_path.is_file():
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        files = pre.get("files") if isinstance(pre, dict) else {}
        if isinstance(files, dict):
            write_emov_manifest(ctx, files)


def restore_original_emov(
    game_rels: list[str],
    ctx: EmovApplyContext,
    *,
    op_type: str = OP_RESTAURAR_ORIGINAL,
) -> str:
    """RESTAURAR_ORIGINAL — restaura vanilla desde último backup registrado."""
    manifest = load_emov_manifest(ctx)
    bid = _backup_id()
    touched: list[str] = []
    for rel in game_rels:
        ent = manifest.get(rel)
        if not ent:
            raise ApplyError(f"No gestionado EMOV: {rel}")
        backup_id = str(ent.get("backup_id") or "")
        bdir = ctx.backups / backup_id
        if not bdir.is_dir():
            raise ApplyError(f"Backup EMOV ausente: {backup_id}")
        src_b = (bdir / "files").joinpath(*Path(rel).parts)
        if not src_b.is_file():
            raise ApplyError(f"Archivo backup ausente: {rel}")
        dst = ctx.game_root.joinpath(*Path(rel).parts)
        _copy_replace(src_b, dst)
        touched.append(rel)
        del manifest[rel]
    write_emov_manifest(ctx, manifest)
    return bid
