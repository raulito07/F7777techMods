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

S01/S05 — motor de instalación con manifiesto, backup, rollback y recuperación.

S05 refuerza la recuperación: cada backup guarda el manifiesto previo y el
rollback/recuperación restauran archivos + manifiesto de forma idempotente.

Riesgo documentado: un corte de corriente o kill -9 durante escrituras de
bajo nivel del SO puede dejar el destino inconsistente. Existe diario
IN_PROGRESS y recuperación best-effort al inicio de execute()/restore, pero
NO se declara seguridad ante cortes de energía (no demostrada).
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .inventory import ModEntry
from .conflicts import evaluate
from .conflict_engine import (
    ConflictAnalysis,
    ConflictSettings,
    analyze_file_conflicts,
    semantic_enabled,
)
from .paths import (
    STAGE,
    MODS,
    DEPLOY,
    LOADOUT_MARKER,
    MANAGED_MANIFEST,
    BACKUPS_DIR,
)

KEEP = {"vortex.deployment.json", "_manual_loadout.json"}
MANIFEST_VERSION = 2  # S04: incluye sha256/origen; lectura compatible con v1
MANIFEST_VERSIONS_READ = {1, 2}
CASE_INSENSITIVE = os.name == "nt"


class ApplyError(Exception):
    """Fallo de instalación; puede incluir estado de rollback."""

    def __init__(self, message: str, *, rollback_ok: bool | None = None):
        super().__init__(message)
        self.rollback_ok = rollback_ok


@dataclass
class ApplyContext:
    """Rutas inyectables (producción por defecto; tests usan temporales)."""

    mods: Path = field(default_factory=lambda: MODS)
    deploy: Path = field(default_factory=lambda: DEPLOY)
    loadout_marker: Path = field(default_factory=lambda: LOADOUT_MARKER)
    manifest: Path = field(default_factory=lambda: MANAGED_MANIFEST)
    backups: Path = field(default_factory=lambda: BACKUPS_DIR)
    stage: Path = field(default_factory=lambda: STAGE)
    data_dir: Path | None = None  # S04: historial de operaciones


@dataclass
class DesiredFile:
    source: Path
    mod_folder: str
    mod_name: str


@dataclass
class ApplyPlan:
    to_add: list[str]
    to_update: list[str]
    to_remove: list[str]
    desired: dict[str, Path]
    desired_meta: dict[str, DesiredFile]
    errors: list[str]
    conflicts: int
    file_unresolved: int = 0
    analysis: ConflictAnalysis | None = None
    settings: ConflictSettings | None = None
    drifted: list[str] = field(default_factory=list)
    # S09 — decisiones de instalación por destino (rel → dict serializable)
    install_decisions: dict[str, dict] = field(default_factory=dict)
    install_mode_policy: str = "COPY"


def default_context() -> ApplyContext:
    return ApplyContext()


def _norm_rel(rel: str) -> str:
    s = rel.replace("\\", "/").strip("/")
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _key(rel: str) -> str:
    n = _norm_rel(rel)
    return n.casefold() if CASE_INSENSITIVE else n


def safe_resolve_under(root: Path, rel: str) -> Path:
    """Une root+rel y exige que el resultado resuelto quede bajo root.

    Bloquea absolutos, '..' y redirecciones por symlink/junction que escapen.
    """
    rel_n = _norm_rel(rel)
    if not rel_n:
        raise ApplyError("Ruta relativa vacía no permitida.")
    p = Path(rel_n)
    if p.is_absolute() or getattr(p, "drive", ""):
        raise ApplyError(f"Ruta absoluta no permitida: {rel}")
    if any(part == ".." for part in Path(rel_n).parts):
        raise ApplyError(f"Ruta escapa del destino (..): {rel}")

    root_res = root.resolve()
    # Construir sin resolve intermedio del padre aún inexistente
    candidate = root_res.joinpath(*Path(rel_n).parts)
    # Si el archivo o algún ancestro existe, resolve detecta junctions/symlinks
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as e:
        raise ApplyError(f"No se pudo resolver ruta de forma segura: {rel} ({e})") from e

    try:
        resolved.relative_to(root_res)
    except ValueError as e:
        raise ApplyError(
            f"Ruta fuera del destino autorizado: {rel} → {resolved}"
        ) from e
    return resolved


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _atomic_write_json(path: Path, data: dict) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_manifest(ctx: ApplyContext | None = None) -> dict[str, dict]:
    """Carga archivos gestionados. Compatible con manifiesto v1 y v2."""
    ctx = ctx or default_context()
    path = ctx.manifest
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    ver = raw.get("version")
    if ver not in MANIFEST_VERSIONS_READ:
        return {}
    files = raw.get("files")
    if not isinstance(files, dict):
        return {}
    out: dict[str, dict] = {}
    for rel, meta in files.items():
        if not isinstance(rel, str) or not isinstance(meta, dict):
            continue
        n = _norm_rel(rel)
        if not n or Path(n).name.lower() in {k.lower() for k in KEEP}:
            continue
        out[n] = meta
    return out


