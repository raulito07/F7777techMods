# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S40 — decisiones manuales de estructura (identidad estable + huella de origen).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .inventory import ModEntry
from .mod_structure import (
    AMBIGUO,
    CON_VARIANTES,
    INCOMPLETO,
    StructureReport,
    analyze_mod_structure,
)

ACK_UNSUPPORTED = "ACK_UNSUPPORTED"
CONFIRM_SIMPLE = "CONFIRM_SIMPLE"
CHOOSE_VARIANT = "CHOOSE_VARIANT"
INSTALL_ALL_COMPOUND = "INSTALL_ALL_COMPOUND"


@dataclass
class StructureResolution:
    folder: str
    fingerprint: str
    action: str
    pak_choice: str = ""
    paks_all: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "folder": self.folder,
            "fingerprint": self.fingerprint,
            "action": self.action,
            "pak_choice": self.pak_choice,
            "paks_all": list(self.paks_all),
            "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict) -> StructureResolution | None:
        if not isinstance(d, dict) or not d.get("folder"):
            return None
        return StructureResolution(
            folder=str(d["folder"]),
            fingerprint=str(d.get("fingerprint") or ""),
            action=str(d.get("action") or ""),
            pak_choice=str(d.get("pak_choice") or ""),
            paks_all=[str(x) for x in (d.get("paks_all") or [])],
            note=str(d.get("note") or ""),
        )


def load_structure_resolutions(path: Path | None) -> dict[str, StructureResolution]:
    if path is None or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, StructureResolution] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            r = StructureResolution.from_dict(v if isinstance(v, dict) else {"folder": k})
            if r:
                out[r.folder] = r
    return out


def save_structure_resolutions(
    path: Path | None, resolutions: dict[str, StructureResolution]
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.to_dict() for k, v in sorted(resolutions.items())}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolution_valid(report: StructureReport, res: StructureResolution | None) -> bool:
    if res is None:
        return False
    if res.folder != report.folder:
        return False
    if report.fingerprint and res.fingerprint != report.fingerprint:
        return False
    return True


def apply_resolution_to_mod(mod: ModEntry, res: StructureResolution) -> None:
    """Aplica elección manual al ModEntry (loadout); no omite comprobaciones de Apply."""
    if res.action == CHOOSE_VARIANT and res.pak_choice:
        mod.pak_elegido = res.pak_choice
        mod.paks_elegidos = [res.pak_choice]
        mod.multi = len(mod.paks) > 1
    elif res.action == INSTALL_ALL_COMPOUND and res.paks_all:
        mod.paks_elegidos = list(res.paks_all)
        mod.pak_elegido = mod.paks_elegidos[0]
        mod.multi = len(mod.paks) > 1


def effective_blocks_prepare(
    report: StructureReport,
    res: StructureResolution | None,
) -> bool:
    """Bloqueo real de preparación/Apply global por este mod."""
    if resolution_valid(report, res):
        if res.action == ACK_UNSUPPORTED:
            return False
        if res.action == CONFIRM_SIMPLE:
            return False
        if res.action == CHOOSE_VARIANT and res.pak_choice:
            return False
        if res.action == INSTALL_ALL_COMPOUND and res.paks_all:
            return False
    if report.classification in (AMBIGUO, INCOMPLETO):
        return report.blocks_prepare
    if report.classification == CON_VARIANTES:
        return report.blocks_prepare
    # Formatos no admitidos / sin instalables: aviso, no bloquean el resto del plan
    if not report.installable and report.classification in {
        "SIN_ARCHIVOS_INSTALABLES",
        "NO_SOPORTADO",
        "FORMATO_NO_PAK",
    }:
        return False
    return report.blocks_prepare


