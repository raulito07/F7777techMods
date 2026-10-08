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

S04 — adopción controlada de archivos existentes (sin copiar/mover/borrar).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .apply import (
    ApplyContext,
    ApplyError,
    KEEP,
    _atomic_write_json,
    _key,
    _norm_rel,
    load_manifest,
    safe_resolve_under,
    vortex_deploy_present,
)
from .hash_cache import HashCache
from .provenance import Provenance, parse_vortex_deployment, scan_destination


@dataclass
class AdoptionCandidate:
    dest_rel: str
    dest_path: Path
    size: int
    sha256: str
    mod_folder: str
    mod_name: str
    stage_file: Path


@dataclass
class AdoptionPlan:
    ok: bool
    errors: list[str]
    candidate: AdoptionCandidate | None = None


def _staging_matches(
    stage_dir: Path,
    dest_rel: str,
    dest_sha: str,
    cache: HashCache,
) -> list[tuple[str, Path]]:
    """Lista (mod_folder, stage_file) con mismo destino lógico y mismo SHA-256."""
    if not stage_dir or not stage_dir.exists():
        return []
    dest_rel = _norm_rel(dest_rel)
    dest_name = Path(dest_rel).name
    matches: list[tuple[str, Path]] = []

    for mod_dir in sorted(stage_dir.iterdir(), key=lambda p: p.name.lower()):
        if not mod_dir.is_dir():
            continue
        # .pak / contenedor plano: destino = nombre de archivo
        for f in mod_dir.rglob("*"):
            if not f.is_file() or f.name.lower() in ("thumbs.db", "desktop.ini"):
                continue
            if f.name.lower().startswith("vortex"):
                continue
            if f.suffix.lower() == ".pak":
                offer_rel = _norm_rel(f.name)
            else:
                offer_rel = _norm_rel(f.relative_to(mod_dir).as_posix())
            if _key(offer_rel) != _key(dest_rel):
                # también permitir match solo por basename de pak si dest es basename
                if not (
                    f.suffix.lower() == ".pak"
                    and _key(f.name) == _key(dest_name)
                    and "/" not in dest_rel
                ):
                    continue
            try:
                sha = cache.get(f) or ""
            except Exception:
                continue
            if sha and sha == dest_sha:
                matches.append((mod_dir.name, f))
    return matches


def plan_adoption(
    dest_rel: str,
    ctx: ApplyContext,
    *,
    hash_cache_path: Path | None = None,
) -> AdoptionPlan:
    """Simula adopción. No escribe manifiesto ni toca el juego."""
    errors: list[str] = []
    dest_rel = _norm_rel(dest_rel)
    if Path(dest_rel).name in KEEP:
        return AdoptionPlan(False, ["Archivo reservado del sistema; no adoptable."])

    if vortex_deploy_present(ctx):
        # Bloquear adopción de cualquier archivo listado en deploy; y avisar deploy activo
        vmap = parse_vortex_deployment(ctx.deploy)
        if _key(dest_rel) in vmap:
            return AdoptionPlan(
                False,
                [
                    "Archivo pertenece a un despliegue Vortex activo "
                    "(vortex.deployment.json). Adopción bloqueada."
                ],
            )
        # Deploy activo pero archivo no listado: aún riesgoso adoptar mezclas
        # Spec: "No adoptar archivos pertenecientes a un despliegue activo de Vortex"
        # Only block Vortex-owned; allow EXTERNO if not in deploy list.

    try:
        dest_path = safe_resolve_under(ctx.mods, dest_rel)
    except ApplyError as e:
        return AdoptionPlan(False, [str(e)])

    if not dest_path.is_file():
        return AdoptionPlan(False, [f"No existe en destino: {dest_rel}"])

    manifest = load_manifest(ctx)
    if _key(dest_rel) in {_key(r) for r in manifest}:
        return AdoptionPlan(False, ["Ya está GESTIONADO en el manifiesto."])

    inv = scan_destination(
        ctx.mods,
        manifest=manifest,
        deploy_path=ctx.deploy,
        compute_hashes=False,
    )
    info = next((x for x in inv.files if _key(x.rel) == _key(dest_rel)), None)
    if info and info.provenance == Provenance.VORTEX:
        return AdoptionPlan(
            False,
            ["Procedencia VORTEX verificable; no se adopta."],
        )
    if info and info.provenance == Provenance.DESCONOCIDO:
        return AdoptionPlan(False, ["Procedencia DESCONOCIDA; adopción bloqueada."])

    cache = HashCache(hash_cache_path)
    try:
        dest_sha = cache.get(dest_path) or ""
    except Exception as e:
        return AdoptionPlan(False, [f"No se pudo calcular SHA-256: {e}"])
    if not dest_sha:
        return AdoptionPlan(False, ["SHA-256 vacío; adopción bloqueada."])

    matches = _staging_matches(ctx.stage, dest_rel, dest_sha, cache)
    # únicos por mod_folder
    by_mod: dict[str, Path] = {}
    for folder, path in matches:
        if folder in by_mod and by_mod[folder] != path:
            return AdoptionPlan(
                False,
                [
                    f"Ambigüedad dentro del mod «{folder}»: varios archivos "
                    f"coinciden con el destino/hash."
                ],
            )
        by_mod[folder] = path

    if not by_mod:
        return AdoptionPlan(
            False,
            [
                "No hay vínculo verificable (mismo destino lógico + SHA-256) "
                "con ningún archivo del staging seleccionado."
            ],
        )
    if len(by_mod) > 1:
        names = ", ".join(sorted(by_mod))
        return AdoptionPlan(
            False,
            [f"Origen ambiguo: el hash coincide con varios mods ({names})."],
        )

    folder, stage_file = next(iter(by_mod.items()))
    try:
        cache.save()
    except Exception:
        pass

    cand = AdoptionCandidate(
        dest_rel=dest_rel,
        dest_path=dest_path,
        size=dest_path.stat().st_size,
        sha256=dest_sha,
        mod_folder=folder,
        mod_name=folder,
        stage_file=stage_file,
    )
    return AdoptionPlan(True, errors, cand)


