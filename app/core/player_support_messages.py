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

S50 — mensajes comprensibles para Biblioteca (sin JSON técnico al jugador).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mod_investigator import InvestigationReport

_CAP_PLAYER = {
    "INSTALACION_CONFIRMADA": "Este mod se puede instalar con F7777techMods de forma segura.",
    "INSTALACION_PROBABLE": "Hay indicios de cómo instalarlo, pero aún falta validación.",
    "INSTALACION_EXTERNA": "Parece necesitar otra herramienta (no el instalador automático de F7777).",
    "NO_SOPORTADO": "F7777techMods reconoce el tipo de archivo, pero aún no puede instalarlo solo.",
    "DESCONOCIDO": "F7777techMods no sabe aún cómo instalar este mod de forma segura.",
}

_FMT_PLAYER = {
    "pak": "paquetes .pak",
    "iostore": "paquetes IoStore (.pak/.utoc/.ucas)",
    "media_movie": "vídeo / cinemáticas",
    "script_lua": "scripts (p. ej. Lua)",
    "injector_tool": "herramienta o inyector",
    "config_ini": "archivos de configuración",
    "reshade": "shaders ReShade",
    "archive_meta": "solo metadatos (sin archivos del mod)",
    "empty": "carpeta vacía",
    "unknown": "formato no identificado",
    "binary_other": "binarios varios",
}


def player_facing_investigation(report: InvestigationReport | None) -> str:
    """Resumen claro para el panel principal (no técnico)."""
    if report is None:
        return (
            "Estado del mod\n"
            "Aún no hay análisis. Pulse Actualizar en la Biblioteca."
        )
    cap = getattr(report.capability, "value", str(report.capability))
    head = _CAP_PLAYER.get(cap, _CAP_PLAYER["DESCONOCIDO"])
    fmts = []
    for f in report.formats or []:
        fam = getattr(f.family, "value", str(f.family))
        fmts.append(_FMT_PLAYER.get(fam, fam))
    fmt_txt = ", ".join(dict.fromkeys(fmts)) if fmts else "sin formato claro"

    lines = [
        "Qué sabemos de este mod",
        head,
        f"Contenido detectado: {fmt_txt}.",
    ]
    if report.apply_allowed:
        lines.append("Instalación automática: disponible (motor F7777 ya soportado).")
    else:
        lines.append("Instalación automática: no disponible por ahora.")

    if report.destinations:
        confirmed = [d for d in report.destinations if d.confirmed]
        if confirmed:
            lines.append(f"Destino conocido: {confirmed[0].path_hint}")
        else:
            lines.append(
                "Destino: solo indicios (no confirmado; no se copiará nada automáticamente)."
            )
    else:
        lines.append("Destino: desconocido.")

    if report.missing_steps:
        lines.append("Qué falta:")
        for s in report.missing_steps[:4]:
            lines.append(f"  • {_soften(s)}")
    if report.manual_steps:
        tag = "Instrucciones (confirmadas)" if report.manual_confirmed else "Instrucciones orientativas"
        lines.append(f"{tag}:")
        for s in report.manual_steps[:4]:
            lines.append(f"  • {_soften(s)}")

    if not report.f7777_installable:
        lines.append(
            "Sigue visible en la Biblioteca. Puede consultarse y etiquetarse; "
            "no se instalará hasta que haya un procedimiento seguro."
        )
        lines.append(
            "¿Quiere ayudar? Vea GAME_ADAPTER_GUIDE.md para proponer un adaptador "
            "(sin subir datos personales ni mods)."
        )
    return "\n".join(lines)


def player_facing_unknown_game(*, game_name: str, game_id: str) -> str:
    return (
        f"Juego poco conocido: {game_name or game_id or '(sin nombre)'}\n"
        "F7777techMods puede listar mods si hay carpeta de origen, "
        "pero no garantiza instalación automática.\n"
        "Falta: adaptador revisado con formatos, destinos y pruebas.\n"
        "Cómo ayudar: documente detección y formatos en un JSON comunitario "
        "(GAME_ADAPTER_GUIDE.md). No envíe rutas personales ni archivos del juego."
    )


def player_facing_unknown_mod(*, mod_name: str) -> str:
    return (
        f"Mod sin procedimiento seguro: {mod_name}\n"
        "Se mantiene en la Biblioteca con la información identificada.\n"
        "Abra «Información técnica» solo si necesita el detalle de investigación."
    )


def _soften(s: str) -> str:
    """Quita jerga dura sin inventar datos."""
    t = s
    for a, b in (
        ("game_root", "carpeta del juego"),
        ("Apply", "instalación automática"),
        ("homólogo", "archivo similar en el juego"),
        ("S42", "canal de vídeo del gestor"),
        ("UE4SS", "herramienta de scripts del juego"),
    ):
        t = t.replace(a, b)
    return t