def managed_key_set(manifest: dict[str, dict]) -> dict[str, str]:
    """key(casefold) -> ruta canónica del manifiesto."""
    return {_key(rel): rel for rel in manifest}


def manifest_payload(ctx: ApplyContext | None = None) -> dict:
    """Snapshot completo del manifiesto en disco (o vacío v2 si no existe)."""
    ctx = ctx or default_context()
    path = ctx.manifest
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("files"), dict):
                return {
                    "version": int(raw.get("version") or MANIFEST_VERSION),
                    "updated_at": str(raw.get("updated_at") or ""),
                    "files": dict(raw["files"]),
                }
        except Exception:
            pass
    return {
        "version": MANIFEST_VERSION,
        "updated_at": "",
        "files": {},
    }


def write_manifest_payload(ctx: ApplyContext, payload: dict) -> None:
    """Escribe un snapshot de manifiesto validado (restauración / recuperación)."""
    if not isinstance(payload, dict):
        raise ApplyError("Snapshot de manifiesto inválido.")
    files = payload.get("files")
    if files is None:
        files = {}
    if not isinstance(files, dict):
        raise ApplyError("Snapshot de manifiesto: 'files' inválido.")
    ver = payload.get("version", MANIFEST_VERSION)
    if ver not in MANIFEST_VERSIONS_READ and ver != MANIFEST_VERSION:
        raise ApplyError(f"Versión de manifiesto no soportada en snapshot: {ver}")
    out = {
        "version": int(ver) if ver in MANIFEST_VERSIONS_READ else MANIFEST_VERSION,
        "updated_at": str(
            payload.get("updated_at")
            or datetime.now().isoformat(timespec="seconds")
        ),
        "files": files,
    }
    _atomic_write_json(ctx.manifest, out)


def build_desired(
    mods: list[ModEntry],
    settings: ConflictSettings | None = None,
) -> tuple[dict[str, DesiredFile], list[str], ConflictAnalysis | None]:
    """Construye destino→origen vía motor S03. Sin sobrescrituras silenciosas."""
    settings = settings or ConflictSettings()
    analysis = analyze_file_conflicts(mods, settings)
    desired: dict[str, DesiredFile] = {}
    for rel, offer in analysis.desired_offers.items():
        desired[_norm_rel(rel)] = DesiredFile(
            source=offer.source,
            mod_folder=offer.mod_folder,
            mod_name=offer.mod_name,
        )
    return desired, list(analysis.errors), analysis


def current_files(ctx: ApplyContext | None = None) -> set[str]:
    ctx = ctx or default_context()
    if not ctx.mods.exists():
        return set()
    out: set[str] = set()
    for f in ctx.mods.rglob("*"):
        if f.is_file() and f.name not in KEEP:
            try:
                out.add(_norm_rel(f.relative_to(ctx.mods).as_posix()))
            except ValueError:
                continue
    return out


def _disk_index(ctx: ApplyContext) -> dict[str, str]:
    """key → ruta relativa real en disco."""
    return {_key(rel): rel for rel in current_files(ctx)}


