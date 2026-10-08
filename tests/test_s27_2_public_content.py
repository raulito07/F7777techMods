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

S27.2 — el contenido del árbol rastreado no debe documentar herramientas
internas de desarrollo ni rutas personales del autor.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Archivos donde sí pueden aparecer patrones de exclusión / detección.
ALLOWLIST_PREFIXES = (
    ".gitignore",
    "tests/test_s26_3_public_tree.py",
    "tests/test_s27_2_public_content.py",
)

# Frases/productos de asistentes o carpetas internas no publicables en docs/código público.
FORBIDDEN_CONTENT = (
    re.compile(r"(?i)\bChatGPT\b"),
    re.compile(r"(?i)\bOpenAI\b"),
    re.compile(r"(?i)\bGitHub Copilot\b|\bCopilot\b"),
    re.compile(r"(?i)\bClaude\b"),
    re.compile(r"(?i)02_Steam_Gestor_Mods"),
    re.compile(r"(?i)Users[/\\][^/\\\s]+[/\\]Documents"),
    re.compile(r"(?i)pendiente de pasar por\b"),
    re.compile(r"(?i)instrucciones? para el agente\b"),
    re.compile(r"(?i)generado durante una sesión\b"),
)

# "Cursor" solo como producto IDE / carpeta .cursor (no cursor de ratón).
CURSOR_PRODUCT = re.compile(r"(?i)(\.cursor/|\bCursor\b)")

SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc"}


def _git_ls_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=str(ROOT))
    return [p.replace("\\", "/") for p in out.decode("utf-8", "replace").split("\0") if p]


def _allowed(path: str) -> bool:
    for a in ALLOWLIST_PREFIXES:
        if path == a or path.startswith(a):
            return True
    return False


class S272PublicContentTests(unittest.TestCase):
    def test_no_internal_dev_phrases_in_tracked_content(self):
        bad: list[str] = []
        for rel in _git_ls_files():
            if _allowed(rel):
                continue
            p = ROOT / rel
            if p.suffix.lower() in SKIP_SUFFIX:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for rx in FORBIDDEN_CONTENT:
                    if rx.search(line):
                        bad.append(f"{rel}:{i}: {line.strip()[:120]}")
                if CURSOR_PRODUCT.search(line):
                    # Permitir menciones técnicas de cursor de UI
                    if re.search(r"(?i)(cursor=|configure\(.*cursor|mouse|ibeam|text_cursor)", line):
                        continue
                    if ".cursor" in line or re.search(r"\bCursor\b", line):
                        bad.append(f"{rel}:{i}: {line.strip()[:120]}")
        self.assertEqual(bad, [], "Referencias internas en árbol público:\n" + "\n".join(bad[:40]))

    def test_author_only_tools_not_tracked(self):
        tracked = set(_git_ls_files())
        forbidden = [
            "tools/s07_readonly_audit.py",
            "tools/s08_ui_capture.py",
            "tools/s19_execute_fov70_apply.py",
            "tools/s19_prepare_fov70.py",
            "tools/s20_ui_captures.py",
        ]
        still = [p for p in forbidden if p in tracked]
        self.assertEqual(still, [], f"scripts solo-autor aún rastreados: {still}")


if __name__ == "__main__":
    unittest.main()
