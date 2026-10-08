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

S21 — identidad, Acerca de, rutas sin hardcode de autor, arranque limpio.
Solo temporales.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class S21IdentityTests(unittest.TestCase):
    def test_version_and_title(self):
        from app.version import __executable_name__, __title__, __version__
        from app.branding import PRODUCT_NAME, window_title, configured_links

        self.assertEqual(__version__, "0.1.0")
        self.assertEqual(__title__, "F7777techMods")
        self.assertEqual(PRODUCT_NAME, "F7777techMods")
        self.assertEqual(__executable_name__, "F7777techMods")
        self.assertIn("F7777techMods", window_title())
        links = configured_links()
        by_label = dict(links)
        self.assertEqual(by_label["Web oficial"], "https://fourseven.es/")
        self.assertEqual(
            by_label["GitHub"], "https://github.com/raulito07/F7777techMods"
        )
        self.assertEqual(
            by_label["Releases"],
            "https://github.com/raulito07/F7777techMods/releases",
        )
        self.assertEqual(len(links), 3)

    def test_no_author_username_in_core_paths(self):
        for rel in (
            "app/core/paths.py",
            "app/core/games.py",
            "app/core/vortex_sync.py",
            "app/branding.py",
            "app/version.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            # Construir aguja sin literales de cuenta en el fuente (auditoría S21).
            needle_win = "Users" + "\\" + "raul" + "_"
            needle_posix = "Users" + "/" + "raul" + "_"
            self.assertNotIn(needle_win, text, rel)
            self.assertNotIn(needle_posix, text, rel)

    def test_about_view_and_nav(self):
        from app.ui.theme import NAV_ITEMS
        from app.ui.views.about import AboutView
        from app.branding import about_lines

        keys = [k for k, _ in NAV_ITEMS]
        self.assertIn("about", keys)
        lines = about_lines()
        self.assertTrue(any("F7777techMods" in ln for ln in lines))
        self.assertTrue(
            any("github.com/raulito07/F7777techMods" in ln for ln in lines)
        )

    def test_clean_boot_data_dir(self):
        td = tempfile.TemporaryDirectory()
        try:
            data = Path(td.name) / "clean_data"
            data.mkdir()
            env = {"SGM_DATA_DIR": str(data)}
            with mock.patch.dict(os.environ, env, clear=False):
                # Reimport paths under env
                import importlib
                import app.core.paths as paths_mod

                importlib.reload(paths_mod)
                self.assertEqual(paths_mod.DATA.resolve(), data.resolve())
                # games registry path under temp
                self.assertTrue(str(paths_mod.GAMES_REGISTRY).startswith(str(data)))
        finally:
            td.cleanup()
            import importlib
            import app.core.paths as paths_mod

            importlib.reload(paths_mod)

    def test_header_marker_present_in_branding(self):
        text = (ROOT / "app" / "branding.py").read_text(encoding="utf-8")
        self.assertIn("F7777techMods — Gestor multijuego de mods.", text)


if __name__ == "__main__":
    unittest.main()