def plan_apply(
    mods: list[ModEntry],
    ctx: ApplyContext | None = None,
    settings: ConflictSettings | None = None,
) -> ApplyPlan:
    ctx = ctx or default_context()
    manifest = load_manifest(ctx)
    managed_keys = managed_key_set(manifest)
    disk = _disk_index(ctx)

    settings = settings or ConflictSettings()
    settings.managed_keys = managed_keys
    settings.disk_index = disk
    settings.mods_root = ctx.mods

    use_semantic = semantic_enabled(settings.adapter_id)
    _, nconf = evaluate(mods, semantic=use_semantic)

    desired_meta, errors, analysis = build_desired(mods, settings)
    desired_paths = {rel: d.source for rel, d in desired_meta.items()}

    for rel in list(desired_meta):
        try:
            safe_resolve_under(ctx.mods, rel)
        except ApplyError as e:
            errors.append(str(e))

    # Refuerzo S01: ningún destino deseado sobre ajeno
    want_keys = {_key(rel): rel for rel in desired_meta}
    for wk, rel in want_keys.items():
        if wk in disk and wk not in managed_keys:
            msg = (
                "Destino existente no gestionado (no se sobrescribe): "
                f"'{disk[wk]}' ← {desired_meta[rel].mod_name}"
            )
            if msg not in errors:
                errors.append(msg)

    to_add: list[str] = []
    to_update: list[str] = []
    to_remove: list[str] = []
    drifted: list[str] = []

    from .hash_cache import HashCache

    cache = HashCache(settings.hash_cache_path)

    for rel, meta in desired_meta.items():
        k = _key(rel)
        if k not in disk:
            to_add.append(rel)
            continue
        if k not in managed_keys:
            continue
        src = meta.source
        canon = managed_keys[k]
        dst = ctx.mods / disk[k]
        expected = str(manifest.get(canon, {}).get("sha256") or "")
        try:
            src_h = cache.get(src) or ""
            dst_h = cache.get(dst) or ""
        except OSError:
            to_update.append(rel)
            continue

        # S04: drift externo — no sobrescribir automáticamente
        if expected and dst_h and dst_h != expected:
            drifted.append(canon)
            errors.append(
                "MODIFICADO_EXTERNO: "
                f"'{canon}' (gestionados) cambió fuera del gestor. "
                "No se sobrescribe automáticamente. Revisa «Archivos instalados»."
            )
            continue

        if src_h and dst_h:
            if src_h != dst_h:
                to_update.append(rel)
        else:
            try:
                if src.stat().st_size != dst.stat().st_size:
                    to_update.append(rel)
            except OSError:
                to_update.append(rel)

    for mk, canon in managed_keys.items():
        if mk not in want_keys:
            to_remove.append(canon)

    try:
        cache.save()
    except Exception:
        pass

    file_unresolved = analysis.unresolved if analysis else 0
    total_blockers = nconf + file_unresolved + len(drifted)

    # S09 — decidir método por archivo (simulación / Apply)
    from .install_modes import InstallMode, decide_install_method, parse_install_mode

    policy = parse_install_mode(settings.install_mode)
    decisions: dict[str, dict] = {}
    stage_root = settings.stage_root
    for rel, meta in desired_meta.items():
        dst = ctx.mods / Path(rel)
        dec = decide_install_method(
            meta.source,
            dst,
            policy,
            stage_root=stage_root,
            mods_root=ctx.mods,
            dest_rel=rel,
        )
        decisions[rel] = {
            "method": dec.method.value,
            "policy": dec.policy.value,
            "reason": dec.reason,
            "size": dec.size,
            "eligible_hardlink": dec.eligible_hardlink,
            "blocked": dec.blocked,
            "already_linked": dec.already_linked,
        }
        if policy == InstallMode.HARDLINK and dec.blocked:
            msg = f"HARDLINK bloqueado para '{rel}': {dec.reason}"
            if msg not in errors:
                errors.append(msg)
                total_blockers += 1

    return ApplyPlan(
        to_add=sorted(to_add),
        to_update=sorted(to_update),
        to_remove=sorted(to_remove),
        desired=desired_paths,
        desired_meta=desired_meta,
        errors=errors,
        conflicts=total_blockers,
        file_unresolved=file_unresolved,
        analysis=analysis,
        settings=settings,
        drifted=drifted,
        install_decisions=decisions,
        install_mode_policy=policy.value,
    )


def vortex_deploy_present(ctx: ApplyContext | None = None) -> bool:
    ctx = ctx or default_context()
    return ctx.deploy.exists()


