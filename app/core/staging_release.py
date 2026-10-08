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

S13 — preparación de liberación de staging (NO ejecuta borrado).
Un ARCHIVO_PROPIO verificado prepara la retirada; nunca la autoriza solo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .archive_catalog import GameArchiveCatalog, ModArchiveEntry
from .archive_plan import _count_hardlinks_to_mods
from .inventory import ModEntry
from .own_archive import is_archive_root_available, read_own_manifest
from .real_archive_job import STATUS_OK, RealArchiveJob


@dataclass
class StagingReleaseRow:
    folder: str
    name: str
    mod_id: str
    own_archive_verified: bool
    archive_path: str
    archive_accessible: bool
    zip_sha256: str
    content_sha256: str
    sandbox_ok: bool
    hardlinks: int
    active_dependency: bool
    vortex_status: str  # conocido|desconocido|sin_paquete_original
    staging_logical: int
    potentially_reclaimable: int
    blocked: bool
    block_reasons: list[str] = field(default_factory=list)
    liberate_action: str = "NO DISPONIBLE"


@dataclass
class StagingReleaseReport:
    game_id: str
    generated_at: str
    rows: list[StagingReleaseRow] = field(default_factory=list)
    prepared_count: int = 0
    blocked_count: int = 0
    reclaimable_if_authorized: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "prepared_count": self.prepared_count,
            "blocked_count": self.blocked_count,
            "reclaimable_if_authorized": self.reclaimable_if_authorized,
            "liberate_staging": "NO DISPONIBLE",
            "notes": list(self.notes),
            "rows": [asdict(r) for r in self.rows],
        }


def build_staging_release_report(
    cat: GameArchiveCatalog,
    mods: list[ModEntry],
    *,
    job: RealArchiveJob | None = None,
    mods_dir: Path | None = None,
    verify_access: bool = True,
) -> StagingReleaseReport:
    """
    Informe por mod. NO borra. liberate_action siempre NO DISPONIBLE.
    """
    rep = StagingReleaseReport(
        game_id=cat.game_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        notes=[
            "Liberar staging: NO DISPONIBLE en S13.",
            "ARCHIVO_PROPIO verificado prepara la retirada, no la autoriza.",
            "Vortex no gestiona archivos propios como paquetes Nexus originales.",
            "No se ha borrado staging ni modificado Vortex/Downloads.",
        ],
    )
    by_mod = {m.folder: m for m in mods}
    job_items = job.items if job else {}

    for entry in cat.mods:
        m = by_mod.get(entry.folder)
        stage = Path(m.stage_path) if m else None
        hl = _count_hardlinks_to_mods(stage, mods_dir) if stage else 0
        jit = job_items.get(entry.folder)

        path = entry.own_archive_path or (jit.path if jit else "")
        accessible = False
        zip_sha = entry.own_archive_sha256 or (jit.zip_sha256 if jit else "")
        content_sha = (jit.content_sha256 if jit else "") or ""
        sandbox_ok = bool(entry.recoverable is True and path)
        verified = False

        if path and verify_access:
            p = Path(path)
            ok_root, _ = is_archive_root_available(p.parent)
            if ok_root and p.is_file():
                accessible = True
                man, errs = read_own_manifest(p)
                if man and not errs:
                    verified = True
                    content_sha = content_sha or man.content_sha256
                    if not zip_sha:
                        try:
                            from .hash_cache import sha256_file

                            zip_sha = sha256_file(p)
                        except OSError:
                            pass
                else:
                    sandbox_ok = False
            else:
                accessible = False
                sandbox_ok = False
        elif jit and jit.status == STATUS_OK:
            verified = True
            accessible = bool(path and Path(path).is_file()) if verify_access else bool(path)

        if jit and jit.status == STATUS_OK:
            verified = verified or bool(jit.zip_sha256)
            sandbox_ok = sandbox_ok or verified

        active = bool(m and m.usar)
        vortex = "desconocido"
        if entry.archive_path:
            vortex = "conocido" if entry.match_grade == "VERIFICADA" else "paquete_original_candidato"
        elif entry.match_grade == "NO ENCONTRADA":
            vortex = "sin_paquete_original"

        reasons: list[str] = []
        blocked = False
        if not verified or not path:
            blocked = True
            reasons.append("sin ARCHIVO_PROPIO verificado")
        if not accessible:
            blocked = True
            reasons.append("ruta de archivo no accesible")
        if not sandbox_ok and not verified:
            blocked = True
            reasons.append("recuperación sandbox no demostrada")
        if hl > 0:
            blocked = True
            reasons.append(f"{hl} hardlink(s) hacia destino")
        if entry.special_installer:
            blocked = True
            reasons.append("instalador especial")
        if active:
            blocked = True
            reasons.append("mod marcado activo en loadout")

        # potencialmente liberable solo si preparado (pero acción sigue NO DISPONIBLE)
        prepared = verified and accessible and not blocked
        reclaim = int(entry.staging_logical_size) if prepared else 0

        row = StagingReleaseRow(
            folder=entry.folder,
            name=entry.name,
            mod_id=entry.mod_id or (jit.mod_id if jit else ""),
            own_archive_verified=verified,
            archive_path=path,
            archive_accessible=accessible,
            zip_sha256=zip_sha,
            content_sha256=content_sha,
            sandbox_ok=sandbox_ok or verified,
            hardlinks=hl,
            active_dependency=active,
            vortex_status=vortex,
            staging_logical=entry.staging_logical_size,
            potentially_reclaimable=reclaim,
            blocked=not prepared,
            block_reasons=reasons if not prepared else [],
            liberate_action="NO DISPONIBLE",
        )
        rep.rows.append(row)
        if prepared:
            rep.prepared_count += 1
            rep.reclaimable_if_authorized += reclaim
        else:
            rep.blocked_count += 1

    return rep


def format_staging_release_report(rep: StagingReleaseReport) -> str:
    def fmt(n: int) -> str:
        x = float(n)
        for u in ("B", "KiB", "MiB", "GiB", "TiB"):
            if x < 1024 or u == "TiB":
                return f"{x:.2f} {u}"
            x /= 1024
        return str(n)

    lines = [
        f"=== Preparación liberación staging — {rep.game_id} ===",
        f"Generado: {rep.generated_at}",
        "Acción «Liberar staging»: NO DISPONIBLE",
        f"Preparados (archivo verificado + sin bloqueos): {rep.prepared_count}",
        f"Bloqueados: {rep.blocked_count}",
        f"Espacio físico potencialmente liberable (si se autorizara): "
        f"{fmt(rep.reclaimable_if_authorized)}",
        "",
    ]
    for n in rep.notes:
        lines.append(f"! {n}")
    lines.append("")
    lines.append("Preparados (muestra):")
    for r in [x for x in rep.rows if not x.blocked][:30]:
        lines.append(
            f"  ✓ {r.name} — {fmt(r.potentially_reclaimable)} — {r.archive_path}"
        )
    lines.append("")
    lines.append("Bloqueados (muestra):")
    for r in [x for x in rep.rows if x.blocked][:40]:
        lines.append(
            f"  ✗ {r.name} — {'; '.join(r.block_reasons) or 'bloqueado'}"
        )
    return "\n".join(lines)
