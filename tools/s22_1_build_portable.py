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

S22.1 — build portable únicamente (PyInstaller onedir + ZIP).
No genera Setup / Inno. No firma binarios. No altera políticas de Windows.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = DIST / "release"
SPEC = ROOT / "packaging" / "F7777techMods.spec"
ZIP_NAME = "F7777techMods_v0.1.0_Windows_Portable.zip"
PRIVATE_MARKERS = ("Users\\raul_", "Users/raul_", "raul_\\Documents")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def scan_tree_for_private(root: Path) -> list[str]:
    bad: list[str] = []
    if not root.exists():
        return bad
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if any(m in rel for m in PRIVATE_MARKERS):
            bad.append(rel)
            continue
        if p.suffix.lower() in {".exe", ".dll", ".pyd", ".zip", ".pyc", ".png", ".jpg", ".jpeg"}:
            continue
        if p.suffix.lower() not in {".json", ".md", ".txt", ".log", ".html", ".toc"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(m in text for m in PRIVATE_MARKERS):
            bad.append(rel)
    return bad


def zip_dir(src: Path, dest_zip: Path) -> None:
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=str(Path(src.name) / f.relative_to(src)))


def verify_zip_integrity(zpath: Path) -> dict:
    with zipfile.ZipFile(zpath, "r") as zf:
        bad = zf.testzip()
        names = zf.namelist()
    required = [
        "F7777techMods/F7777techMods.exe",
        "F7777techMods/LICENSE",
        "F7777techMods/README_PORTABLE.md",
        "F7777techMods/THIRD_PARTY_NOTICES.md",
    ]
    missing = [r for r in required if r not in names and r.replace("/", "\\") not in names]
    # ZIP always uses /
    missing = [r for r in required if r not in names]
    has_internal = any(n.startswith("F7777techMods/_internal/") for n in names)
    return {
        "testzip_ok": bad is None,
        "first_bad": bad,
        "entries": len(names),
        "missing_required": missing,
        "has_internal": has_internal,
    }


def main() -> int:
    RELEASE.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "product": "F7777techMods",
        "version": "0.1.0",
        "channel": "portable_only",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "setup_generated": False,
        "steps": [],
    }

    app_dist = DIST / "F7777techMods"
    if app_dist.exists():
        shutil.rmtree(app_dist)
    build_dir = ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)])
    report["steps"].append({"pyinstaller": "ok", "out": str(app_dist)})

    exe = app_dist / "F7777techMods.exe"
    if not exe.is_file():
        report["error"] = f"missing {exe}"
        (RELEASE / "build_report_portable.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return 1

    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, app_dist / name)
    readme = ROOT / "docs" / "README_PORTABLE.md"
    if readme.is_file():
        shutil.copy2(readme, app_dist / "README_PORTABLE.md")

    # Release onedir (no tocar Setup existente si hubiera)
    release_dir = RELEASE / "F7777techMods"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    shutil.copytree(app_dist, release_dir)

    portable_zip = RELEASE / ZIP_NAME
    zip_dir(app_dist, portable_zip)
    integrity = verify_zip_integrity(portable_zip)

    private_hits = scan_tree_for_private(app_dist)
    report["private_scan"] = private_hits
    report["zip_integrity"] = integrity

    artifacts = [
        {
            "path": str(portable_zip.relative_to(ROOT)).replace("\\", "/"),
            "bytes": portable_zip.stat().st_size,
            "sha256": sha256_file(portable_zip),
        }
    ]
    report["artifacts"] = artifacts

    sums = RELEASE / "SHA256SUMS.txt"
    sums.write_text(
        f"{artifacts[0]['sha256']}  {ZIP_NAME}\n",
        encoding="utf-8",
    )

    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, RELEASE / name)
    shutil.copy2(readme, RELEASE / "README_PORTABLE.md")

    notes = RELEASE / "RELEASE_NOTES_0.1.0.md"
    notes.write_text(
        """# F7777techMods v0.1.0 (Beta) — portable Windows

**Empresa:** Four Seven Tech  
**Autor:** Raúl Ruano Gil  
**Licencia:** GNU GPL v3 o posterior

## Descarga

Archivo: `F7777techMods_v0.1.0_Windows_Portable.zip`

1. Extraer el ZIP completo.
2. Ejecutar `F7777techMods\\F7777techMods.exe`.
3. Configurar juegos y carpetas.

Ver `README_PORTABLE.md` dentro del ZIP.

## Qué NO incluye esta release

- Instalador Setup (retirado de la distribución pública).
- Firma digital Authenticode.
- Mods, staging Vortex, backups o datos del desarrollador.

## Datos

`%LOCALAPPDATA%\\FourSevenTech\\F7777techMods\\`  
Override: `SGM_DATA_DIR`.

## Aviso Windows

Ejecutable **sin firma**. Algunos equipos pueden bloquearlo (SmartScreen, Control de aplicaciones, políticas corporativas). No se garantiza ejecución en todos los Windows. No desactive protecciones del sistema para forzar el uso.

## Verificación

Comprobar SHA-256 con `SHA256SUMS.txt`.
""",
        encoding="utf-8",
    )

    download = RELEASE / "INSTRUCCIONES_DESCARGA.md"
    download.write_text(
        """# Instrucciones de descarga — F7777techMods 0.1.0 portable

1. Descarga solo `F7777techMods_v0.1.0_Windows_Portable.zip`.
2. Verifica el hash en `SHA256SUMS.txt`.
3. Extrae a una carpeta de tu elección (p. ej. Documentos o Escritorio).
4. Abre `F7777techMods\\F7777techMods.exe`.
5. Lee el aviso sobre ejecutable sin firma en `README_PORTABLE.md`.

No hay instalador Setup en esta release.
""",
        encoding="utf-8",
    )

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["private_hits_count"] = len(private_hits)
    report["ok"] = (
        integrity.get("testzip_ok")
        and integrity.get("has_internal")
        and not integrity.get("missing_required")
        and len(private_hits) == 0
    )
    (RELEASE / "build_report_portable.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "zip": ZIP_NAME,
                "bytes": artifacts[0]["bytes"],
                "sha256": artifacts[0]["sha256"],
                "private_hits": len(private_hits),
                "integrity": integrity,
                "ok": report["ok"],
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
