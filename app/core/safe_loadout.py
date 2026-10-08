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

S08 — propuesta de subconjunto seguro (simulación; no muta loadout ni Apply).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .adapters import get_adapter
from .apply import ApplyContext, plan_apply
from .conflict_engine import ConflictKind, ConflictSettings, analyze_file_conflicts, semantic_enabled
from .conflicts import evaluate
from .content_classify import ModClassification, classify_mod
from .inventory import ModEntry


@dataclass
class SafeSubsetProposal:
    """Resultado de selección segura — no modifica plan del usuario."""

    candidate_folders: list[str] = field(default_factory=list)
    candidate_names: list[str] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    files_to_copy: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    ok_for_controlled_test: bool = False
    summary: str = ""


def _exclude(folder: str, name: str, reason: str) -> dict:
    return {"folder": folder, "name": name, "reason": reason}


def _clone_mod(m: ModEntry, *, usar: bool | None = None) -> ModEntry:
    c = deepcopy(m)
    if usar is not None:
        c.usar = usar
    return c


def propose_safe_subset(
    mods: list[ModEntry],
    settings: ConflictSettings,
    ctx: ApplyContext | None = None,
    *,
    max_mods: int | None = None,
    source_usar_only: bool = True,
) -> SafeSubsetProposal:
    """Elige candidatos sin variantes/conflictos/desconocidos y simula instalación.

    No altera ``usar`` de los mods originales.
    """
    prop = SafeSubsetProposal()
    adapter_id = settings.adapter_id or "generic_folder"
    use_sem = semantic_enabled(adapter_id)

    pool = [m for m in mods if m.usar] if source_usar_only else list(mods)
    candidates: list[ModEntry] = []

    for m in pool:
        mc = classify_mod(m, adapter_id)
        if mc.variant_pending or (m.multi and not m.pak_elegido and m.usar):
            prop.excluded.append(_exclude(m.folder, m.name, "variante pendiente"))
            continue
        if not mc.has_installable:
            reason = "sin instalables"
            if mc.special:
                reason = "solo destino especial / sin .pak"
            elif mc.documentation and not mc.installable:
                reason = "solo documentación"
            elif mc.unknown:
                reason = "contenido desconocido sin instalables"
            prop.excluded.append(_exclude(m.folder, m.name, reason))
            continue
        if mc.unknown:
            prop.excluded.append(
                _exclude(
                    m.folder,
                    m.name,
                    "contenido desconocido pendiente: " + ", ".join(mc.unknown[:4]),
                )
            )
            continue
        if mc.special:
            prop.excluded.append(
                _exclude(
                    m.folder,
                    m.name,
                    "destino especial: " + ", ".join(mc.special[:4]),
                )
            )
            continue
        candidates.append(_clone_mod(m, usar=True))

    # Excluir por conflictos de archivo / semántica (iterativo, quita todos los implicados)
    guard = 0
    while candidates and guard < 50:
        guard += 1
        analysis = analyze_file_conflicts(candidates, settings)
        bad: set[str] = set()
        for fc in analysis.file_conflicts:
            if fc.resolved:
                continue
            if fc.kind in (
                ConflictKind.FILE_CONFLICT,
                ConflictKind.FOREIGN_FILE,
                ConflictKind.VARIANT,
            ):
                for o in fc.offers:
                    bad.add(o.mod_folder)
                prop.warnings.append(
                    f"{fc.kind.value}: {fc.dest_rel} ← "
                    + ", ".join(o.mod_name for o in fc.offers)
                )
        for fc in analysis.variant_issues:
            if not fc.resolved:
                for c in candidates:
                    if c.folder in fc.dest_key or c.name.split(":")[0] in fc.note:
                        bad.add(c.folder)

        slots, _ = evaluate(candidates, semantic=use_sem)
        if slots:
            name_to_folder = {c.name: c.folder for c in candidates}
            for sid, names in slots.items():
                prop.warnings.append(f"Semántico {sid}: {names}")
                for n in names:
                    if n in name_to_folder:
                        bad.add(name_to_folder[n])

        if not bad:
            break
        kept: list[ModEntry] = []
        for c in candidates:
            if c.folder in bad:
                prop.excluded.append(_exclude(c.folder, c.name, "conflicto no resuelto"))
            else:
                kept.append(c)
        candidates = kept

    if max_mods is not None and len(candidates) > max_mods:
        candidates.sort(key=lambda m: (len(m.paks) > 1, m.name.lower()))
        for c in candidates[max_mods:]:
            prop.excluded.append(_exclude(c.folder, c.name, "fuera del cupo de prueba"))
        candidates = candidates[:max_mods]

    prop.candidate_folders = [c.folder for c in candidates]
    prop.candidate_names = [c.name for c in candidates]

    prop.warnings.append(
        "Advertencia: no se analiza el interior de .pak; "
        "pueden existir solapes internos no detectados."
    )

    if not candidates:
        prop.summary = "No hay candidatos seguros con el plan actual."
        prop.ok_for_controlled_test = False
        prop.blockers.append("subconjunto vacío")
        return prop

    # Simular con plan_apply sobre copia (solo candidatos activos)
    cand_set = set(prop.candidate_folders)
    sim_mods = [_clone_mod(m, usar=(m.folder in cand_set)) for m in mods]

    try:
        if ctx is None:
            # Solo desired vía análisis (sin disco de juego)
            analysis = analyze_file_conflicts(sim_mods, settings)
            for rel, offer in analysis.desired_offers.items():
                prop.files_to_copy.append(
                    {
                        "dest_rel": rel,
                        "source": str(offer.source),
                        "mod": offer.mod_name,
                        "folder": offer.mod_folder,
                    }
                )
            if analysis.unresolved:
                prop.blockers.append(
                    f"{analysis.unresolved} conflictos de archivo sin resolver"
                )
            if analysis.errors:
                for e in analysis.errors[:20]:
                    if "AJENO" in e or "variante" in e.lower() or "CONFLICTO" in e:
                        prop.blockers.append(e)
        else:
            plan = plan_apply(sim_mods, ctx, settings)
            for rel, meta in plan.desired_meta.items():
                prop.files_to_copy.append(
                    {
                        "dest_rel": rel,
                        "source": str(meta.source),
                        "mod": meta.mod_name,
                        "folder": meta.mod_folder,
                    }
                )
            for e in plan.errors:
                # Bloqueos reales (ajeno / variante); semántica ya filtrada
                if "no gestionado" in e.lower() or "AJENO" in e or "variante" in e.lower():
                    prop.blockers.append(e)
                elif "Choque" in e or "CONFLICTO" in e:
                    prop.blockers.append(e)
            if plan.file_unresolved:
                prop.blockers.append(
                    f"{plan.file_unresolved} conflictos de archivo sin resolver"
                )

        prop.ok_for_controlled_test = bool(prop.files_to_copy) and not prop.blockers
        prop.summary = (
            f"{len(candidates)} mods / {len(prop.files_to_copy)} archivos a copiar "
            "(simulación; Apply no ejecutado; loadout del usuario no modificado)."
        )
    except Exception as exc:  # noqa: BLE001
        prop.blockers.append(str(exc))
        prop.ok_for_controlled_test = False
        prop.summary = f"Error en simulación: {exc}"

    return prop