def execute_adoption(
    plan: AdoptionPlan,
    ctx: ApplyContext,
    *,
    confirm: bool,
) -> dict:
    """Añade al manifiesto. No copia/mueve/borra archivos del juego."""
    if not confirm:
        raise ApplyError("Adopción cancelada: falta confirmación explícita.")
    if not plan.ok or not plan.candidate:
        raise ApplyError(
            "Adopción no válida.\n" + "\n".join(plan.errors or ["sin candidato"])
        )
    # Revalidar
    fresh = plan_adoption(
        plan.candidate.dest_rel,
        ctx,
        hash_cache_path=None,
    )
    # Use same checks; recompute with cache optional
    if not fresh.ok or not fresh.candidate:
        raise ApplyError("Revalidación fallida.\n" + "\n".join(fresh.errors))
    if fresh.candidate.sha256 != plan.candidate.sha256:
        raise ApplyError("El archivo cambió durante la confirmación; adopción bloqueada.")
    if fresh.candidate.mod_folder != plan.candidate.mod_folder:
        raise ApplyError("El origen verificable cambió; adopción bloqueada.")

    if vortex_deploy_present(ctx):
        vmap = parse_vortex_deployment(ctx.deploy)
        if _key(plan.candidate.dest_rel) in vmap:
            raise ApplyError("Deploy Vortex activo sobre este archivo; adopción bloqueada.")

    from .apply import MANIFEST_VERSION, prepare_manifest_backup
    from .operations import OperationRecord, new_operation_id, save_operation

    # Snapshot del manifiesto previo (sin tocar archivos del juego)
    bdir = prepare_manifest_backup(ctx, note="adoption")
    (bdir / "IN_PROGRESS").write_text("adopting\n", encoding="utf-8")

    now = datetime.now().isoformat(timespec="seconds")
    c = fresh.candidate
    try:
        manifest = load_manifest(ctx)
        manifest[_norm_rel(c.dest_rel)] = {
            "mod_folder": c.mod_folder,
            "mod_name": c.mod_name,
            "source": str(c.stage_file),
            "installed_at": now,
            "sha256": c.sha256,
            "size": c.size,
            "origin": "adopt",
            "adopted_at": now,
            "adopt_evidence": {
                "stage_file": str(c.stage_file),
                "sha256_match": True,
                "dest_rel": _norm_rel(c.dest_rel),
            },
        }
        payload = {
            "version": MANIFEST_VERSION,
            "updated_at": now,
            "files": manifest,
        }
        _atomic_write_json(ctx.manifest, payload)
        (bdir / "IN_PROGRESS").unlink(missing_ok=True)
        meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
        meta["status"] = "success"
        meta["transaction"] = {**(meta.get("transaction") or {}), "phase": "success"}
        _atomic_write_json(bdir / "meta.json", meta)
    except Exception as e:
        from .apply import recover_incomplete_transactions

        recover_incomplete_transactions(ctx)
        raise ApplyError(f"Fallo en adopción: {e}") from e

    result = {
        "adopted": _norm_rel(c.dest_rel),
        "mod_folder": c.mod_folder,
        "sha256": c.sha256,
    }
    if ctx.data_dir is not None:
        save_operation(
            ctx.data_dir,
            OperationRecord(
                id=new_operation_id(),
                op_type="adopt",
                at=now,
                backup_id=bdir.name,
                adopted=[result["adopted"]],
                status="success",
                has_pre_manifest=True,
                post_hashes={result["adopted"]: c.sha256},
                note=f"mod={c.mod_folder}",
            ),
        )
    return result
