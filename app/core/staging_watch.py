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

S09 — detección de cambios locales en staging (solo lectura del staging).
No modifica staging. No confunde con actualizaciones Nexus.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from .hash_cache import HashCache, sha256_file
from .inventory import ModEntry

SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


class StagingChangeKind(str, Enum):
    ADDED = "añadido"
    MODIFIED = "modificado"
    REMOVED = "eliminado"
    RENAMED = "renombrado"
    VARIANT_GONE = "variante_desaparecida"
    STRUCTURE = "estructura"


@dataclass
class FileChange:
    kind: StagingChangeKind
    rel: str
    detail: str = ""
    old_rel: str = ""
    sha256: str = ""


@dataclass
class ModStagingDelta:
    folder: str
    name: str
    changes: list[FileChange] = field(default_factory=list)
    label: str = ""  # «Cambio local detectado» / «Pendiente de revisión»

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


@dataclass
class StagingWatchResult:
    deltas: list[ModStagingDelta] = field(default_factory=list)
    fingerprint_path: str = ""
    scanned_mods: int = 0
    changed_mods: int = 0
    note: str = (
        "Cambios locales en staging (huellas SHA-256). "
        "No implica actualización disponible en Nexus."
    )


def _scan_mod_files(stage_path: Path, *, with_hash: bool = True) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not stage_path.is_dir():
        return out
    for f in stage_path.rglob("*"):
        if not f.is_file():
            continue
        if f.name.lower() in SKIP_NAMES or f.name.lower().startswith("vortex"):
            continue
        try:
            rel = f.relative_to(stage_path).as_posix()
            st = f.stat()
            ent = {
                "size": st.st_size,
                "mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
                "sha256": "",
            }
            if with_hash:
                ent["sha256"] = sha256_file(f)
            out[rel] = ent
        except OSError:
            continue
    return out


def load_fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"version": 1, "mods": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {"version": 1, "mods": {}}


