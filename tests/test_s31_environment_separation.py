# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S31 — independencia del empaquetado runtime (sandbox temporal).
No toca la instalación diaria ni el perfil real.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class S31EnvironmentSeparationTests(unittest.TestCase):
    def test_gitignore_keeps_private_out(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in ("INFORME_S*.md", "dist/", "data/**", ".idea/"):
            self.assertIn(needle, gi)
        self.assertTrue(".cursor" in gi or "IDE" in gi or ".idea/" in gi)

    def test_packaged_tree_independent_of_repo(self):
        stage_src = ROOT / "dist" / "F7777techMods_runtime"
        if not (
            stage_src.is_dir()
            and (stage_src / "runtime" / "Scripts" / "python.exe").is_file()
        ):
            self.skipTest("No hay dist/F7777techMods_runtime; ejecute --build antes")

        td = Path(tempfile.mkdtemp(prefix="s31_indep_"))
        self.addCleanup(lambda: shutil.rmtree(td, ignore_errors=True))
        dest = td / "pkg"
        shutil.copytree(
            stage_src,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        py = dest / "runtime" / "Scripts" / "python.exe"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(dest)
        env["SGM_DATA_DIR"] = str(td / "data")
        env["SGM_TEST_SANDBOX"] = "1"
        env["F7777TECHMODS_INSTALL_DIR"] = str(dest)
        env.pop("PYTHONHOME", None)
        code = f"""
import sys
from pathlib import Path
repo = Path(r"{ROOT}").resolve()
sep = str(repo) + (__import__("os").sep)
sys.path = [
    p for p in sys.path
    if str(Path(p).resolve()) != str(repo)
    and not str(Path(p).resolve()).startswith(sep)
]
sys.path.insert(0, r"{dest}")
import app
p = Path(app.__file__).resolve()
assert str(p).startswith(r"{dest}"), p
assert not str(p).startswith(str(repo)), p
import customtkinter, PIL
from app.core.inventory import ModEntry
from app.core.mod_structure import analyze_mod_structure
m = ModEntry(
    folder="t", name="t", characters=["OTROS"], character_main="OTROS",
    paks=[], multi=False, on_disk=False, stage_path=str(Path(r"{td}") / "missing"),
)
r = analyze_mod_structure(m, "ue4_paks_mods")
print("indep_ok", r.classification)
"""
        r = subprocess.run(
            [str(py), "-c", code],
            cwd=str(td),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("indep_ok", r.stdout)

    def test_install_requires_explicit_flag(self):
        text = (ROOT / "tools" / "s30_3_install_runtime_daily.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("NO instala", text)
        self.assertIn("autorización explícita", text)


if __name__ == "__main__":
    unittest.main()
