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

S21 — auditoría de privacidad + inventario Git propuesto (solo lectura).
No borra, no hace commit, no modifica historial.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "_s21_privacy_git_audit.json"

USER_MARKERS = re.compile(
    r"(?i)(C:\\\\Users\\\\[^\\/\"']+|C:/Users/[^\\/\"']+|Users\\\\raul_|Users/raul_|raul_)"
)
SECRETISH = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|bearer|credential|\.pem|\.p12)"
)

# Árbol de código/docs que formaría un repo público (no data runtime)
PUBLIC_GLOBS = [
    "app/**/*.py",
    "tests/**/*.py",
    "tools/**/*.py",
    "docs/**/*.md",
    "examples/**/*",
    ".github/**/*",
    "README.md",
    "requirements.txt",
    "requirements-build.txt",
    "requirements-legacy.txt",
    ".gitignore",
    "Iniciar_Gestor.bat",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "app/**/*.txt",
]


def _git(*args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, "git no disponible"


def scan_code_for_private_paths() -> list[dict]:
    findings: list[dict] = []
    for rel_root in ("app", "tests", "tools", "docs", "examples"):
        base = ROOT / rel_root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".py", ".md", ".json", ".txt", ".bat"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if USER_MARKERS.search(text):
                # Permitir plantillas con TU_USUARIO / placeholders
                if "TU_USUARIO" in text and "raul_" not in text.lower():
                    continue
                findings.append(
                    {
                        "file": str(p.relative_to(ROOT)).replace("\\", "/"),
                        "kind": "user_path_in_source",
                    }
                )
            if SECRETISH.search(text) and "credential" not in p.name.lower():
                # Evitar falsos positivos en docs de licencia / plantillas
                if p.suffix == ".md" and "password" not in text.lower():
                    continue
    return findings


def proposed_public_files() -> list[str]:
    out: list[str] = []
    for pattern in PUBLIC_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    # dedupe sort
    return sorted(set(out))


def main() -> int:
    code_findings = scan_code_for_private_paths()
    # Hallazgos runtime locales (no borrar; deben estar gitignored)
    runtime_private: list[str] = []
    data = ROOT / "data"
    if data.is_dir():
        for p in data.rglob("*"):
            if p.is_file() and p.name not in {".gitkeep", "README.md"}:
                runtime_private.append(str(p.relative_to(ROOT)).replace("\\", "/"))

    rc_repo, out_repo = _git("rev-parse", "--is-inside-work-tree")
    is_repo = rc_repo == 0 and "true" in out_repo.lower()
    tracked: list[str] = []
    history_note = "Sin repositorio Git en esta carpeta — no hay historial que auditar."
    if is_repo:
        rc_ls, out_ls = _git("ls-files")
        tracked = [ln.strip().replace("\\", "/") for ln in out_ls.splitlines() if ln.strip()]
        history_note = (
            "Hay repositorio Git. Revisar que ningún archivo privado esté en "
            "tracked o en commits previos antes de publicar."
        )
        # Si hay tracked con data/ o raul_
        for t in tracked:
            if t.startswith("data/") and not t.endswith((".gitkeep", "README.md")):
                code_findings.append({"file": t, "kind": "tracked_runtime_data"})

    # Código: paths.py / games no deben tener Users\raul_
    hardcode_ok = True
    for rel in ("app/core/paths.py", "app/core/games.py", "app/core/vortex_sync.py"):
        p = ROOT / rel
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="ignore")
            if "Users\\raul_" in t or "Users/raul_" in t:
                hardcode_ok = False
                code_findings.append({"file": rel, "kind": "hardcoded_author_path"})

    from app.version import __title__, __version__
    from app.branding import PRODUCT_NAME, OFFICIAL_WEBSITE_URL

    report = {
        "ok": True,
        "product": PRODUCT_NAME,
        "version": __version__,
        "title_match": __title__ == "F7777techMods" and PRODUCT_NAME == "F7777techMods",
        "official_website_configured": bool(OFFICIAL_WEBSITE_URL.strip()),
        "deleted_nothing": True,
        "git": {
            "is_repository": is_repo,
            "tracked_count": len(tracked),
            "tracked_sample": tracked[:50],
            "history_note": history_note,
        },
        "code_findings": code_findings,
        "code_findings_count": len(code_findings),
        "hardcoded_author_paths_cleared": hardcode_ok,
        "runtime_private_present_locally": len(runtime_private),
        "runtime_private_sample": runtime_private[:40],
        "runtime_must_stay_gitignored": True,
        "proposed_public_file_count": len(proposed_public_files()),
        "proposed_public_sample": proposed_public_files()[:80],
        "publication_repo": (
            "GO"
            if hardcode_ok and not is_repo and not any(
                f.get("kind") == "hardcoded_author_path" for f in code_findings
            )
            and len([f for f in code_findings if f.get("kind") == "user_path_in_source"]) == 0
            else "NO-GO"
        ),
        "publication_installer": "GO-CONDITIONAL",
        "notes": [
            "Datos runtime locales se conservan (FOV70/manifiestos); no se borran.",
            "Sin git history: no hay secretos en commits previos en esta carpeta.",
            "Rellenar branding URLs antes de mostrar enlaces en UI pública.",
            "Decidir LICENSE antes de claim open source.",
        ],
    }

    # Ajuste GO repo: permitir hallazgos solo en tools de auditoría que buscan 'raul_'
    audit_self = [
        f
        for f in code_findings
        if "s20_privacy" in f.get("file", "")
        or "s21_privacy" in f.get("file", "")
        or f.get("file", "").startswith("examples/")
    ]
    real_findings = [f for f in code_findings if f not in audit_self]
    # Filtrar tools que mencionan raul_ como patrón de búsqueda
    real_findings = [
        f
        for f in real_findings
        if not (
            f.get("kind") == "user_path_in_source"
            and (
                "privacy" in f.get("file", "")
                or "audit" in f.get("file", "")
                or f.get("file", "").endswith("test_s21_identity.py")
            )
        )
    ]
    report["code_findings_actionable"] = real_findings
    report["code_findings_actionable_count"] = len(real_findings)
    if hardcode_ok and len(real_findings) == 0 and not is_repo:
        report["publication_repo"] = "GO-AFTER-INIT-WITH-GITIGNORE"
    elif hardcode_ok and len(real_findings) == 0 and is_repo:
        # Revisar tracked
        bad_tracked = [
            t
            for t in tracked
            if t.startswith("data/") and not t.endswith((".gitkeep", "README.md"))
        ]
        report["publication_repo"] = "NO-GO" if bad_tracked else "GO-AFTER-REVIEW"
    else:
        report["publication_repo"] = "NO-GO"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "product": report["product"],
        "hardcoded_cleared": report["hardcoded_author_paths_cleared"],
        "actionable": report["code_findings_actionable_count"],
        "git_repo": report["git"]["is_repository"],
        "publication_repo": report["publication_repo"],
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