def save_fingerprint(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = dict(data)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_fingerprint(mods: list[ModEntry]) -> dict:
    mods_map: dict[str, dict] = {}
    for m in mods:
        files = _scan_mod_files(Path(m.stage_path))
        mods_map[m.folder] = {
            "name": m.name,
            "files": files,
            "paks": list(m.paks),
            "pak_elegido": m.pak_elegido,
        }
    return {"version": 1, "mods": mods_map}


def diff_mod(
    folder: str,
    name: str,
    old: dict | None,
    new_files: dict[str, dict],
    *,
    old_paks: list[str] | None = None,
    new_paks: list[str] | None = None,
) -> ModStagingDelta:
    delta = ModStagingDelta(folder=folder, name=name)
    old_files = (old or {}).get("files") or {}
    old_set = set(old_files)
    new_set = set(new_files)

    for rel in sorted(new_set - old_set):
        delta.changes.append(
            FileChange(
                StagingChangeKind.ADDED,
                rel,
                sha256=str(new_files[rel].get("sha256") or ""),
            )
        )
    for rel in sorted(old_set - new_set):
        delta.changes.append(
            FileChange(
                StagingChangeKind.REMOVED,
                rel,
                sha256=str(old_files[rel].get("sha256") or ""),
            )
        )
    for rel in sorted(old_set & new_set):
        if old_files[rel].get("sha256") != new_files[rel].get("sha256"):
            delta.changes.append(
                FileChange(
                    StagingChangeKind.MODIFIED,
                    rel,
                    detail="sha256 distinto",
                    sha256=str(new_files[rel].get("sha256") or ""),
                )
            )

    # Renombres: mismo hash, distinta ruta (heurística)
    removed = [c for c in delta.changes if c.kind == StagingChangeKind.REMOVED]
    added = [c for c in delta.changes if c.kind == StagingChangeKind.ADDED]
    used_add: set[str] = set()
    rename_pairs: list[tuple[FileChange, FileChange]] = []
    for r in removed:
        for a in added:
            if a.rel in used_add:
                continue
            if r.sha256 and r.sha256 == a.sha256:
                rename_pairs.append((r, a))
                used_add.add(a.rel)
                break
    for r, a in rename_pairs:
        delta.changes = [c for c in delta.changes if c is not r and c is not a]
        delta.changes.append(
            FileChange(
                StagingChangeKind.RENAMED,
                a.rel,
                old_rel=r.rel,
                sha256=a.sha256,
                detail=f"{r.rel} → {a.rel}",
            )
        )

    op = list(old_paks or (old or {}).get("paks") or [])
    np = list(new_paks or [])
    for p in op:
        if p not in np:
            delta.changes.append(
                FileChange(
                    StagingChangeKind.VARIANT_GONE,
                    p,
                    detail="variante .pak ya no está en staging",
                )
            )

    # Estructura: cambio fuerte de conteo de archivos
    if old and abs(len(old_files) - len(new_files)) >= 3 and len(delta.changes) >= 3:
        delta.changes.append(
            FileChange(
                StagingChangeKind.STRUCTURE,
                "(mod)",
                detail=f"archivos {len(old_files)} → {len(new_files)}",
            )
        )

    if delta.changes:
        # «Pendiente de revisión» si hay modificados/añadidos/variante; si no, local
        kinds = {c.kind for c in delta.changes}
        if kinds & {
            StagingChangeKind.MODIFIED,
            StagingChangeKind.ADDED,
            StagingChangeKind.VARIANT_GONE,
            StagingChangeKind.STRUCTURE,
        }:
            delta.label = "Pendiente de revisión"
        else:
            delta.label = "Cambio local detectado"
    return delta


def detect_staging_changes(
    mods: list[ModEntry],
    fingerprint_path: Path,
    *,
    cache: HashCache | None = None,
    quick: bool = False,
) -> StagingWatchResult:
    """Compara staging actual con última huella registrada. No escribe staging.

    ``quick=True``: solo size/mtime (UI); si difiere, etiqueta pendiente sin rehash.
    """
    _ = cache  # reservado
    prev = load_fingerprint(fingerprint_path)
    prev_mods = prev.get("mods") or {}
    result = StagingWatchResult(fingerprint_path=str(fingerprint_path))
    result.scanned_mods = len(mods)

    for m in mods:
        new_files = _scan_mod_files(Path(m.stage_path), with_hash=not quick)
        old = prev_mods.get(m.folder)
        if old is None:
            # Primera vez: no marcar como cambio si no había huella global
            if not prev_mods:
                continue
            delta = ModStagingDelta(
                folder=m.folder,
                name=m.name,
                label="Pendiente de revisión",
                changes=[
                    FileChange(
                        StagingChangeKind.ADDED,
                        "(mod)",
                        detail="mod nuevo respecto a huella previa",
                    )
                ],
            )
            result.deltas.append(delta)
            continue
        if quick:
            # Diff ligero por size/mtime
            old_files = old.get("files") or {}
            changed = False
            if set(old_files) != set(new_files):
                changed = True
            else:
                for rel, ent in new_files.items():
                    o = old_files.get(rel) or {}
                    if int(o.get("size", -1)) != int(ent.get("size", -2)) or int(
                        o.get("mtime_ns", -1)
                    ) != int(ent.get("mtime_ns", -2)):
                        changed = True
                        break
            if changed:
                result.deltas.append(
                    ModStagingDelta(
                        folder=m.folder,
                        name=m.name,
                        label="Pendiente de revisión",
                        changes=[
                            FileChange(
                                StagingChangeKind.MODIFIED,
                                "(mod)",
                                detail="cambio size/mtime (revisión completa pendiente)",
                            )
                        ],
                    )
                )
            continue
        delta = diff_mod(
            m.folder,
            m.name,
            old,
            new_files,
            old_paks=list(old.get("paks") or []),
            new_paks=list(m.paks),
        )
        if delta.has_changes:
            result.deltas.append(delta)

    result.changed_mods = len(result.deltas)
    return result


def record_staging_fingerprint(mods: list[ModEntry], fingerprint_path: Path) -> dict:
    """Actualiza huella tras revisión aceptada. No toca archivos de staging."""
    data = build_fingerprint(mods)
    save_fingerprint(fingerprint_path, data)
    return data


def format_staging_watch_report(result: StagingWatchResult) -> str:
    lines = [
        "=== Cambios locales en staging (S09) ===",
        result.note,
        f"Mods escaneados: {result.scanned_mods} · con cambios: {result.changed_mods}",
        f"Huella: {result.fingerprint_path or '(ninguna)'}",
        "",
    ]
    if not result.deltas:
        lines.append("(sin cambios respecto a la última huella registrada)")
        return "\n".join(lines)
    for d in result.deltas[:80]:
        lines.append(f"• {d.name} — {d.label}")
        for c in d.changes[:12]:
            extra = f" ({c.detail})" if c.detail else ""
            lines.append(f"    [{c.kind.value}] {c.rel}{extra}")
        if len(d.changes) > 12:
            lines.append(f"    … +{len(d.changes) - 12} más")
    if len(result.deltas) > 80:
        lines.append(f"… y {len(result.deltas) - 80} mods más")
    lines.append("")
    lines.append("No se ha modificado el staging ni el juego.")
    return "\n".join(lines)
