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

S26.3 — el árbol rastreado por Git no debe incluir materiales internos
de IDE/agentes ni informes de sesión de desarrollo.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Rutas / nombres que no deben aparecer en `git ls-files`.
# No se bloquea código legítimo solo por palabras sueltas en el contenido.
FORBIDDEN_PREFIXES = (
    ".cursor/",
    ".codex/",
    ".claude/",
    "agent-transcripts/",
    "agent-tools/",
    "legacy/",
)

FORBIDDEN_EXACT = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
}

FORBIDDEN_NAME_RES = (
    re.compile(r"^INFORME_S.*\.md$", re.IGNORECASE),
    re.compile(r"^INFORME_UI_.*\.md$", re.IGNORECASE),
    re.compile(r"^HANDOFF_.*\.md$", re.IGNORECASE),
    re.compile(r"(^|/)_agent(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)prompts(/|$)", re.IGNORECASE),
)

# Documentación / CI públicos permitidos aunque vivan bajo .github/
ALLOWED_PREFIXES = (
    ".github/ISSUE_TEMPLATE/",
    ".github/workflows/",
)


def _git_ls_files() -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=str(ROOT),
        stderr=subprocess.STDOUT,
    )
    if not out:
        return []
    return [p.replace("\\", "/") for p in out.decode("utf-8", "replace").split("\0") if p]


def _is_forbidden(path: str) -> bool:
    for allow in ALLOWED_PREFIXES:
        if path.startswith(allow):
            return False
    if path in FORBIDDEN_EXACT:
        return True
    for pref in FORBIDDEN_PREFIXES:
        if path.startswith(pref):
            return True
    name = path.rsplit("/", 1)[-1]
    for rx in FORBIDDEN_NAME_RES:
        if rx.search(path) or rx.search(name):
            return True
    return False


class S263PublicTreeTests(unittest.TestCase):
    def test_tracked_tree_has_no_internal_dev_materials(self):
        files = _git_ls_files()
        self.assertGreater(len(files), 50, "árbol git inesperadamente vacío")
        bad = sorted(p for p in files if _is_forbidden(p))
        self.assertEqual(
            bad,
            [],
            "Material interno rastreado (retirar con git rm --cached + .gitignore):\n"
            + "\n".join(bad),
        )

    def test_github_issue_templates_still_allowed(self):
        files = set(_git_ls_files())
        self.assertTrue(
            any(p.startswith(".github/ISSUE_TEMPLATE/") for p in files),
            "faltan plantillas públicas .github/ISSUE_TEMPLATE",
        )

    def test_local_cursor_rule_file_still_on_disk(self):
        # Conservar entorno local; no debe estar en git ls-files.
        rule = ROOT / ".cursor" / "rules" / "four-seven-tech.mdc"
        self.assertTrue(rule.is_file(), "regla Cursor local ausente en disco")
        tracked = set(_git_ls_files())
        self.assertNotIn(".cursor/rules/four-seven-tech.mdc", tracked)


if __name__ == "__main__":
    unittest.main()
