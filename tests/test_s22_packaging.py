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

Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S22 — licencia GPL, datos LOCALAPPDATA, identidad About.
Solo temporales (salvo lectura de LICENSE).
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class S22PackagingTests(unittest.TestCase):
    def test_license_file_is_gpl3(self):
        lic = (ROOT / "LICENSE").read_text(encoding="utf-8", errors="ignore")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", lic)
        self.assertIn("Version 3", lic)
        self.assertGreater(len(lic), 10_000)

    def test_version_license_field(self):
        from app.version import __license__, __version__

        self.assertEqual(__version__, "0.1.0")
        self.assertEqual(__license__, "GPL-3.0-or-later")

    def test_branding_gpl(self):
        import app.branding as b

        self.assertIn("GPL", b.LICENSE_SHORT)
        self.assertIn("General Public License", b.LICENSE_NAME)
        text = "\n".join(b.about_lines())
        self.assertIn("GPL", text)
        self.assertNotIn("pendiente de publicación", text.lower())
        self.assertFalse(hasattr(b, "RIGHTS_LINE"))

    def test_headers_no_proprietary_ban(self):
        text = (ROOT / "app" / "branding.py").read_text(encoding="utf-8")
        self.assertNotIn("Todos los derechos reservados", text)
        self.assertNotIn("Queda prohibida su reproducción", text)
        self.assertIn("GNU", text)

    def test_frozen_data_uses_localappdata(self):
        td = tempfile.TemporaryDirectory()
        try:
            fake_local = Path(td.name) / "Local"
            fake_local.mkdir()
            import app.core.paths as paths_mod

            with mock.patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(fake_local),
                    "SGM_USE_APPDATA": "1",
                },
                clear=False,
            ):
                os.environ.pop("SGM_DATA_DIR", None)
                expected = fake_local / "FourSevenTech" / "F7777techMods"
                self.assertEqual(
                    paths_mod.resolve_data_dir().resolve(), expected.resolve()
                )
                with mock.patch.object(paths_mod, "is_frozen", return_value=True):
                    os.environ.pop("SGM_USE_APPDATA", None)
                    self.assertEqual(
                        paths_mod.resolve_data_dir().resolve(), expected.resolve()
                    )
        finally:
            td.cleanup()

    def test_dev_data_stays_repo_data(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SGM_DATA_DIR", None)
            os.environ.pop("SGM_USE_APPDATA", None)
            with mock.patch("app.core.paths.is_frozen", return_value=False):
                import app.core.paths as paths_mod

                importlib.reload(paths_mod)
                self.assertEqual(paths_mod.DATA.name, "data")
        import app.core.paths as paths_mod

        importlib.reload(paths_mod)

    def test_sgm_data_dir_override(self):
        td = tempfile.TemporaryDirectory()
        try:
            clean = Path(td.name) / "x"
            clean.mkdir()
            with mock.patch.dict(os.environ, {"SGM_DATA_DIR": str(clean)}, clear=False):
                import app.core.paths as paths_mod

                importlib.reload(paths_mod)
                self.assertEqual(paths_mod.DATA.resolve(), clean.resolve())
        finally:
            td.cleanup()
            import app.core.paths as paths_mod

            importlib.reload(paths_mod)

    def test_third_party_notices_exist(self):
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        self.assertTrue((ROOT / "docs" / "LICENCIAS_AUDITORIA_S22.md").is_file())


if __name__ == "__main__":
    unittest.main()