def _backup_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _prepare_backup(
    plan: ApplyPlan,
    ctx: ApplyContext,
) -> Path:
    """Copia archivos que se modificarán/eliminarán. Falla → no tocar destino."""
    ctx.backups.mkdir(parents=True, exist_ok=True)
    # No reutilizar ids: uuid garantiza no sobrescribir backups anteriores
    bid = _backup_id()
    bdir = ctx.backups / bid
    if bdir.exists():
        raise ApplyError(f"Directorio de backup ya existe: {bdir}")
    bdir.mkdir(parents=False)
    files_dir = bdir / "files"
    files_dir.mkdir()

    disk = _disk_index(ctx)
    to_touch: list[tuple[str, str]] = []  # (rel_plan, action)

    for rel in plan.to_remove:
        to_touch.append((rel, "remove"))
    for rel in plan.to_update:
        to_touch.append((rel, "update"))
    # add: solo backup si por carrera ya existe (no debería si plan limpio)
    for rel in plan.to_add:
        if _key(rel) in disk:
            to_touch.append((rel, "replace_unmanaged_guard"))

    saved: dict[str, dict] = {}
    for rel, action in to_touch:
        k = _key(rel)
        if k not in disk:
            continue
        real_rel = disk[k]
        src = safe_resolve_under(ctx.mods, real_rel)
        if not src.is_file():
            continue
        # Verificar que backup no apunta al mismo árbol que mods
        dest_backup = files_dir.joinpath(*Path(real_rel).parts)
        try:
            dest_backup.resolve().relative_to(ctx.backups.resolve())
        except ValueError as e:
            raise ApplyError("Ruta de backup fuera del área autorizada.") from e
        if ctx.mods.resolve() in dest_backup.resolve().parents or dest_backup.resolve() == ctx.mods.resolve():
            raise ApplyError("Backup no puede residir dentro de la carpeta de mods.")

        dest_backup.parent.mkdir(parents=True, exist_ok=True)
        # S09: backups SIEMPRE copia independiente (nunca hardlink a stage/juego)
        shutil.copy2(src, dest_backup)
        if not dest_backup.is_file() or dest_backup.stat().st_size != src.stat().st_size:
            raise ApplyError(f"Backup incompleto para: {real_rel}")
        try:
            if os.path.samefile(src, dest_backup):
                raise ApplyError(
                    f"Backup no puede ser hardlink al origen: {real_rel}"
                )
        except OSError:
            pass
        saved[real_rel] = {"action": action, "existed": True, "backup_method": "COPY"}

    pre = manifest_payload(ctx)
    _atomic_write_json(bdir / "pre_manifest.json", pre)

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "saved": saved,
        "created_new": [],
        "status": "prepared",
        "has_pre_manifest": True,
        "transaction": {
            "phase": "prepared",
            "to_add": list(plan.to_add),
            "to_update": list(plan.to_update),
            "to_remove": list(plan.to_remove),
        },
    }
    _atomic_write_json(bdir / "meta.json", meta)
    (bdir / "IN_PROGRESS").write_text("prepared\n", encoding="utf-8")
    return bdir


def prepare_manifest_backup(ctx: ApplyContext, *, note: str = "") -> Path:
    """Backup solo de manifiesto (adopción / restauración). No toca archivos del juego."""
    ctx.backups.mkdir(parents=True, exist_ok=True)
    bid = _backup_id()
    bdir = ctx.backups / bid
    if bdir.exists():
        raise ApplyError(f"Directorio de backup ya existe: {bdir}")
    bdir.mkdir(parents=False)
    (bdir / "files").mkdir()
    pre = manifest_payload(ctx)
    _atomic_write_json(bdir / "pre_manifest.json", pre)
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "saved": {},
        "created_new": [],
        "status": "prepared",
        "has_pre_manifest": True,
        "kind": "manifest_only",
        "note": note,
        "transaction": {"phase": "prepared"},
    }
    _atomic_write_json(bdir / "meta.json", meta)
    return bdir


