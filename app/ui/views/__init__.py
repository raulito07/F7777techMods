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
"""

from .summary import SummaryView
from .library import LibraryView
from .conflicts import ConflictsView
from .installed import InstalledView
from .storage_archive import StorageArchiveView
from .history import HistoryView
from .settings import SettingsView
from .about import AboutView

__all__ = [
    "SummaryView",
    "LibraryView",
    "ConflictsView",
    "InstalledView",
    "StorageArchiveView",
    "HistoryView",
    "SettingsView",
    "AboutView",
]
