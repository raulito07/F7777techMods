@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo === F7777techMods — SOLO PRUEBA S29 (sandbox sintetico) ===
echo NO es el acceso diario. Uso diario: acceso directo Escritorio F7777techMods.
echo No usa Steam, Vortex ni su perfil personal.
echo Destino Apply: %%TEMP%%\F7777techMods_S29_UI_TEST\mods_dest_*
echo.
python tools\s29_ui_test_mode.py --reset --ui
if errorlevel 1 (
  echo.
  echo Error al arrancar. Compruebe Python y dependencias.
  pause
  exit /b 1
)
endlocal
