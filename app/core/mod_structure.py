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

S28 — detección de estructura de mods (solo lectura).
Reutiliza adaptadores y content_classify; no escribe ni aplica.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .adapters import get_adapter
from .content_classify import ContentKind, classify_mod
from .inventory import ModEntry
from .path_safety import (
    PathSafetyIssue,
    ZipSafetyReport,
    check_fs_path,
    check_relative_path,
    inspect_zip,
)

# Clasificaciones de resultado (producto)
SIMPLE = "SIMPLE"
COMPUESTO = "COMPUESTO"
CON_VARIANTES = "CON_VARIANTES"
AMBIGUO = "AMBIGUO"
INCOMPLETO = "INCOMPLETO"
NO_SOPORTADO = "NO_SOPORTADO"
SIN_ARCHIVOS_INSTALABLES = "SIN_ARCHIVOS_INSTALABLES"


class Certainty(str, Enum):
    CONFIRMED = "CONFIRMADO"  # regla de adaptador / estructura clara
    HEURISTIC = "HEURISTICO"  # indicios por nombre
    UNKNOWN = "DESCONOCIDO"


@dataclass
class FileGroup:
    """Grupo lógico (p. ej. IoStore stem)."""

    stem: str
    pak: str = ""
    utoc: str = ""
    ucas: str = ""
    complete_for_adapter: bool = False
    missing: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class VariantHint:
    label: str
    members: list[str]
    certainty: Certainty = Certainty.HEURISTIC
    note: str = ""


@dataclass
class StructureReport:
    folder: str
    name: str
    adapter_id: str
    classification: str
    certainty: Certainty
    explanation: str
    format_label: str
    installable: list[str] = field(default_factory=list)
    groups: list[FileGroup] = field(default_factory=list)
    variants: list[VariantHint] = field(default_factory=list)
    issues: list[PathSafetyIssue] = field(default_factory=list)
    zip_reports: list[ZipSafetyReport] = field(default_factory=list)
    blocks_prepare: bool = False
    needs_manual_review: bool = False
    analyzed_ms: float = 0.0
    fingerprint: str = ""

    @property
    def blocked(self) -> bool:
        return self.blocks_prepare or self.classification in {
            INCOMPLETO,
            NO_SOPORTADO,
            AMBIGUO,
            SIN_ARCHIVOS_INSTALABLES,
        }


_VARIANT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bfov\s*[-_]?\s*(\d{2,3})\b"), "FOV{0}"),
    (re.compile(r"(?i)\b(performance|quality)\b"), "{0}"),
    (re.compile(r"(?i)\b([24]k)\b"), "{0}"),
    (re.compile(r"(?i)\b(default|alternative|alt|optional)\b"), "{0}"),
]


def _fingerprint(root: Path) -> str:
    if not root.is_dir():
        return "missing"
    try:
        st = root.stat()
        n = 0
        newest = int(st.st_mtime_ns)
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            n += 1
            try:
                newest = max(newest, int(p.stat().st_mtime_ns))
            except OSError:
                pass
            if n >= 500:
                break
        return f"{n}:{newest}"
    except OSError:
        return "error"


def _format_label(adapter_id: str, installable: list[str]) -> str:
    ad = get_adapter(adapter_id)
    sufs = {Path(x).suffix.lower() for x in installable}
    if ad.iostore_sidecars:
        parts = []
        if ".pak" in sufs:
            parts.append(".pak")
        if ".utoc" in sufs:
            parts.append(".utoc")
        if ".ucas" in sufs:
            parts.append(".ucas")
        return "UE5 IoStore (" + "+".join(parts or ["?"]) + ")"
    if ad.pak_centric:
        return "UE4 PAK (.pak)"
    if installable:
        return "Carpeta / archivos genéricos"
    return "Sin formato instalable"


