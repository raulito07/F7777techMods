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

S14/S16 — simulación de liberación de staging (NO borra).
Categorías: LIBERABLE | BLOQUEADO | PENDIENTE_VORTEX.
Espacio físico estimado ≠ tamaño lógico garantizado.
Ejecución de borrado: NO DISPONIBLE en S16.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .archive_catalog import GameArchiveCatalog
from .archive_plan import _count_hardlinks_to_mods
from .inventory import ModEntry
from .own_archive import is_archive_root_available, read_own_manifest
from .real_archive_job import STATUS_OK, RealArchiveJob
from .vortex_liberation import (
    VortexStagingRisk,
    assess_vortex_for_mod,
    format_vortex_research_summary,
    probe_for_liberation,
)
from .vortex_sync import VortexEnableSnapshot
from .work_library import (
    PRESENCE_ARCHIVED,
    PRESENCE_INSTALLED,
    PRESENCE_VORTEX,
    PRESENCE_WORK,
    WorkLibraryIndex,
    classify_presence,
)

# Categorías de política S16
CAT_LIBERABLE = "LIBERABLE"
CAT_BLOQUEADO = "BLOQUEADO"
CAT_PENDIENTE_VORTEX = "PENDIENTE_VORTEX"

PROCEDURE_STEPS = [
    "seleccionar_archivados",
    "verificar_zip",
    "comprobar_manifiesto",
    "detectar_hardlinks",
    "operaciones_pendientes",
    "verificar_dependencias",
    "impacto_vortex",
    "simular_espacio",
    "solicitar_confirmacion",
    "ejecutar_si_autorizado",
]


@dataclass
class LiberationRow:
    folder: str
    name: str
    presence: list[str]
    archived_verified: bool
    archive_accessible: bool
    vortex_managed_likely: bool
    gestor_managed_installed: bool
    work_extracted: bool
    in_use_work: bool
    hardlinks_to_game: int
    staging_logical: int
    staging_physical_est: int | None  # None = no determinable
    reclaimable_physical_est: int | None
    blocked: bool
    block_reasons: list[str] = field(default_factory=list)
    liberate_action: str = "BLOQUEADO"
    # S16
    category: str = CAT_BLOQUEADO
    recommended_method: str = "BLOQUEADO"
    vortex_risk: str = ""
    vortex_state_label: str = ""
    independence_ok: bool = False
    space_freed: bool = False  # staging ausente ≠ solo archivado
    instructions: str = ""
    procedure_ok_until: str = ""
    execution_available: bool = False


@dataclass
class LiberationSimulation:
    game_id: str
    generated_at: str
    rows: list[LiberationRow] = field(default_factory=list)
    candidates: int = 0
    blocked_count: int = 0
    pendiente_vortex_count: int = 0
    liberable_count: int = 0
    physical_est_total: int | None = 0
    logical_staging_total: int = 0
    reclaimable_if_authorized: int | None = 0
    notes: list[str] = field(default_factory=list)
    vortex_impact: list[str] = field(default_factory=list)
    procedure_summary: list[str] = field(default_factory=list)
    execution_authorized: bool = False  # siempre False en S16

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "generated_at": self.generated_at,
            "candidates": self.candidates,
            "blocked_count": self.blocked_count,
            "pendiente_vortex_count": self.pendiente_vortex_count,
            "liberable_count": self.liberable_count,
            "physical_est_total": self.physical_est_total,
            "logical_staging_total": self.logical_staging_total,
            "reclaimable_if_authorized": self.reclaimable_if_authorized,
            "liberate_staging": "NO DISPONIBLE",
            "execution_authorized": False,
            "notes": list(self.notes),
            "vortex_impact": list(self.vortex_impact),
            "procedure_summary": list(self.procedure_summary),
            "rows": [asdict(r) for r in self.rows],
        }


def estimate_physical_bytes(stage_path: Path | None) -> tuple[int | None, int, int]:
    """
    Estima bytes físicos liberables en carpeta staging del mod.
    - Archivos con st_nlink > 1 → 0 (compartidos; borrar no libera todo).
    - Resto: tamaño lógico como cota superior (no clusters exactos).
    Devuelve (physical_est, logical_total, shared_files).
    """
    if stage_path is None or not stage_path.is_dir():
        return None, 0, 0
    logical = 0
    physical = 0
    shared = 0
    try:
        for f in stage_path.rglob("*"):
            if not f.is_file():
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            logical += st.st_size
            nlink = getattr(st, "st_nlink", 1) or 1
            if nlink > 1:
                shared += 1
                continue
            physical += st.st_size
    except OSError:
        return None, logical, shared
    return physical, logical, shared