def structure_procedure(report: StructureReport) -> str:
    """Pasos seguros sugeridos según clasificación (sin inventar destinos)."""
    cls = report.classification
    if cls == "FORMATO_NO_PAK":
        return (
            "1) Este mod no contiene .pak instalables con el adaptador actual.\n"
            "2) Desactívelo en plan si solo usa F7777techMods para despliegue PAK,\n"
            "   o despliegue el contenido con la herramienta indicada (p. ej. Vortex).\n"
            "3) Pulse «Reconocer: no desplegable aquí» para quitar el aviso de revisión."
        )
    if cls == CON_VARIANTES:
        return (
            "1) Abra «Revisar estructura» y elija UNA variante .pak,\n"
            "   o confirme instalar todos los componentes si son independientes.\n"
            "2) Guarde; se revalidará si cambia la carpeta de origen."
        )
    if cls == INCOMPLETO:
        return (
            "1) Complete grupos IoStore (.pak+.utoc+.ucas) en origen\n"
            "   o desactive el mod en plan hasta tener el grupo entero."
        )
    if cls == AMBIGUO:
        return (
            "1) Revise archivos y rutas en «Revisar estructura».\n"
            "2) Resuelva colisiones o confirme solo si el adaptador demuestra destino seguro."
        )
    if cls == "SIN_ARCHIVOS_INSTALABLES":
        return (
            "1) Compruebe que la carpeta staging existe y contiene archivos del mod.\n"
            "2) Actualice inventario; si la fuente falta, reactive desde Vortex/WORK."
        )
    if report.needs_manual_review:
        return "1) Abra «Revisar estructura» para ver archivos y confirmar la relación."
    return "Estructura clara; no requiere revisión manual."


def structure_row_state(
    report: StructureReport | None,
    res: StructureResolution | None,
    *,
    usar: bool,
) -> tuple[str, str]:
    """(tag S39, etiqueta corta) para Biblioteca."""
    if not usar or report is None:
        return "unchanged", "—"
    if resolution_valid(report, res) and res.action == ACK_UNSUPPORTED:
        return "unchanged", "No desplegable (reconocido)"
    if report.classification == "FORMATO_NO_PAK":
        if resolution_valid(report, res):
            return "unchanged", "No desplegable (reconocido)"
        return "pending", "Formato no PAK (.emov…)"
    if effective_blocks_prepare(report, res):
        short = report.classification.replace("_", " ")[:22]
        if report.classification == "FORMATO_NO_PAK":
            return "pending", "Formato no PAK (.emov…)"
        if report.classification == CON_VARIANTES:
            return "pending", "Elegir variante .pak"
        if report.classification == INCOMPLETO:
            return "pending", "Grupo IoStore incompleto"
        if report.classification == AMBIGUO:
            return "pending", "Ambigüedad — revisar"
        return "pending", f"Revisión: {short}"
    if report.needs_manual_review and not resolution_valid(report, res):
        return "pending", "Revisión recomendada"
    return "unchanged", "Estructura OK"


def format_review_body(
    mod: ModEntry,
    report: StructureReport,
    res: StructureResolution | None,
    *,
    file_list: list[str],
) -> str:
    lines = [
        f"Mod: {mod.name}",
        f"Carpeta: {mod.folder}",
        f"Clasificación: {report.classification} ({report.certainty.value})",
        f"Formato: {report.format_label}",
        "",
        report.explanation,
        "",
        "Procedimiento:",
        structure_procedure(report),
        "",
    ]
    if res and resolution_valid(report, res):
        lines.append(f"Decisión guardada: {res.action} ({res.note or '—'})")
    elif res and not resolution_valid(report, res):
        lines.append("Decisión anterior CADUCADA (cambió el contenido de origen).")
    lines.append("")
    lines.append(f"Archivos ({len(file_list)}):")
    for rel in file_list[:40]:
        lines.append(f"  • {rel}")
    if len(file_list) > 40:
        lines.append(f"  • … y {len(file_list) - 40} más")
    if report.variants:
        lines.append("")
        lines.append("Variantes / componentes detectados:")
        for v in report.variants[:8]:
            lines.append(f"  • {v.label}: {', '.join(v.members[:6])}")
    return "\n".join(lines)


def list_structure_files(mod: ModEntry, limit: int = 120) -> list[str]:
    root = Path(mod.stage_path) if mod.stage_path else Path()
    if not root.is_dir():
        return list(mod.paks)[:limit]
    out: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            out.append(p.relative_to(root).as_posix())
        except ValueError:
            out.append(p.name)
        if len(out) >= limit:
            out.append("…")
            break
    return out


def reanalyze_with_resolution(
    mod: ModEntry,
    adapter_id: str,
    res: StructureResolution | None,
) -> StructureReport:
    report0 = analyze_mod_structure(mod, adapter_id)
    if res and resolution_valid(report0, res):
        apply_resolution_to_mod(mod, res)
    return analyze_mod_structure(mod, adapter_id)