def _iostore_groups(files: list[str]) -> list[FileGroup]:
    by_stem: dict[str, FileGroup] = {}
    for rel in files:
        p = Path(rel)
        suf = p.suffix.lower()
        if suf not in {".pak", ".utoc", ".ucas"}:
            continue
        stem = p.stem
        g = by_stem.setdefault(stem, FileGroup(stem=stem))
        if suf == ".pak":
            g.pak = rel
        elif suf == ".utoc":
            g.utoc = rel
        elif suf == ".ucas":
            g.ucas = rel
    out: list[FileGroup] = []
    for g in by_stem.values():
        missing = []
        # Regla confirmada del adaptador UE5: los tres componentes del stem
        if not g.pak:
            missing.append(".pak")
        if not g.utoc:
            missing.append(".utoc")
        if not g.ucas:
            missing.append(".ucas")
        g.missing = missing
        g.complete_for_adapter = not missing
        if missing:
            g.note = (
                "Grupo IoStore incompleto (regla adaptador UE5): faltan "
                + ", ".join(missing)
            )
        else:
            g.note = "Grupo IoStore completo (regla adaptador)"
        out.append(g)
    return out


def _variant_hints(names: list[str]) -> list[VariantHint]:
    """Indicios por nombre; Certainty.HEURISTIC — no autoelige."""
    buckets: dict[str, list[str]] = {}
    for name in names:
        labels: list[str] = []
        for rx, fmt in _VARIANT_PATTERNS:
            m = rx.search(name)
            if not m:
                continue
            try:
                label = fmt.format(*(m.groups() or (m.group(0),)))
            except Exception:
                label = m.group(0)
            labels.append(label.upper())
        if not labels:
            continue
        key = "|".join(sorted(set(labels)))
        buckets.setdefault(key, []).append(name)
    hints: list[VariantHint] = []
    for key, members in buckets.items():
        if len(members) < 1:
            continue
        # Solo tiene sentido como familia si hay ≥2 miembros o multi-pak
        hints.append(
            VariantHint(
                label=key.replace("|", " / "),
                members=sorted(members),
                certainty=Certainty.HEURISTIC,
                note="Indicio por nombre; no es prueba de incompatibilidad ni elección automática",
            )
        )
    return hints