def _archive_status(
    entry, job_items: dict
) -> tuple[bool, bool, str, list[str]]:
    """(archived_verified, accessible, path, errors)."""
    errs: list[str] = []
    jit = job_items.get(entry.folder)
    path = entry.own_archive_path or (jit.path if jit else "")
    archived = False
    accessible = False
    if not path:
        errs.append("sin ruta ARCHIVO_PROPIO")
        return False, False, "", errs
    p = Path(path)
    ok_root, root_msg = is_archive_root_available(p.parent)
    if not ok_root:
        errs.append(root_msg or "raíz de archivo no disponible")
        if jit and jit.status == STATUS_OK:
            archived = True
        return archived, False, path, errs
    if not p.is_file():
        errs.append("ZIP ausente")
        return False, False, path, errs
    accessible = True
    man, merrs = read_own_manifest(p)
    if man and not merrs:
        archived = True
    else:
        errs.extend(merrs[:3] or ["manifiesto inválido"])
        if jit is not None and jit.status == STATUS_OK:
            archived = True
            errs.append("manifiesto débil; job OK previo (revisar)")
    return archived, accessible, path, errs


def simulate_staging_liberation(
    cat: GameArchiveCatalog,
    mods: list[ModEntry],
    *,
    job: RealArchiveJob | None = None,
    work_idx: WorkLibraryIndex | None = None,
    mods_dir: Path | None = None,
    managed_rel_paths: set[str] | None = None,
    vortex_snap: VortexEnableSnapshot | None = None,
    vortex_game_id: str | None = None,
    roaming: Path | None = None,
    game_installed: bool = True,
    independence_by_folder: dict[str, bool] | None = None,
    pending_ops: bool = False,
) -> LiberationSimulation:
    """
    Simula liberación (política S16). Nunca borra.
    Ejecución real: siempre NO DISPONIBLE.
    """
    _ = managed_rel_paths  # reservado
    sim = LiberationSimulation(
        game_id=cat.game_id,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        notes=[
            "Liberar staging REAL: NO DISPONIBLE (S16).",
            "Categorías: LIBERABLE | BLOQUEADO | PENDIENTE_VORTEX.",
            "Archivado ≠ espacio liberado.",
            "ZIP correcto solo no basta para LIBERABLE.",
            "Tamaño lógico ≠ espacio físico garantizado.",
            "Biblioteca propia no pone en peligro originales Vortex.",
        ],
        vortex_impact=[
            "Borrar staging sin Uninstall Vortex → missing/broken, "
            "Deploy/actualizaciones rotos.",
            "No se ejecuta Purge ni Uninstall Vortex automáticamente.",
            "No se modifica state.v2 ni la base de datos Vortex.",
            "No se mueven Downloads.",
            "Camino seguro del gestor: ARCHIVO_PROPIO → WORK_LIBRARY → plan/Apply "
            "sin tocar staging.",
            "Sin procedimiento seguro y autorizado → no hay borrado.",
        ],
        procedure_summary=[
            f"Flujo: {' → '.join(PROCEDURE_STEPS)}",
            "Paso ejecutar_si_autorizado: OMITIDO (S16 no autoriza borrado).",
        ],
        execution_authorized=False,
    )

    snap = vortex_snap
    if snap is None and vortex_game_id:
        snap = probe_for_liberation(
            vortex_game_id, roaming=roaming, mods_dir=mods_dir
        )

    by_mod = {m.folder: m for m in mods}
    job_items = job.items if job else {}
    work_by_folder = {}
    if work_idx:
        for rec in work_idx.mods.values():
            work_by_folder[rec.folder] = rec

    phys_sum = 0
    phys_known = True
    reclaim_sum = 0
    reclaim_known = True
    indep = independence_by_folder or {}

    for entry in cat.mods:
        m = by_mod.get(entry.folder)
        stage = Path(m.stage_path) if m and m.stage_path else None
        # Si stage_path apunta a work, no contar como staging Vortex
        vortex_exists = False
        if stage and stage.is_dir():
            stage_root = Path(cat.stage_dir) if cat.stage_dir else None
            if stage_root and stage_root.is_dir():
                try:
                    stage.resolve().relative_to(stage_root.resolve())
                    vortex_exists = True
                except ValueError:
                    vortex_exists = False
            else:
                # sin stage_dir configurado: presencia de carpeta = posible Vortex
                vortex_exists = True

        archived, accessible, _path, arch_errs = _archive_status(entry, job_items)
        wrec = work_by_folder.get(entry.folder)
        work_ex = bool(wrec and Path(wrec.work_path).is_dir())
        installed = bool(m and m.on_disk)

        presence = classify_presence(
            has_own_archive=archived,
            vortex_stage_exists=vortex_exists,
            work_extracted=work_ex,
            installed_in_game=installed,
        )

        hl = _count_hardlinks_to_mods(stage, mods_dir) if stage and vortex_exists else 0
        phys, logical, shared = (
            estimate_physical_bytes(stage) if vortex_exists else (0, 0, 0)
        )
        if vortex_exists:
            if phys is None:
                phys_known = False
            else:
                phys_sum += phys
            sim.logical_staging_total += entry.staging_logical_size or logical
        else:
            logical = entry.staging_logical_size or 0

        v_assess = assess_vortex_for_mod(
            entry.folder,
            staging_exists=vortex_exists,
            snap=snap,
            game_installed=game_installed,
        )

        tech_block: list[str] = []
        if not archived or not accessible:
            tech_block.append(
                "sin ARCHIVO_PROPIO verificado/accesible"
                + (f" ({arch_errs[0]})" if arch_errs else "")
            )
        if hl > 0:
            tech_block.append(f"{hl} hardlink(s) hacia destino de juego")
        if shared > 0:
            tech_block.append(f"{shared} archivo(s) con nlink>1 (espacio físico incierto)")
        if wrec and wrec.in_use:
            tech_block.append("extraído en biblioteca propia marcado en uso")
        if entry.special_installer:
            tech_block.append("instalador especial")
        if m and m.usar:
            tech_block.append("mod activo en loadout del gestor")
        if pending_ops:
            tech_block.append("operaciones de archivado pendientes")
        if installed and not work_ex and vortex_exists:
            tech_block.append(
                "instalado en juego y aún depende de staging (sin work extraído)"
            )

        independence_ok = bool(indep.get(entry.folder, False))
        if archived and accessible and entry.folder not in indep:
            # sin prueba explícita: no asumir independencia
            independence_ok = False

        space_freed = not vortex_exists
        category = CAT_BLOQUEADO
        method = "BLOQUEADO"
        instructions = ""
        reasons = list(tech_block)

        if tech_block:
            category = CAT_BLOQUEADO
            method = "BLOQUEADO"
            instructions = "Corrija bloqueos técnicos antes de plantear liberación."
        elif vortex_exists:
            # Recuperable pero Vortex puede depender → nunca LIBERABLE solo por ZIP
            category = CAT_PENDIENTE_VORTEX
            method = v_assess.recommended_method
            instructions = v_assess.instructions
            reasons.append(
                f"Vortex: {v_assess.risk.value} — retirada solo vía procedimiento oficial"
            )
            if not independence_ok:
                reasons.append(
                    "independencia WORK no comprobada en esta simulación "
                    "(use «Comprobar independencia»)"
                )
        else:
            # Sin staging: espacio ya liberado; categoría informativa
            if archived and accessible:
                category = CAT_LIBERABLE
                method = "GESTOR_INDEPENDENT"
                instructions = (
                    "Staging ausente (espacio liberado). Mantener ARCHIVO_PROPIO; "
                    "usar WORK_LIBRARY para instalar. No hay borrado que ejecutar."
                )
                if not independence_ok:
                    # ZIP ok y sin staging: liberable en sentido de espacio;
                    # independencia recomendable pero no bloquea categoría
                    instructions += (
                        " Recomendado verificar restore→WORK antes de Apply."
                    )
            else:
                category = CAT_BLOQUEADO
                method = "BLOQUEADO"
                instructions = "Sin staging y sin archivo propio usable."
                reasons.append("sin archivo propio para recuperación")

        # LIBERABLE con staging presente: solo huérfano teórico con riesgo NONE
        # (no alcanzable si vortex_exists). Política: ZIP solo ≠ LIBERABLE.
        if (
            category == CAT_PENDIENTE_VORTEX
            and independence_ok
            and v_assess.risk == VortexStagingRisk.NONE
        ):
            category = CAT_LIBERABLE

        reclaim = None
        if (
            category in (CAT_PENDIENTE_VORTEX, CAT_LIBERABLE)
            and vortex_exists
            and phys is not None
            and not tech_block
        ):
            reclaim = phys
            reclaim_sum += phys
        elif phys is None and vortex_exists:
            reclaim_known = False

        # Ejecución siempre bloqueada en S16
        exec_block = "ejecución de borrado no autorizada en S16"
        row = LiberationRow(
            folder=entry.folder,
            name=entry.name,
            presence=presence,
            archived_verified=archived,
            archive_accessible=accessible,
            vortex_managed_likely=vortex_exists
            or v_assess.risk
            not in (VortexStagingRisk.NONE,),
            gestor_managed_installed=installed,
            work_extracted=work_ex,
            in_use_work=bool(wrec and wrec.in_use),
            hardlinks_to_game=hl,
            staging_logical=entry.staging_logical_size or logical,
            staging_physical_est=phys if vortex_exists else 0,
            reclaimable_physical_est=reclaim,
            blocked=True,  # S16: nunca ejecuta
            block_reasons=reasons + [exec_block],
            liberate_action=category,
            category=category,
            recommended_method=method,
            vortex_risk=v_assess.risk.value,
            vortex_state_label=(
                f"{v_assess.reliability}; staging="
                f"{'sí' if vortex_exists else 'no'}"
            ),
            independence_ok=independence_ok,
            space_freed=space_freed,
            instructions=instructions,
            procedure_ok_until="simular_espacio",
            execution_available=False,
        )
        sim.rows.append(row)
        if category == CAT_LIBERABLE:
            sim.liberable_count += 1
            sim.candidates += 1
        elif category == CAT_PENDIENTE_VORTEX:
            sim.pendiente_vortex_count += 1
            sim.candidates += 1  # candidatos a flujo Vortex, no a borrado gestor
        else:
            sim.blocked_count += 1

    sim.physical_est_total = phys_sum if phys_known else None
    sim.reclaimable_if_authorized = reclaim_sum if reclaim_known else None
    return sim


