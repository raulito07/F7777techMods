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

S50 — carga y validación de adaptadores JSON comunitarios (sin ejecutar código).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .community_adapter_api import (
    ALLOWED_PERMISSIONS_V1,
    COMMUNITY_ADAPTER_API_VERSION,
    SUPPORTED_API_VERSIONS,
    AdapterOrigin,
    CommunityAdapterSpec,
    CompatibilityClaim,
    DestinationDeclaration,
    DetectionHint,
    EvidenceKind,
    FormatDeclaration,
    ManualInstruction,
)
from .community_adapter_security import sanitize_community_document

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
PERMISSION_REQUEST = "request_code_extension_review"


@dataclass
class LoadResult:
    spec: CommunityAdapterSpec | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    path: str = ""

    @property
    def ok(self) -> bool:
        return self.spec is not None and not self.errors


def _evidence(raw: str | None) -> EvidenceKind:
    m = {
        "confirmada": EvidenceKind.CONFIRMED,
        "confirmed": EvidenceKind.CONFIRMED,
        "probable": EvidenceKind.PROBABLE,
        "debil": EvidenceKind.WEAK,
        "weak": EvidenceKind.WEAK,
        "ninguna": EvidenceKind.NONE,
        "none": EvidenceKind.NONE,
        "sin_pruebas": EvidenceKind.UNTESTED,
        "untested": EvidenceKind.UNTESTED,
        "": EvidenceKind.UNTESTED,
    }
    return m.get((raw or "").strip().lower(), EvidenceKind.UNTESTED)