def format_safe_subset_report(prop: SafeSubsetProposal) -> str:
    lines = [
        "=== SUBCONJUNTO SEGURO (S08) — solo simulación ===",
        prop.summary,
        f"Apto prueba controlada: {'SI' if prop.ok_for_controlled_test else 'NO'}",
        "",
        f"Candidatos ({len(prop.candidate_names)}):",
    ]
    for n, f in zip(prop.candidate_names, prop.candidate_folders):
        lines.append(f"  • {n}")
        lines.append(f"      folder: {f}")
    if prop.files_to_copy:
        lines.append("")
        lines.append(f"Archivos exactos a copiar ({len(prop.files_to_copy)}):")
        for row in prop.files_to_copy[:80]:
            lines.append(f"  → {row['dest_rel']}")
            lines.append(f"      desde: {row['source']}")
            lines.append(f"      mod: {row['mod']}")
        if len(prop.files_to_copy) > 80:
            lines.append(f"  … y {len(prop.files_to_copy) - 80} más")
    if prop.blockers:
        lines.append("")
        lines.append("Bloqueos:")
        for b in prop.blockers:
            lines.append(f"  ✗ {b}")
    if prop.warnings:
        lines.append("")
        lines.append("Advertencias:")
        for w in prop.warnings[:40]:
            lines.append(f"  ! {w}")
    if prop.excluded:
        lines.append("")
        lines.append(f"Excluidos ({len(prop.excluded)}; muestra):")
        for ex in prop.excluded[:40]:
            lines.append(f"  — {ex['name']}: {ex['reason']}")
        if len(prop.excluded) > 40:
            lines.append(f"  … y {len(prop.excluded) - 40} más")
    lines.append("")
    lines.append("Apply NO ejecutado. Loadout del usuario NO modificado.")
    return "\n".join(lines)


def adapter_notes(adapter_id: str) -> str:
    return get_adapter(adapter_id).notes
