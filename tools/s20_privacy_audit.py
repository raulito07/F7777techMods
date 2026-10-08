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

S20 — auditoría PRELIMINAR de privacidad (solo lectura; no borra).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "_s20_privacy_audit.json"

USER_PATH = re.compile(
    r"(?i)(C:\\\\Users\\\\[^\\/\"']+|C:/Users/[^\\/\"']+|AppData\\\\Roaming|"
    r"Program Files \(x86\)\\\\Steam|raul_)"
)
SECRETISH = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|bearer|credential|\.pem|\.p12)"
)


def scan() -> dict:
    findings: list[dict] = []
    categories = {
        "absolute_user_paths": [],
        "local_config": [],
        "runtime_data": [],
        "captures": [],
        "possible_secrets": [],
        "third_party_notes": [],
    }

    # data/
    data = ROOT / "data"
    if data.is_dir():
        for p in data.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if p.suffix.lower() in {".json", ".txt", ".md", ".log"}:
                categories["runtime_data"].append(rel)
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")[:200_000]
                except OSError:
                    continue
                if USER_PATH.search(text):
                    categories["absolute_user_paths"].append(rel)
                    findings.append({"file": rel, "kind": "user_path"})
                if SECRETISH.search(text):
                    categories["possible_secrets"].append(rel)

    for cap in ("_s17_captures", "_s18_captures", "_s19_captures", "_s20_captures"):
        d = ROOT / cap
        if d.is_dir():
            for p in d.glob("*.png"):
                categories["captures"].append(str(p.relative_to(ROOT)).replace("\\", "/"))

    # samples of code with hardcoded legacy paths (known, documented)
    paths_py = ROOT / "app" / "core" / "paths.py"
    if paths_py.is_file():
        t = paths_py.read_text(encoding="utf-8", errors="ignore")
        if "Users\\raul_" in t or "Users/raul_" in t:
            categories["absolute_user_paths"].append("app/core/paths.py (LEGACY defaults)")
            findings.append(
                {
                    "file": "app/core/paths.py",
                    "kind": "legacy_default_paths",
                    "note": "Convertir a vacío / discovery; no empaquetar defaults del autor.",
                }
            )

    categories["local_config"] = [
        x
        for x in categories["runtime_data"]
        if x.endswith(("games.json", "ui_settings.json", "loadout.json"))
    ]
    categories["third_party_notes"] = [
        "customtkinter / Pillow: revisar LICENSE al empaquetar",
        "Vortex / Nexus / Steam: no redistribuir; solo rutas locales del usuario",
    ]

    report = {
        "ok": True,
        "deleted_nothing": True,
        "findings_count": len(findings),
        "findings": findings[:200],
        "categories": {k: v[:200] for k, v in categories.items()},
        "recommendations": [
            "Aplicar .gitignore del repo antes de cualquier push.",
            "Usar examples/games.example.json; no commitear data/games.json real.",
            "Sanear LEGACY_* en paths.py para builds públicos.",
            "No incluir capturas con rutas de usuario en el release.",
            "No publicar todavía — auditoría preliminar solamente.",
        ],
    }
    return report


def main() -> int:
    rep = scan()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"findings={rep['findings_count']} -> {OUT}")
    for r in rep["recommendations"]:
        print(" -", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