def validate_structure(raw: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    ver = str(raw.get("api_version") or "")
    if ver not in SUPPORTED_API_VERSIONS:
        errs.append(
            f"api_version '{ver}' no soportada (esperada {COMMUNITY_ADAPTER_API_VERSION})"
        )
    aid = str(raw.get("adapter_id") or "")
    if not _ID_RE.match(aid):
        errs.append("adapter_id inválido (^[a-z][a-z0-9_]{1,63}$)")
    if not str(raw.get("display_name") or "").strip():
        errs.append("display_name obligatorio")
    games = raw.get("game_ids")
    if not isinstance(games, list) or not games:
        errs.append("game_ids debe ser lista no vacía")
    elif any(not str(g).strip() for g in games):
        errs.append("game_ids contiene entradas vacías")
    formats = raw.get("formats")
    if formats is not None and not isinstance(formats, list):
        errs.append("formats debe ser lista")
    for p in raw.get("permissions") or []:
        if str(p) not in ALLOWED_PERMISSIONS_V1:
            errs.append(f"permiso desconocido o no concedido: {p}")
    return errs


def document_to_spec(raw: dict[str, Any]) -> CommunityAdapterSpec:
    formats = []
    for f in raw.get("formats") or []:
        if not isinstance(f, dict):
            continue
        exts = tuple(
            str(e) if str(e).startswith(".") else f".{e}"
            for e in (f.get("extensions") or [])
        )
        formats.append(
            FormatDeclaration(
                id=str(f.get("id") or "fmt"),
                extensions=exts,
                label=str(f.get("label") or ""),
                installer_id=str(f.get("installer_id") or ""),
                notes=str(f.get("notes") or ""),
            )
        )
    destinations = []
    for d in raw.get("destinations") or []:
        if not isinstance(d, dict):
            continue
        destinations.append(
            DestinationDeclaration(
                id=str(d.get("id") or "dest"),
                relative_path=str(d.get("relative_path") or d.get("path") or ""),
                format_ids=tuple(str(x) for x in (d.get("format_ids") or [])),
                verified=bool(d.get("verified")),
                evidence=_evidence(str(d.get("evidence") or "")),
                notes=str(d.get("notes") or ""),
            )
        )
    det_raw = raw.get("detection") or {}
    if not isinstance(det_raw, dict):
        det_raw = {}
    detection = DetectionHint(
        steam_app_ids=tuple(str(x) for x in (det_raw.get("steam_app_ids") or [])),
        folder_name_contains=tuple(
            str(x) for x in (det_raw.get("folder_name_contains") or [])
        ),
        required_relative_paths=tuple(
            str(x) for x in (det_raw.get("required_relative_paths") or [])
        ),
        notes=str(det_raw.get("notes") or ""),
    )
    manuals = []
    for m in raw.get("manual_instructions") or raw.get("manual") or []:
        if not isinstance(m, dict):
            continue
        steps = tuple(str(s) for s in (m.get("steps") or []))
        manuals.append(
            ManualInstruction(
                title=str(m.get("title") or "Manual"),
                steps=steps,
                confirmed=bool(m.get("confirmed")),
            )
        )
    compat = None
    craw = raw.get("compatibility")
    if isinstance(craw, dict) and craw.get("summary"):
        compat = CompatibilityClaim(
            summary=str(craw.get("summary")),
            evidence=_evidence(str(craw.get("evidence") or "")),
            test_refs=tuple(str(x) for x in (craw.get("test_refs") or [])),
        )
    origin = AdapterOrigin.COMMUNITY_DECLARATIVE
    perms_list = [str(p) for p in (raw.get("permissions") or [])]
    if raw.get("code_extension_requested") or PERMISSION_REQUEST in perms_list:
        origin = AdapterOrigin.COMMUNITY_CODE_PENDING

    return CommunityAdapterSpec(
        api_version=str(raw.get("api_version")),
        adapter_id=str(raw.get("adapter_id")),
        display_name=str(raw.get("display_name")),
        game_ids=tuple(str(g) for g in (raw.get("game_ids") or [])),
        origin=origin,
        formats=tuple(formats),
        destinations=tuple(destinations),
        detection=detection,
        dependencies_notes=str(raw.get("dependencies_notes") or ""),
        conflicts_notes=str(raw.get("conflicts_notes") or ""),
        capabilities=tuple(str(x) for x in (raw.get("capabilities") or [])),
        manual=tuple(manuals),
        compatibility=compat,
        permissions=tuple(str(p) for p in (raw.get("permissions") or [])),
        limitations=tuple(str(x) for x in (raw.get("limitations") or [])),
        author=str(raw.get("author") or ""),
        license=str(raw.get("license") or "GPL-3.0-or-later"),
        auto_install_allowed=False,
        maps_to_official_adapter=str(raw.get("maps_to_official_adapter") or ""),
        raw=dict(raw),
    )


def load_community_adapter_file(path: Path) -> LoadResult:
    result = LoadResult(path=str(path))
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
    except Exception as exc:
        result.errors.append(f"JSON inválido: {exc}")
        return result
    if not isinstance(raw, dict):
        result.errors.append("raíz JSON debe ser objeto")
        return result

    sec = sanitize_community_document(raw)
    result.warnings.extend(sec.warnings)
    if not sec.ok:
        result.errors.extend(sec.errors)
        return result

    struct_errs = validate_structure(raw)
    if struct_errs:
        result.errors.extend(struct_errs)
        return result

    # Formato declarado sin instalador → warning, no error
    for f in raw.get("formats") or []:
        if isinstance(f, dict) and not (f.get("installer_id") or "").strip():
            result.warnings.append(
                f"formato '{f.get('id')}' sin installer_id "
                "(reconocido, sin instalación automática)"
            )

    if raw.get("compatibility") and _evidence(
        str((raw.get("compatibility") or {}).get("evidence") or "")
    ) == EvidenceKind.UNTESTED:
        result.warnings.append("compatibilidad declarada sin pruebas")

    result.spec = document_to_spec(raw)
    return result


def load_community_adapters_dir(root: Path) -> list[LoadResult]:
    """Carga *.json bajo root (incluye examples/). No ejecuta nada."""
    out: list[LoadResult] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.json")):
        # ignorar schema
        if "schema" in path.name.lower():
            continue
        out.append(load_community_adapter_file(path))
    return out
