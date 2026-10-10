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

S50 — política de seguridad para adaptadores comunitarios.
No ejecuta Python/scripts de terceros. No omite protecciones Apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .community_adapter_api import FORBIDDEN_DECLARATIVE_KEYS


@dataclass
class SecurityVerdict:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Siempre False para comunitario v1 tras sanitize
    auto_install_allowed: bool = False
    code_execution_requested: bool = False


def _walk_keys(obj: Any, found: set[str] | None = None) -> set[str]:
    if found is None:
        found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(str(k))
            _walk_keys(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_keys(item, found)
    return found


def path_is_unsafe(rel: str) -> tuple[bool, str]:
    """Rutas relativas inseguras (absolutización, traversal, UNC)."""
    s = (rel or "").strip().replace("\\", "/")
    if not s:
        return True, "ruta vacía"
    if s.startswith("/") or (len(s) >= 2 and s[1] == ":"):
        return True, "ruta absoluta no permitida"
    if s.startswith("//") or s.startswith("\\\\"):
        return True, "UNC / red no permitido"
    parts = PurePosixPath(s).parts
    if ".." in parts:
        return True, "traversal '..' prohibido"
    if any(p.startswith("~") for p in parts):
        return True, "expansión home no permitida"
    return False, ""


def scan_forbidden_keys(raw: dict[str, Any]) -> list[str]:
    keys = {k.lower() for k in _walk_keys(raw)}
    hits = sorted(keys & {k.lower() for k in FORBIDDEN_DECLARATIVE_KEYS})
    return hits


def sanitize_community_document(raw: dict[str, Any]) -> SecurityVerdict:
    """
    Valida y neutraliza intentos de omitir el motor.
    - Fuerza auto_install / apply a False.
    - Detecta petición de código ejecutable (no se carga).
    """
    v = SecurityVerdict(ok=True)
    if not isinstance(raw, dict):
        return SecurityVerdict(ok=False, errors=["documento no es un objeto JSON"])

    forbidden = scan_forbidden_keys(raw)
    if forbidden:
        v.ok = False
        v.errors.append(
            "Claves prohibidas (intentan omitir seguridad o ejecutar código): "
            + ", ".join(forbidden)
        )

    # Flags de apply / overwrite → siempre rechazados o forzados
    for key in ("auto_install", "auto_install_allowed", "can_auto_install", "apply"):
        if key in raw and raw.get(key) is True:
            v.warnings.append(
                f"'{key}=true' ignorado: adaptadores comunitarios no habilitan Apply"
            )
            raw[key] = False

    # Destinos
    for dest in raw.get("destinations") or []:
        if not isinstance(dest, dict):
            continue
        rel = str(dest.get("relative_path") or dest.get("path") or "")
        bad, why = path_is_unsafe(rel)
        if bad:
            v.ok = False
            v.errors.append(f"destino inseguro '{rel}': {why}")
        if dest.get("overwrite_originals") is True:
            v.ok = False
            v.errors.append("overwrite_originals no permitido")
        # verified sin evidence confirmada → degradar
        if dest.get("verified") is True and str(dest.get("evidence") or "") not in (
            "confirmada",
            "confirmed",
        ):
            v.warnings.append(
                f"destino '{dest.get('id', rel)}': verified degradado (sin evidencia confirmada)"
            )
            dest["verified"] = False

    # Código ejecutable
    code_block = raw.get("code") or raw.get("plugin") or raw.get("entrypoint")
    if code_block:
        v.code_execution_requested = True
        v.ok = False
        v.errors.append(
            "Extensiones con código no se cargan en v1. "
            "Use permission 'request_code_extension_review' y abra revisión de seguridad."
        )

    perms = [str(p) for p in (raw.get("permissions") or [])]
    if "execute_code" in perms or "run_python" in perms:
        v.code_execution_requested = True
        v.ok = False
        v.errors.append("permiso de ejecución de código no concedido en API 1.0")

    v.auto_install_allowed = False
    raw["auto_install_allowed"] = False
    return v


def community_cannot_bypass_apply_guards() -> dict[str, bool]:
    """Contrato documentado: guards del motor siempre activos."""
    return {
        "path_validation": True,
        "foreign_file_protection": True,
        "backup_required": True,
        "user_confirmation": True,
        "rollback": True,
        "apply_engine_restrictions": True,
        "community_auto_install": False,
    }


def resolve_community_root(override: Path | None = None) -> Path:
    """Carpeta de adaptadores comunitarios (repo o datos locales)."""
    if override is not None:
        return Path(override)
    # Preferir ejemplos del repo; datos de usuario opcionales vía env
    import os

    env = (os.environ.get("SGM_COMMUNITY_ADAPTERS") or "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[2]
    return here / "community_adapters"