def analyze_mod_structure(
    mod: ModEntry,
    adapter_id: str,
    *,
    inspect_zips: bool = True,
    cache: dict[str, StructureReport] | None = None,
) -> StructureReport:
    """Analiza un mod sin escribir. Usa caché por fingerprint si se proporciona."""
    t0 = time.perf_counter()
    root = Path(mod.stage_path) if mod.stage_path else Path()
    fp = _fingerprint(root) if root else "no-root"
    cache_key = f"{mod.folder}|{adapter_id}|{fp}|{mod.pak_elegido}|{int(mod.usar)}"
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    ad = get_adapter(adapter_id)
    mc = classify_mod(mod, adapter_id)
    issues: list[PathSafetyIssue] = []
    zip_reports: list[ZipSafetyReport] = []

    if not root.is_dir():
        # Metadatos de inventario sin carpeta legible → no inventar instalables
        pak_names_meta = list(mc.pak_names or mod.paks)
        if pak_names_meta:
            report = StructureReport(
                folder=mod.folder,
                name=mod.name,
                adapter_id=adapter_id,
                classification=AMBIGUO,
                certainty=Certainty.HEURISTIC,
                explanation=(
                    "Hay nombres .pak en inventario, pero la carpeta de origen "
                    "no es accesible para inspección. Revisión manual / re-escaneo."
                ),
                format_label=_format_label(adapter_id, pak_names_meta),
                installable=[],
                variants=_variant_hints(pak_names_meta),
                blocks_prepare=bool(mod.usar),
                needs_manual_review=True,
                analyzed_ms=(time.perf_counter() - t0) * 1000.0,
                fingerprint=fp,
            )
            if cache is not None:
                cache[cache_key] = report
            return report
        report = StructureReport(
            folder=mod.folder,
            name=mod.name,
            adapter_id=adapter_id,
            classification=SIN_ARCHIVOS_INSTALABLES,
            certainty=Certainty.CONFIRMED,
            explanation="No hay carpeta de origen ni archivos instalables conocidos.",
            format_label="Sin origen",
            blocks_prepare=True,
            needs_manual_review=True,
            analyzed_ms=(time.perf_counter() - t0) * 1000.0,
            fingerprint=fp,
        )
        if cache is not None:
            cache[cache_key] = report
        return report

    if root.is_dir():
        issues.extend(check_fs_path(root))
        # Muestra acotada de archivos (evitar coste excesivo)
        n = 0
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            n += 1
            try:
                rel = f.relative_to(root).as_posix()
            except ValueError:
                rel = f.name
            issues.extend(check_relative_path(rel))
            issues.extend(check_fs_path(f, root=root))
            if inspect_zips and f.suffix.lower() == ".zip":
                zip_reports.append(inspect_zip(f))
            if n >= 800:
                issues.append(
                    PathSafetyIssue(
                        "SCAN_CAP",
                        "Análisis limitado a 800 archivos (inventario grande)",
                        str(root),
                        False,
                    )
                )
                break

    for zr in zip_reports:
        if not zr.ok:
            issues.extend(zr.issues)

    installable = list(mc.installable)
    groups: list[FileGroup] = []
    if ad.iostore_sidecars:
        # Agrupar por todos los pak/utoc/ucas vistos en el mod (no solo instalables)
        all_ios = [
            fc.rel
            for fc in mc.files
            if Path(fc.rel).suffix.lower() in {".pak", ".utoc", ".ucas"}
        ]
        if not all_ios:
            all_ios = list(mod.paks)
        groups = _iostore_groups(all_ios)

    pak_names = list(mc.pak_names or mod.paks)
    variants = _variant_hints(pak_names)
    if mc.variant_pending or (mod.multi and not mod.pak_elegido):
        # Confirmado por reglas de plan existentes
        if not any(v.label == "PENDIENTE_ELECCION" for v in variants):
            variants.insert(
                0,
                VariantHint(
                    label="PENDIENTE_ELECCION",
                    members=pak_names,
                    certainty=Certainty.CONFIRMED,
                    note="Varias .pak y ninguna elegida (regla de plan)",
                ),
            )

    # Colisiones de destino dentro del mod (mismo dest_rel, distintos archivos)
    dest_map: dict[str, list[str]] = {}
    for fc in mc.files:
        if fc.kind != ContentKind.INSTALLABLE:
            continue
        dest = (fc.dest_rel or Path(fc.rel).name).replace("\\", "/").lower()
        dest_map.setdefault(dest, []).append(fc.rel)
    for dest, rels in dest_map.items():
        if len(set(r.lower() for r in rels)) > 1:
            issues.append(
                PathSafetyIssue(
                    "INTERNAL_DEST_COLLISION",
                    f"Varios archivos → mismo destino '{dest}': {', '.join(rels[:4])}",
                    dest,
                    True,
                )
            )

    incomplete_groups = [g for g in groups if not g.complete_for_adapter]
    confirmed_blocks = [i for i in issues if i.confirmed]
    zip_bad = any(not z.ok for z in zip_reports)

    # Clasificación
    classification = SIMPLE
    certainty = Certainty.CONFIRMED
    explanation = ""
    blocks = False
    manual = False

    if not root.is_dir() and not mod.paks and not getattr(mod, "work_extracted", False):
        classification = SIN_ARCHIVOS_INSTALABLES
        explanation = "No hay carpeta de origen ni archivos .pak conocidos."
        blocks = True
    elif mc.special and not mc.has_installable:
        classification = NO_SOPORTADO
        certainty = Certainty.CONFIRMED
        explanation = (
            "Solo contenido de destino especial (p. ej. inyector/DLL); "
            "no va a Paks/~mods con el adaptador actual."
        )
        blocks = True
        manual = True
    elif not mc.has_installable and not pak_names:
        classification = SIN_ARCHIVOS_INSTALABLES
        explanation = "Sin archivos instalables según el adaptador."
        blocks = True
    elif incomplete_groups and ad.iostore_sidecars:
        classification = INCOMPLETO
        certainty = Certainty.CONFIRMED
        explanation = (
            "Hay grupos IoStore incompletos (.pak/.utoc/.ucas). "
            "No se debe instalar un subconjunto parcial."
        )
        blocks = True
    elif mc.variant_pending or (mod.multi and mod.usar and not mod.pak_elegido):
        classification = CON_VARIANTES
        certainty = Certainty.CONFIRMED
        explanation = "Hay variantes .pak; se requiere elección manual antes de preparar."
        blocks = bool(mod.usar)
        manual = True
    elif len(pak_names) > 1:
        classification = CON_VARIANTES
        certainty = Certainty.CONFIRMED
        explanation = "Varias .pak detectadas (familia de variantes)."
        manual = not bool(mod.pak_elegido)
    elif len(installable) > 3 or (ad.iostore_sidecars and groups and len(groups) > 1):
        classification = COMPUESTO
        certainty = Certainty.CONFIRMED
        explanation = "Varios archivos/grupos instalables en el mismo mod."
    elif confirmed_blocks or zip_bad:
        classification = AMBIGUO
        certainty = Certainty.CONFIRMED
        explanation = "Problemas de seguridad o rutas confirman bloqueo / revisión."
        blocks = True
        manual = True
    elif any(not i.confirmed for i in issues) or (
        variants and any(v.certainty == Certainty.HEURISTIC for v in variants)
    ):
        # Heurísticas solas no bloquean si hay instalables claros
        if mc.has_installable and not incomplete_groups:
            classification = SIMPLE if len(installable) <= 3 else COMPUESTO
            certainty = Certainty.HEURISTIC
            explanation = (
                "Estructura usable; hay indicios heurísticos (variantes/nombres) "
                "que no sustituyen revisión."
            )
            manual = bool(variants) and len(pak_names) > 1 and not mod.pak_elegido
        else:
            classification = AMBIGUO
            certainty = Certainty.HEURISTIC
            explanation = "Ambigüedad heurística; se requiere revisión manual."
            blocks = True
            manual = True
    else:
        classification = SIMPLE
        certainty = Certainty.CONFIRMED
        explanation = "Un conjunto instalable claro según el adaptador."

    # Special+installable mezcla → revisión
    if mc.special and mc.has_installable:
        manual = True
        if classification == SIMPLE:
            classification = COMPUESTO
        explanation += " Contiene también archivos de destino especial (revisión)."

    fmt = _format_label(adapter_id, installable or pak_names)
    report = StructureReport(
        folder=mod.folder,
        name=mod.name,
        adapter_id=adapter_id,
        classification=classification,
        certainty=certainty,
        explanation=explanation.strip(),
        format_label=fmt,
        installable=installable,
        groups=groups,
        variants=variants,
        issues=issues,
        zip_reports=zip_reports,
        blocks_prepare=blocks,
        needs_manual_review=manual or blocks,
        analyzed_ms=(time.perf_counter() - t0) * 1000.0,
        fingerprint=fp,
    )
    if cache is not None:
        cache[cache_key] = report
    return report


def analyze_library_structures(
    mods: list[ModEntry],
    adapter_id: str,
    *,
    cache: dict[str, StructureReport] | None = None,
    only_usar: bool = False,
) -> dict[str, StructureReport]:
    out: dict[str, StructureReport] = {}
    store = cache if cache is not None else {}
    for m in mods:
        if only_usar and not m.usar:
            continue
        out[m.folder] = analyze_mod_structure(m, adapter_id, cache=store)
    return out


def structure_blocks_apply(reports: dict[str, StructureReport], mods: list[ModEntry]) -> bool:
    """True si algún mod activo en plan tiene bloqueo de estructura."""
    active = {m.folder for m in mods if m.usar}
    for folder in active:
        r = reports.get(folder)
        if r and r.blocks_prepare:
            return True
    return False