def _copy_replace(src: Path, dst: Path) -> None:
    """Copia vía temporal en el mismo directorio + os.replace."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + f".{uuid.uuid4().hex}.partial")
    try:
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            raise ApplyError(f"Copia incompleta: {src.name}")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for d in sorted(root.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except OSError:
                    pass


def _restore_pre_manifest(bdir: Path, ctx: ApplyContext) -> None:
    """Restaura el manifiesto previo guardado en el backup (si existe)."""
    pre_path = bdir / "pre_manifest.json"
    if not pre_path.is_file():
        return
    try:
        payload = json.loads(pre_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ApplyError(f"No se pudo leer pre_manifest del backup: {e}") from e
    write_manifest_payload(ctx, payload)


def _rollback(bdir: Path, ctx: ApplyContext, created_new: list[str]) -> None:
    """Restaura archivos + manifiesto previo; elimina solo archivos nuevos de la tx."""
    meta_path = bdir / "meta.json"
    saved: dict[str, dict] = {}
    if meta_path.exists():
        try:
            saved = json.loads(meta_path.read_text(encoding="utf-8")).get("saved") or {}
        except Exception:
            saved = {}

    errors: list[str] = []

    # Quitar archivos nuevos creados por esta transacción
    for rel in created_new:
        try:
            p = safe_resolve_under(ctx.mods, rel)
            if p.is_file():
                p.unlink()
        except Exception as e:
            errors.append(f"No se pudo eliminar nuevo {rel}: {e}")

    # Restaurar guardados
    files_dir = bdir / "files"
    for rel, info in saved.items():
        if not info.get("existed"):
            continue
        try:
            bak = files_dir.joinpath(*Path(_norm_rel(rel)).parts)
            dst = safe_resolve_under(ctx.mods, rel)
            if not bak.is_file():
                errors.append(f"Falta backup para restaurar: {rel}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copy_replace(bak, dst)
        except Exception as e:
            errors.append(f"No se pudo restaurar {rel}: {e}")

    try:
        _restore_pre_manifest(bdir, ctx)
    except Exception as e:
        errors.append(f"No se pudo restaurar manifiesto previo: {e}")

    _prune_empty_dirs(ctx.mods)

    if errors:
        raise ApplyError(
            "Rollback incompleto:\n" + "\n".join(errors),
            rollback_ok=False,
        )


def _write_manifest(
    plan: ApplyPlan,
    ctx: ApplyContext,
    *,
    hash_cache_path: Path | None = None,
) -> dict[str, str]:
    """Escribe manifiesto v2. Devuelve mapa rel→sha256 instalado."""
    from .hash_cache import HashCache

    cache = HashCache(hash_cache_path)
    files: dict[str, dict] = {}
    post_hashes: dict[str, str] = {}
    now = datetime.now().isoformat(timespec="seconds")
    prev = load_manifest(ctx)
    for rel, meta in plan.desired_meta.items():
        rel_n = _norm_rel(rel)
        sha = ""
        size = 0
        try:
            sha = cache.get(meta.source) or ""
            size = meta.source.stat().st_size
        except OSError:
            pass
        old = prev.get(rel_n) or {}
        method = "COPY"
        if plan.install_decisions and rel_n in plan.install_decisions:
            method = str(plan.install_decisions[rel_n].get("method") or "COPY")
        elif plan.install_decisions and rel in plan.install_decisions:
            method = str(plan.install_decisions[rel].get("method") or "COPY")
        entry = {
            "mod_folder": meta.mod_folder,
            "mod_name": meta.mod_name,
            "source": str(meta.source),
            "installed_at": old.get("installed_at") or now,
            "sha256": sha,
            "size": size,
            "origin": old.get("origin") or "install",
            "install_method": method,
        }
        if old.get("adopted_at"):
            entry["adopted_at"] = old["adopted_at"]
        if old.get("adopt_evidence"):
            entry["adopt_evidence"] = old["adopt_evidence"]
        files[rel_n] = entry
        if sha:
            post_hashes[rel_n] = sha
    payload = {
        "version": MANIFEST_VERSION,
        "updated_at": now,
        "files": files,
    }
    _atomic_write_json(ctx.manifest, payload)
    try:
        cache.save()
    except Exception:
        pass
    return post_hashes


def _write_marker(plan: ApplyPlan, ctx: ApplyContext) -> None:
    payload = {
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "files": len(plan.desired_meta),
        "source": str(ctx.stage),
        "manifest": str(ctx.manifest),
        "s01": True,
    }
    _atomic_write_json(ctx.loadout_marker, payload)


def list_incomplete_backups(ctx: ApplyContext) -> list[Path]:
    """Backups con marca IN_PROGRESS (más recientes primero)."""
    if not ctx.backups.exists():
        return []
    return sorted(
        (p for p in ctx.backups.iterdir() if p.is_dir() and (p / "IN_PROGRESS").exists()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def recover_incomplete_transactions(ctx: ApplyContext) -> list[str]:
    """Recupera transacciones interrumpidas (idempotente).

    Restaura archivos del backup y el manifiesto previo. Ejecutar dos veces
    no debe alterar el estado si la primera recuperación tuvo éxito.

    No garantiza recuperación ante corte de corriente / kill -9 durante
    escrituras de bajo nivel del sistema operativo.
    """
    notes: list[str] = []
    candidates = list_incomplete_backups(ctx)
    if not candidates:
        return notes

    for bdir in candidates:
        try:
            meta: dict = {}
            if (bdir / "meta.json").exists():
                meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
            created_new = list(meta.get("created_new") or [])
            # También considerar created_new ya persistido en meta tras fase copied
            _rollback(bdir, ctx, created_new)
            (bdir / "IN_PROGRESS").unlink(missing_ok=True)
            meta["status"] = "recovered_on_next_run"
            tx = meta.get("transaction") if isinstance(meta.get("transaction"), dict) else {}
            tx = dict(tx)
            tx["phase"] = "recovered"
            meta["transaction"] = tx
            _atomic_write_json(bdir / "meta.json", meta)
            notes.append(f"Recuperado backup incompleto: {bdir.name}")
        except Exception as e:
            notes.append(f"Fallo recuperando {bdir.name}: {e}")
            # Dejar IN_PROGRESS para inspección / reintento
    return notes


def _recover_incomplete_if_any(ctx: ApplyContext) -> None:
    """Compat S01: delega en recover_incomplete_transactions."""
    recover_incomplete_transactions(ctx)


def execute(
    plan: ApplyPlan,
    ctx: ApplyContext | None = None,
    mods: list[ModEntry] | None = None,
    *,
    progress: Callable[[str, int, int], None] | None = None,
) -> None:
    """Aplica el plan con backup + rollback. No escribe si hay errores/Vortex.

    Si se pasa ``mods``, revalida conflictos/prioridades (S03) antes de tocar disco.

    ``progress(phase, current, total)`` es opcional (S06). ``total==0`` indica
    fase indeterminada; no inventar porcentajes en la UI si total es 0.
    """
    ctx = ctx or default_context()

    def _prog(phase: str, current: int = 0, total: int = 0) -> None:
        if progress is None:
            return
        try:
            progress(phase, current, total)
        except Exception:
            pass

    _prog("recuperación", 0, 0)
    _recover_incomplete_if_any(ctx)

    # S10: destino no verificado → no escribir
    if plan.settings is not None and not plan.settings.destination_verified:
        raise ApplyError("Destino del juego no verificado. Apply bloqueado (S10).")

    if vortex_deploy_present(ctx):
        raise ApplyError(
            "Despliegue Vortex activo (vortex.deployment.json). "
            "Haz Purge en Vortex antes de aplicar. Instalación bloqueada."
        )
    if plan.conflicts or plan.errors or plan.file_unresolved:
        raise ApplyError(
            "Plan inválido (conflictos o errores). No se modificó el destino.\n"
            + "\n".join(plan.errors[:20])
        )

    # Revalidación crítica S03 (no confiar solo en la GUI)
    if mods is not None:
        fresh = plan_apply(mods, ctx, plan.settings)
        if fresh.conflicts or fresh.errors or fresh.file_unresolved:
            raise ApplyError(
                "Revalidación: siguen existiendo conflictos sin resolver.\n"
                + "\n".join(fresh.errors[:20])
            )
        if set(fresh.desired_meta) != set(plan.desired_meta):
            raise ApplyError(
                "Revalidación: el conjunto de destinos cambió. Vuelve a simular."
            )
        for rel, meta in fresh.desired_meta.items():
            old = plan.desired_meta[rel]
            if old.mod_folder != meta.mod_folder or Path(old.source) != Path(meta.source):
                raise ApplyError(
                    f"Revalidación: ganador distinto para '{rel}' "
                    f"({old.mod_folder} → {meta.mod_folder}). Vuelve a simular."
                )
        plan = fresh

        # S15 — procedencia STAGING_VORTEX / WORK_LIBRARY
        from .mod_source import validate_mods_for_apply

        game_id = ""
        if plan.settings is not None:
            game_id = str(getattr(plan.settings, "game_id", "") or "")
        stage_root = plan.settings.stage_root if plan.settings else None
        work_root = getattr(plan.settings, "work_root", None) if plan.settings else None
        if not game_id:
            # fallback: no bloquear staging-only si no hay game_id (tests S01)
            mixed = {
                getattr(m, "source_kind", "STAGING_VORTEX")
                for m in mods
                if m.usar
            }
            if "WORK_LIBRARY" in mixed:
                raise ApplyError(
                    "S15: instalación desde WORK_LIBRARY requiere game_id en settings."
                )
        else:
            src_v = validate_mods_for_apply(
                mods,
                game_id=game_id,
                stage_root=stage_root,
                work_root=Path(work_root) if work_root else None,
                only_usar=True,
            )
            if not src_v.ok:
                raise ApplyError(
                    "Revalidación de procedencia (S15) falló. No se modificó el destino.\n"
                    + "\n".join(src_v.errors[:20])
                )

    # Validar orígenes y permisos previos
    ctx.mods.mkdir(parents=True, exist_ok=True)
    for rel, meta in plan.desired_meta.items():
        safe_resolve_under(ctx.mods, rel)
        if not meta.source.is_file():
            raise ApplyError(f"Origen inexistente: {meta.source}")
        # Nunca instalar sobre ajeno (refuerzo)
        k = _key(rel)
        disk = _disk_index(ctx)
        managed_keys = managed_key_set(load_manifest(ctx))
        if k in disk and k not in managed_keys:
            raise ApplyError(
                f"Bloqueado: '{disk[k]}' es ajeno al gestor (prioridad no aplica)."
            )

    manifest = load_manifest(ctx)
    managed_keys = managed_key_set(manifest)
    for rel in plan.to_remove:
        if _key(rel) not in managed_keys:
            raise ApplyError(
                f"Refusing delete: '{rel}' no consta en el manifiesto."
            )
        safe_resolve_under(ctx.mods, rel)

    # Separación backup ↔ mods
    try:
        if ctx.backups.resolve() == ctx.mods.resolve():
            raise ApplyError("BACKUPS_DIR no puede coincidir con la carpeta de mods.")
        ctx.mods.resolve().relative_to(ctx.backups.resolve())
        raise ApplyError("La carpeta de mods no puede estar dentro de backups.")
    except ValueError:
        pass  # mods no está bajo backups → OK
    try:
        ctx.backups.resolve().relative_to(ctx.mods.resolve())
        raise ApplyError("Backups no pueden estar dentro de la carpeta de mods.")
    except ValueError:
        pass

    _prog("backup", 0, 0)
    bdir = _prepare_backup(plan, ctx)
    created_new: list[str] = []
    meta_path = bdir / "meta.json"

    try:
        (bdir / "IN_PROGRESS").write_text("applying\n", encoding="utf-8")

        # Eliminar solo gestionados
        n_rem = len(plan.to_remove)
        for i, rel in enumerate(plan.to_remove, start=1):
            _prog("retirar", i, n_rem)
            p = safe_resolve_under(ctx.mods, rel)
            if p.is_file():
                p.unlink()

        # Añadir / actualizar (S09: COPY o HARDLINK atómico; nunca in-place)
        from .install_modes import InstallMethod, install_file_atomic

        copy_list = list(plan.to_add) + list(plan.to_update)
        n_copy = len(copy_list)
        methods_used: dict[str, str] = {}
        for i, rel in enumerate(copy_list, start=1):
            _prog("instalar", i, n_copy)
            src = plan.desired_meta[rel].source
            dst = safe_resolve_under(ctx.mods, rel)
            existed = dst.is_file()
            dec = (plan.install_decisions or {}).get(rel) or {}
            want_hl = str(dec.get("method") or "").upper() == "HARDLINK"
            if want_hl:
                used = install_file_atomic(src, dst, InstallMethod.HARDLINK)
            else:
                # COPY: mantiene _copy_replace (S01; tests/regresión)
                _copy_replace(src, dst)
                used = InstallMethod.COPY
            methods_used[rel] = used.value
            if plan.install_decisions is not None:
                ent = dict(plan.install_decisions.get(rel) or {})
                ent["method"] = used.value
                ent["method_applied"] = used.value
                plan.install_decisions[rel] = ent
            if not existed:
                created_new.append(_norm_rel(rel))
            if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
                raise ApplyError(f"Verificación fallida tras instalar: {rel}")

        # Actualizar diario con created_new antes del manifiesto
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["created_new"] = created_new
        meta["status"] = "copied"
        meta["install_methods"] = methods_used
        meta["install_mode_policy"] = plan.install_mode_policy
        tx = dict(meta.get("transaction") or {})
        tx["phase"] = "copied"
        meta["transaction"] = tx
        _atomic_write_json(meta_path, meta)

        _prog("manifiesto", 0, 0)
        hash_path = plan.settings.hash_cache_path if plan.settings else None
        post_hashes = _write_manifest(plan, ctx, hash_cache_path=hash_path)
        meta["status"] = "manifest_written"
        tx["phase"] = "manifest_written"
        meta["transaction"] = tx
        _atomic_write_json(meta_path, meta)

        _write_marker(plan, ctx)

        _prune_empty_dirs(ctx.mods)

        meta["status"] = "success"
        tx["phase"] = "success"
        meta["transaction"] = tx
        _atomic_write_json(meta_path, meta)
        (bdir / "IN_PROGRESS").unlink(missing_ok=True)
        _prog("listo", 1, 1)

        # S04 — historial de operaciones
        if ctx.data_dir is not None:
            try:
                from .operations import OperationRecord, new_operation_id, save_operation

                op_type = "apply"
                if plan.to_remove and not plan.to_add and not plan.to_update:
                    op_type = "deactivate"
                rec = OperationRecord(
                    id=new_operation_id(),
                    op_type=op_type,
                    at=datetime.now().isoformat(timespec="seconds"),
                    backup_id=bdir.name,
                    added=list(plan.to_add),
                    updated=list(plan.to_update),
                    removed=list(plan.to_remove),
                    status="success",
                    post_hashes=post_hashes,
                    has_pre_manifest=True,
                    note=f"files={len(plan.desired_meta)}",
                )
                save_operation(ctx.data_dir, rec)
            except Exception:
                pass

    except Exception as e:
        rollback_ok: bool | None = None
        try:
            _rollback(bdir, ctx, created_new)
            rollback_ok = True
            if (bdir / "IN_PROGRESS").exists():
                (bdir / "IN_PROGRESS").write_text("rolled_back\n", encoding="utf-8")
                (bdir / "IN_PROGRESS").unlink(missing_ok=True)
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta["status"] = "rolled_back"
                    _atomic_write_json(meta_path, meta)
                except Exception:
                    pass
            if ctx.data_dir is not None:
                try:
                    from .operations import OperationRecord, new_operation_id, save_operation

                    save_operation(
                        ctx.data_dir,
                        OperationRecord(
                            id=new_operation_id(),
                            op_type="apply",
                            at=datetime.now().isoformat(timespec="seconds"),
                            backup_id=bdir.name,
                            added=list(plan.to_add),
                            updated=list(plan.to_update),
                            removed=list(plan.to_remove),
                            status="rolled_back",
                            has_pre_manifest=True,
                            errors=[str(e)],
                        ),
                    )
                except Exception:
                    pass
        except Exception as re:
            rollback_ok = False
            msg = (
                f"Fallo en instalación: {e}\n"
                f"Además el rollback falló: {re}\n"
                f"Backup en: {bdir}"
            )
            if isinstance(e, ApplyError):
                raise ApplyError(msg, rollback_ok=False) from re
            raise ApplyError(msg, rollback_ok=False) from re

        if isinstance(e, ApplyError):
            raise ApplyError(str(e), rollback_ok=rollback_ok) from e
        raise ApplyError(f"Fallo en instalación: {e}", rollback_ok=rollback_ok) from e
