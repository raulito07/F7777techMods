# -*- coding: utf-8 -*-
"""
F7777techMods — Gestor multijuego de mods.
Versión: 0.1.0
Empresa: Four Seven Tech
Autor: Raúl Ruano Gil

Copyright (c) 2026 Raúl Ruano Gil.
Desarrollado bajo Four Seven Tech.

Este programa es software libre bajo GNU GPL v3 o posterior.

S30.3 — distribución diaria con runtime Python firmado (modelo Folio/Gabinete).
No usa PyInstaller como proceso de entrada. No modifica WDAC ni Folio/Gabinete.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "F7777techMods"
STAGE = ROOT / "dist" / "F7777techMods_runtime"


def install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Programs" / "FourSevenTech" / PRODUCT


def data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "FourSevenTech" / PRODUCT


def desktop_lnk() -> Path:
    return Path.home() / "Desktop" / f"{PRODUCT}.lnk"


def base_python() -> Path:
    # Python oficial del usuario (firmado PSF), solo como fuente de venv
    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe"
    if cand.is_file():
        return cand
    return Path(sys.executable)


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def authenticode_status(path: Path) -> str:
    ps = (
        f"(Get-AuthenticodeSignature -LiteralPath '{path}').Status.ToString()"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps], text=True
    ).strip()
    return out


def wdac_probe(pythonw: Path) -> bool:
    """Ejecuta sonda mínima con el pythonw del runtime. False = política bloquea."""
    probe = Path(os.environ.get("TEMP", ".")) / "sgm_s303_wdac_probe.py"
    marker = Path(os.environ.get("TEMP", ".")) / "sgm_s303_wdac_probe_ok.txt"
    if marker.exists():
        marker.unlink()
    probe.write_text(
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    try:
        r = subprocess.run(
            [str(pythonw), str(probe)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as e:
        print(f"WDAC_PROBE_BLOCK: {e}")
        return False
    ok = marker.is_file() and r.returncode == 0
    print(f"WDAC_PROBE ok={ok} rc={r.returncode} sig={authenticode_status(pythonw)}")
    return ok


def build_stage() -> Path:
    if STAGE.exists():
        shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    runtime = STAGE / "runtime"
    py = base_python()
    print(f"Base Python: {py}")
    run([str(py), "-m", "venv", "--copies", str(runtime)])
    pyw = runtime / "Scripts" / "pythonw.exe"
    py_rt = runtime / "Scripts" / "python.exe"
    if not pyw.is_file():
        raise SystemExit("venv sin pythonw.exe")
    sig = authenticode_status(pyw)
    print(f"runtime pythonw Authenticode={sig}")
    if sig != "Valid":
        raise SystemExit(
            f"ABORT: pythonw del runtime no tiene firma Valid ({sig}). "
            "No se despliega un host no autorizado."
        )
    if not wdac_probe(pyw):
        raise SystemExit(
            "ABORT: WDAC/App Control bloqueó la sonda del runtime firmado. "
            "No se despliega. Se requiere autorización administrativa."
        )
    run(
        [
            str(py_rt),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "customtkinter>=6.0.0",
            "Pillow>=10.0.0",
        ]
    )
    # App package + entry
    shutil.copytree(ROOT / "app", STAGE / "app")
    shutil.copy2(ROOT / "run_f7777techmods.py", STAGE / "run_f7777techmods.py")
    lic = STAGE / "licenses"
    lic.mkdir(exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, lic / name)
    # Runtime LICENSE
    for name in ("LICENSE.txt", "LICENSE"):
        src = runtime / name
        if src.is_file():
            shutil.copy2(src, lic / f"PYTHON_{name}")
            break
    res = STAGE / "resources"
    res.mkdir(exist_ok=True)
    assets = ROOT / "packaging" / "assets"
    for name in ("f7777techmods.ico", "f7777techmods.png"):
        if (assets / name).is_file():
            shutil.copy2(assets / name, res / name)
            shutil.copy2(assets / name, STAGE / name)
    # Launchers (sin EXE propio sin firmar)
    (STAGE / "Abrir F7777techMods.cmd").write_text(
        "\r\n".join(
            [
                "@echo off",
                'cd /d "%~dp0"',
                "REM Neutralizar sandbox/test heredado",
                "set SGM_TEST_SANDBOX=",
                "set SGM_DATA_DIR=",
                "set SGM_USE_APPDATA=1",
                "set PYTHONPATH=%~dp0",
                "set F7777TECHMODS_INSTALL_DIR=%~dp0",
                'if not exist "%~dp0runtime\\Scripts\\pythonw.exe" (',
                "  echo Falta runtime\\Scripts\\pythonw.exe",
                "  pause",
                "  exit /b 1",
                ")",
                'start "" /D "%~dp0" "%~dp0runtime\\Scripts\\pythonw.exe" "%~dp0run_f7777techmods.py"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (STAGE / "Abrir F7777techMods.vbs").write_text(
        "\r\n".join(
            [
                'Set sh = CreateObject("WScript.Shell")',
                'Set fso = CreateObject("Scripting.FileSystemObject")',
                "d = fso.GetParentFolderName(WScript.ScriptFullName)",
                "sh.CurrentDirectory = d",
                "On Error Resume Next",
                'sh.Environment("Process").Remove("SGM_TEST_SANDBOX")',
                'sh.Environment("Process").Remove("SGM_DATA_DIR")',
                "On Error Goto 0",
                'sh.Environment("Process")("SGM_USE_APPDATA") = "1"',
                'sh.Environment("Process")("PYTHONPATH") = d',
                'sh.Environment("Process")("F7777TECHMODS_INSTALL_DIR") = d',
                'pyw = d & "\\runtime\\Scripts\\pythonw.exe"',
                'script = d & "\\run_f7777techmods.py"',
                'sh.Run """" & pyw & """ """ & script & """", 0, False',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (STAGE / "ACTUALIZAR.txt").write_text(
        "Actualización manual (runtime Python) — requiere autorización explícita\r\n"
        "1) Cerrar F7777techMods\r\n"
        "2) En el repo: python -m unittest discover -s tests\r\n"
        "3) python tools\\s30_3_install_runtime_daily.py --build\r\n"
        "4) python tools\\s30_3_install_runtime_daily.py --install --shortcut --smoke\r\n"
        "   (--install NUNCA se ejecuta solo ni en cada cambio de código)\r\n"
        "5) Mismo acceso directo del Escritorio\r\n"
        "Rollback: carpeta F7777techMods_prev junto a la instalación\r\n"
        f"Datos usuario (intactos): {data_dir()}\r\n"
        "Ver también docs/ENTORNOS.md\r\n",
        encoding="utf-8",
    )
    meta = {
        "product": PRODUCT,
        "version": "0.1.0",
        "distribution": "runtime_python_psf_signed",
        "entry": "runtime/Scripts/pythonw.exe + run_f7777techmods.py",
        "pythonw_authenticode": sig,
        "s29_default": False,
        "data_dir": str(data_dir()),
    }
    (STAGE / "install_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return STAGE


def verify_stage(stage: Path) -> None:
    """Comprueba dependencias, licencias y recursos antes de activar."""
    required = [
        stage / "runtime" / "Scripts" / "pythonw.exe",
        stage / "runtime" / "Scripts" / "python.exe",
        stage / "app" / "__init__.py",
        stage / "run_f7777techmods.py",
        stage / "Abrir F7777techMods.vbs",
        stage / "licenses" / "LICENSE",
        stage / "f7777techmods.ico",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("ABORT verify_stage, faltan:\n" + "\n".join(missing))
    py = stage / "runtime" / "Scripts" / "python.exe"
    r = subprocess.run(
        [str(py), "-c", "import customtkinter, PIL; print('deps_ok')"],
        capture_output=True,
        text=True,
        cwd=str(stage),
        env={**os.environ, "PYTHONPATH": str(stage)},
        check=False,
    )
    if r.returncode != 0 or "deps_ok" not in (r.stdout or ""):
        raise SystemExit(f"ABORT: dependencias incompletas: {r.stderr[:300]}")
    # El stage no debe referenciar la ruta del repo de desarrollo
    for rel in ("Abrir F7777techMods.cmd", "Abrir F7777techMods.vbs"):
        text = (stage / rel).read_text(encoding="utf-8", errors="ignore")
        # Evitar rutas de desarrollo del autor embebidas en launchers
        lowered = text.lower()
        if "documents\\" in lowered and "juegos" in lowered:
            raise SystemExit(f"ABORT: launcher referencia ruta de desarrollo: {rel}")
        if "f7777techmods_install_dir" not in lowered and "pythonpath" not in lowered:
            raise SystemExit(f"ABORT: launcher incompleto: {rel}")


def app_is_running() -> bool:
    ps = (
        "@(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" |"
        "Where-Object { $_.CommandLine -match 'F7777techMods|run_f7777techmods' }).Count"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps], text=True
        ).strip()
        return int(out or "0") > 0
    except Exception:
        return False


def deploy(stage: Path) -> Path:
    """Activa instalación diaria. Requiere --install explícito. No toca datos personales."""
    verify_stage(stage)
    dest = install_dir()
    if app_is_running():
        raise SystemExit(
            "ABORT: F7777techMods está en ejecución. Ciérrelo antes de --install."
        )
    # Preparación en carpeta temporal junto al destino (no en el repo)
    staging = dest.parent / (dest.name + "_staging")
    prev = dest.parent / (dest.name + "_prev")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(stage, staging)
    pyw = staging / "runtime" / "Scripts" / "pythonw.exe"
    if authenticode_status(pyw) != "Valid" or not wdac_probe(pyw):
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit("ABORT: firma/WDAC falló en staging. Instalación intacta.")
    # Backup instalación anterior + activación
    if dest.exists():
        if prev.exists():
            shutil.rmtree(prev, ignore_errors=True)
        dest.rename(prev)
    try:
        staging.rename(dest)
    except Exception:
        # Rollback inmediato si no se puede activar
        if prev.exists() and not dest.exists():
            prev.rename(dest)
        raise
    print(f"Instalado: {dest}")
    print(f"Backup prev: {prev}")
    print(f"Datos personales NO tocados: {data_dir()}")
    return dest


def rollback_from_prev() -> None:
    dest = install_dir()
    prev = dest.parent / (dest.name + "_prev")
    if not prev.exists():
        raise SystemExit("No hay F7777techMods_prev para rollback")
    if dest.exists():
        failed = dest.parent / (dest.name + "_failed")
        if failed.exists():
            shutil.rmtree(failed, ignore_errors=True)
        dest.rename(failed)
    prev.rename(dest)
    print(f"Rollback OK → {dest}")


def create_shortcut(dest: Path) -> None:
    vbs = dest / "Abrir F7777techMods.vbs"
    ico = dest / "f7777techmods.ico"
    lnk = desktop_lnk()
    work = str(dest)
    target = str(vbs)
    icon = str(ico if ico.is_file() else vbs)
    ps = f"""
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut('{str(lnk).replace("'", "''")}')
$S.TargetPath = '{target.replace("'", "''")}'
$S.WorkingDirectory = '{work.replace("'", "''")}'
$S.IconLocation = '{icon.replace("'", "''")},0'
$S.Description = 'F7777techMods — Four Seven Tech (runtime Python)'
$S.WindowStyle = 1
$S.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"Acceso directo: {lnk} -> {target}")


def smoke_launch(dest: Path) -> None:
    vbs = dest / "Abrir F7777techMods.vbs"
    # Arranque real vía wscript (como acceso directo)
    proc = subprocess.Popen(
        ["wscript.exe", "//B", str(vbs)],
        cwd=str(dest),
    )
    time.sleep(5)
    # Buscar proceso pythonw con nuestro título vía Get-Process es frágil; marker UI
    # Comprobar que no hay denegación CI reciente del pythonw instalado
    ps = (
        "$e=Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-CodeIntegrity/Operational';"
        "Id=3077;StartTime=(Get-Date).AddMinutes(-10)} -MaxEvents 30 -EA SilentlyContinue |"
        "Where-Object { $_.Message -match 'FourSevenTech\\\\F7777techMods\\\\runtime' };"
        "if($e){'CI_DENY='+$e.Count}else{'CI_DENY=0'}"
    )
    ci = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps], text=True
    ).strip()
    print(ci)
    if ci.startswith("CI_DENY=") and ci != "CI_DENY=0":
        raise SystemExit("ABORT post-deploy: Code Integrity denegó el runtime instalado.")
    # Cerrar procesos pythonw hijos de esta app (best-effort)
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" |"
            "Where-Object { $_.CommandLine -match 'F7777techMods' } |"
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }",
        ],
        check=False,
    )
    print("Smoke launch: sin denegación CI del runtime instalado")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Build/instalación diaria F7777techMods (runtime Python). "
        "--install requiere autorización explícita; no forma parte de --all."
    )
    ap.add_argument("--build", action="store_true", help="Genera dist/F7777techMods_runtime")
    ap.add_argument(
        "--install",
        action="store_true",
        help="ACTUALIZA la instalación diaria (explícito; pide app cerrada)",
    )
    ap.add_argument("--shortcut", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--rollback", action="store_true", help="Restaura *_prev")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Solo --build + verificación de stage (NO instala)",
    )
    args = ap.parse_args()
    if args.rollback:
        rollback_from_prev()
        return 0
    if args.all:
        args.build = True
    if not any([args.build, args.install, args.shortcut, args.smoke]):
        ap.print_help()
        print("\nNota: use --build para empaquetar; --install solo con autorización.")
        return 2
    stage = STAGE
    if args.build:
        stage = build_stage()
        verify_stage(stage)
        print(f"Stage listo (sin instalar): {stage}")
    dest = install_dir()
    if args.install:
        if not stage.exists():
            raise SystemExit("ABORT: no hay stage; ejecute --build antes de --install")
        verify_stage(stage)
        dest = deploy(stage)
        try:
            # Smoke obligatorio tras install; rollback si falla
            smoke_launch(dest)
        except SystemExit:
            print("Smoke/CI falló → rollback automático")
            rollback_from_prev()
            raise
    if args.shortcut:
        if not (dest / "Abrir F7777techMods.vbs").is_file():
            raise SystemExit("ABORT: no hay instalación diaria para el acceso directo")
        create_shortcut(dest)
    elif args.smoke and not args.install:
        smoke_launch(dest)
    gj = data_dir() / "games.json"
    if gj.is_file():
        games = json.loads(gj.read_text(encoding="utf-8")).get("games") or {}
        print("Perfiles (solo lectura):", ", ".join(games.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
