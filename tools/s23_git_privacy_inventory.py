# -*- coding: utf-8 -*-
"""
F7777techMods — inventario de candidatos Git + auditoría de privacidad (S23).
Solo lectura. No hace commit ni push. No borra archivos.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "release" / "s23_git_privacy_inventory.json"
# dist/release puede estar gitignored; también escribir bajo data/ si hace falta
OUT_FALLBACK = ROOT / "data" / "_s23_git_privacy_inventory.json"

USERISH = re.compile(
    r"(?i)("
    r"C:\\\\Users\\\\[^\\/\"'\s]+|"
    r"C:/Users/[^\\/\"'\s]+|"
    r"Users\\\\raul_|"
    r"Users/raul_|"
    r"raul_\\\\Documents|"
    r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]|"
    r"password\s*=\s*['\"][^'\"]+['\"]|"
    r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"
    r")"
)

# Archivos de auditoría / build que mencionan patrones a propósito
ALLOW_MENTION = {
    "tools/s20_privacy_audit.py",
    "tools/s21_privacy_git_audit.py",
    "tools/s22_1_build_portable.py",
    "tools/s22_1_probe_portable.py",
    "tools/s23_git_privacy_inventory.py",
    "tests/test_s21_identity.py",
}


def run_git(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    rc, inside = run_git("rev-parse", "--is-inside-work-tree")
    is_repo = rc == 0 and "true" in inside.lower()

    report: dict = {
        "is_repo": is_repo,
        "root": str(ROOT),
        "commits": None,
        "branch": None,
        "candidates": [],
        "findings": [],
        "ignored_samples": [],
    }

    if not is_repo:
        report["error"] = "no_git_repo"
        _write(report)
        print(json.dumps(report, indent=2, ensure_ascii=False)[:2000])
        return 1

    _, branch = run_git("branch", "--show-current")
    report["branch"] = branch.strip()
    rc_log, log = run_git("rev-list", "--count", "HEAD")
    report["commits"] = int(log.strip()) if rc_log == 0 and log.strip().isdigit() else 0

    # Archivos que Git trackearía si se hiciera `git add -A` respetando ignore
    rc_ls, out_ls = run_git("ls-files", "--others", "--cached", "--exclude-standard")
    # Also include already tracked
    rc_tr, out_tr = run_git("ls-files")
    names = set()
    for block in (out_ls, out_tr):
        for ln in block.splitlines():
            ln = ln.strip().replace("\\", "/")
            if ln:
                names.add(ln)
    # Prefer porcelain status for untracked that would be added
    rc_st, out_st = run_git("status", "--porcelain", "--untracked-files=all")
    for ln in out_st.splitlines():
        if len(ln) < 4:
            continue
        path = ln[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path and not path.endswith("/"):
            # status ?? means untracked candidate
            names.add(path)

    # Dry-run add to see what would be staged
    rc_dry, out_dry = run_git("add", "-A", "-n")
    dry_files = []
    for ln in out_dry.splitlines():
        # "add 'path'" or "remove 'path'"
        m = re.search(r"'(.*)'", ln)
        if m:
            dry_files.append(m.group(1).replace("\\", "/"))
    report["dry_run_add_count"] = len(dry_files)
    report["dry_run_add_sample"] = dry_files[:80]
    candidates = sorted(set(dry_files) | {n for n in names if (ROOT / n).is_file()})
    # Restrict to files that exist and are not under ignored dirs by checking check-ignore
    clean = []
    for rel in sorted(set(dry_files)):
        p = ROOT / rel
        if not p.is_file():
            continue
        rc_ig, out_ig = run_git("check-ignore", "-q", rel)
        if rc_ig == 0:
            continue  # ignored
        clean.append(rel)
    report["candidates"] = clean
    report["candidate_count"] = len(clean)

    findings = []
    for rel in clean:
        if rel.replace("\\", "/") in ALLOW_MENTION:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if USERISH.search(text):
            # ignore TU_USUARIO placeholders
            if "TU_USUARIO" in text and "raul_" not in text.lower():
                continue
            findings.append({"file": rel.replace("\\", "/"), "kind": "private_pattern"})

    report["findings"] = findings
    report["findings_count"] = len(findings)

    # Sample ignored important paths
    for probe in (
        "data/games.json",
        "data/managed_manifest.json",
        "dist/release/F7777techMods_v0.1.0_Windows_Portable.zip",
        "INFORME_S19_APPLY.md",
        "legacy/_ff7r_mods_lib.py",
    ):
        rc_ig, _ = run_git("check-ignore", "-q", probe)
        report["ignored_samples"].append({"path": probe, "ignored": rc_ig == 0})

    # LICENSE check
    lic = ROOT / "LICENSE"
    report["license_gpl3"] = lic.is_file() and "GNU GENERAL PUBLIC LICENSE" in lic.read_text(
        encoding="utf-8", errors="ignore"
    )

    _write(report)
    print(
        json.dumps(
            {
                "branch": report["branch"],
                "commits": report["commits"],
                "candidates": report["candidate_count"],
                "findings": report["findings_count"],
                "license_gpl3": report["license_gpl3"],
                "out": str(OUT if OUT.parent.is_dir() else OUT_FALLBACK),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["findings_count"] == 0 else 2


def _write(report: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        OUT_FALLBACK.parent.mkdir(parents=True, exist_ok=True)
        OUT_FALLBACK.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
