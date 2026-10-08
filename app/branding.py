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

S21–S24 — identidad pública, enlaces oficiales y licencia GPL v3.
"""

from __future__ import annotations

from .version import __author__, __company__, __title__, __version__

# Nombre exacto del producto (cuatro sietes: F7777techMods)
PRODUCT_NAME = __title__  # F7777techMods
PRODUCT_TAGLINE = "Gestor multijuego de mods"
PRODUCT_BYLINE = "by Four Seven Tech"
COMPANY_NAME = __company__
AUTHOR_NAME = __author__
COPYRIGHT_LINE = "Copyright (c) 2026 Raúl Ruano Gil."
LICENSE_NAME = "GNU General Public License v3.0 (o posterior)"
LICENSE_SHORT = "GNU GPL v3"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"

# Enlaces oficiales — solo URLs confirmadas. Vacío = oculto (no placeholders activos).
OFFICIAL_WEBSITE_URL = "https://fourseven.es/"
OFFICIAL_GITHUB_URL = "https://github.com/raulito07/F7777techMods"
OFFICIAL_RELEASES_URL = "https://github.com/raulito07/F7777techMods/releases"

INDEPENDENT_APP_NOTICE = (
    "Aplicación independiente. No está afiliada a Square Enix, Steam, "
    "Nexus Mods ni Vortex. Esas marcas pertenecen a sus respectivos titulares."
)


def window_title() -> str:
    return f"{PRODUCT_NAME}  ·  v{__version__}"


def about_lines() -> list[str]:
    lines = [
        PRODUCT_NAME,
        PRODUCT_BYLINE,
        PRODUCT_TAGLINE,
        f"Versión {__version__} Beta",
        "",
        f"Empresa: {COMPANY_NAME}",
        f"Autor: {AUTHOR_NAME}",
        COPYRIGHT_LINE,
        f"Licencia: {LICENSE_SHORT}",
        "",
        INDEPENDENT_APP_NOTICE,
        "",
        "Enlaces oficiales:",
    ]
    if OFFICIAL_WEBSITE_URL.strip():
        lines.append(f"  Web: {OFFICIAL_WEBSITE_URL.strip()}")
    if OFFICIAL_GITHUB_URL.strip():
        lines.append(f"  GitHub: {OFFICIAL_GITHUB_URL.strip()}")
    if OFFICIAL_RELEASES_URL.strip():
        lines.append(f"  Releases: {OFFICIAL_RELEASES_URL.strip()}")
    if not any(
        (
            OFFICIAL_WEBSITE_URL.strip(),
            OFFICIAL_GITHUB_URL.strip(),
            OFFICIAL_RELEASES_URL.strip(),
        )
    ):
        lines.append("  (ningún enlace configurado)")
    lines.append(f"  Texto GPL: {LICENSE_URL}")
    return lines


def configured_links() -> list[tuple[str, str]]:
    """Pares (etiqueta, url) solo si la URL está configurada."""
    out: list[tuple[str, str]] = []
    if OFFICIAL_WEBSITE_URL.strip():
        out.append(("Web oficial", OFFICIAL_WEBSITE_URL.strip()))
    if OFFICIAL_GITHUB_URL.strip():
        out.append(("GitHub", OFFICIAL_GITHUB_URL.strip()))
    if OFFICIAL_RELEASES_URL.strip():
        out.append(("Releases", OFFICIAL_RELEASES_URL.strip()))
    return out