def format_liberation_simulation(sim: LiberationSimulation) -> str:
    def fmt(n: int | None) -> str:
        if n is None:
            return "n/d"
        x = float(n)
        for u in ("B", "KiB", "MiB", "GiB", "TiB"):
            if x < 1024 or u == "TiB":
                return f"{x:.2f} {u}"
            x /= 1024
        return str(n)

    lines = [
        f"=== Simulación liberación staging S16 — {sim.game_id} ===",
        f"Generado: {sim.generated_at}",
        "Acción real de borrado: NO DISPONIBLE",
        f"LIBERABLE={sim.liberable_count} · "
        f"PENDIENTE_VORTEX={sim.pendiente_vortex_count} · "
        f"BLOQUEADO={sim.blocked_count}",
        f"Staging lógico total≈ {fmt(sim.logical_staging_total)}",
        f"Estimación física (nlink==1)≈ {fmt(sim.physical_est_total)}",
        f"Recuperable SI hubiera autorización≈ {fmt(sim.reclaimable_if_authorized)}",
        "",
        "Archivado ≠ espacio liberado.",
        "Presencia: "
        f"{PRESENCE_ARCHIVED} | {PRESENCE_VORTEX} | {PRESENCE_WORK} | {PRESENCE_INSTALLED}",
        "",
    ]
    for n in sim.notes:
        lines.append(f"! {n}")
    lines.append("")
    for p in sim.procedure_summary:
        lines.append(f"· {p}")
    lines.append("")
    lines.append("Impacto Vortex:")
    for v in sim.vortex_impact:
        lines.append(f"  — {v}")
    lines.append("")
    lines.append("Detalle por mod:")
    for r in sim.rows[:40]:
        freed = "ESPACIO_LIBERADO" if r.space_freed else "STAGING_PRESENTE"
        lines.append(
            f"  [{r.category}] {r.name} — {freed} — "
            f"método={r.recommended_method} — "
            f"pres={'|'.join(r.presence)} — "
            f"lógico={fmt(r.staging_logical)} fís≈{fmt(r.staging_physical_est)} — "
            f"indep={'sí' if r.independence_ok else 'no'}"
        )
        if r.block_reasons:
            lines.append(f"      bloqueos: {'; '.join(r.block_reasons[:3])}")
        if r.instructions:
            lines.append(f"      → {r.instructions[:160]}")
    lines.append("")
    lines.append(format_vortex_research_summary())
    return "\n".join(lines)
