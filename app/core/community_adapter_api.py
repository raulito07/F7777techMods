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

S50 — interfaz pública versionada de adaptadores comunitarios.
Declarativo (JSON). No ejecuta código de terceros.
Reconocer ≠ instalar automáticamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

# Versión de contrato público. Incrementar solo con cambios incompatibles.
COMMUNITY_ADAPTER_API_VERSION = "1.0"
SUPPORTED_API_VERSIONS = frozenset({"1.0"})

PERMISSION_DECLARE_FORMATS = "declare_formats"
PERMISSION_DECLARE_DESTINATIONS = "declare_destinations"
PERMISSION_DECLARE_MANUAL = "declare_manual_instructions"
PERMISSION_DECLARE_DETECTION = "declare_game_detection"
PERMISSION_REQUEST_CODE_REVIEW = "request_code_extension_review"

ALLOWED_PERMISSIONS_V1 = frozenset(
    {
        PERMISSION_DECLARE_FORMATS,
        PERMISSION_DECLARE_DESTINATIONS,
        PERMISSION_DECLARE_MANUAL,
        PERMISSION_DECLARE_DETECTION,
        PERMISSION_REQUEST_CODE_REVIEW,
    }
)

FORBIDDEN_DECLARATIVE_KEYS = frozenset(
    {
        "execute",
        "exec",
        "python",
        "script",
        "shell",
        "subprocess",
        "eval",
        "import",
        "bypass_backup",
        "bypass_confirm",
        "bypass_rollback",
        "bypass_path_validation",
        "overwrite_originals",
        "force_apply",
        "skip_foreign_check",
        "auto_apply",
        "enable_apply",
        "apply_enabled",
        "disable_safety",
    }
)


class RecognitionLayer(str, Enum):
    """Capas independientes. Nunca colapsar en un solo booleano."""

    GAME_RECOGNIZED = "juego_reconocido"
    MOD_RECOGNIZED = "mod_reconocido"
    FORMAT_RECOGNIZED = "formato_reconocido"
    DESTINATION_VERIFIED = "destino_verificado"
    AUTO_INSTALL_COMPATIBLE = "instalacion_automatica_compatible"


class AdapterOrigin(str, Enum):
    OFFICIAL = "oficial"
    COMMUNITY_DECLARATIVE = "comunitario_declarativo"
    COMMUNITY_CODE_PENDING = "comunitario_codigo_pendiente_revision"


class EvidenceKind(str, Enum):
    CONFIRMED = "confirmada"
    PROBABLE = "probable"
    WEAK = "debil"
    NONE = "ninguna"
    UNTESTED = "sin_pruebas"


@dataclass(frozen=True)
class FormatDeclaration:
    id: str
    extensions: tuple[str, ...]
    label: str = ""
    installer_id: str = ""
    notes: str = ""


@dataclass(frozen=True)
class DestinationDeclaration:
    id: str
    relative_path: str
    format_ids: tuple[str, ...] = ()
    verified: bool = False
    evidence: EvidenceKind = EvidenceKind.UNTESTED
    notes: str = ""


@dataclass(frozen=True)
class DetectionHint:
    steam_app_ids: tuple[str, ...] = ()
    folder_name_contains: tuple[str, ...] = ()
    required_relative_paths: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ManualInstruction:
    title: str
    steps: tuple[str, ...]
    confirmed: bool = False


@dataclass(frozen=True)
class CompatibilityClaim:
    summary: str
    evidence: EvidenceKind = EvidenceKind.UNTESTED
    test_refs: tuple[str, ...] = ()


@dataclass
class CommunityAdapterSpec:
    """Especificación pública v1 (JSON → modelo). Nunca autoriza Apply sola."""

    api_version: str
    adapter_id: str
    display_name: str
    game_ids: tuple[str, ...]
    origin: AdapterOrigin = AdapterOrigin.COMMUNITY_DECLARATIVE
    formats: tuple[FormatDeclaration, ...] = ()
    destinations: tuple[DestinationDeclaration, ...] = ()
    detection: DetectionHint = field(default_factory=DetectionHint)
    dependencies_notes: str = ""
    conflicts_notes: str = ""
    capabilities: tuple[str, ...] = ()
    manual: tuple[ManualInstruction, ...] = ()
    compatibility: CompatibilityClaim | None = None
    permissions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    author: str = ""
    license: str = "GPL-3.0-or-later"
    auto_install_allowed: bool = False
    maps_to_official_adapter: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def recognition_snapshot(
        self,
        *,
        formats_present: Iterable[str] | None = None,
        destination_on_disk: bool = False,
    ) -> dict[RecognitionLayer, bool]:
        fmts = {str(x).lower() for x in (formats_present or [])}
        fmt_ok = False
        for f in self.formats:
            exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in f.extensions}
            if fmts & exts or f.id.lower() in fmts:
                fmt_ok = True
                break
        dest_verified = destination_on_disk and any(
            d.verified and d.evidence == EvidenceKind.CONFIRMED for d in self.destinations
        )
        return {
            RecognitionLayer.GAME_RECOGNIZED: True,
            RecognitionLayer.MOD_RECOGNIZED: bool(fmts),
            RecognitionLayer.FORMAT_RECOGNIZED: fmt_ok,
            RecognitionLayer.DESTINATION_VERIFIED: dest_verified,
            RecognitionLayer.AUTO_INSTALL_COMPATIBLE: False,
        }


def recognition_layers_blank() -> dict[RecognitionLayer, bool]:
    return {layer: False for layer in RecognitionLayer}
