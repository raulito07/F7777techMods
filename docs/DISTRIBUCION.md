# Distribución Windows — F7777techMods 0.1.0

**Empresa:** Four Seven Tech · **Licencia:** GNU GPL v3 (`LICENSE`)

Hay **dos canales**. No son intercambiables en todos los PCs.

## 1. Canal diario recomendado (runtime Python)

Arquitectura alineada con otras aplicaciones Four Seven Tech:

- Host: `runtime\Scripts\pythonw.exe` (Authenticode Python Software Foundation)
- App: paquete `app/` + `run_f7777techmods.py`
- Launcher: `Abrir F7777techMods.vbs` (sin consola)
- Instalación estable: `%LOCALAPPDATA%\Programs\FourSevenTech\F7777techMods\`
- Datos: `%LOCALAPPDATA%\FourSevenTech\F7777techMods\`

Build / actualización: [DESARROLLO.md](DESARROLLO.md) §§ C–E y [ENTORNOS.md](ENTORNOS.md).

En equipos con WDAC que exigen *Enterprise signing level*, este canal evita el bootloader PyInstaller sin firma.

## 2. Canal portable GitHub (PyInstaller)

- Artefacto: `F7777techMods_v0.1.0_Windows_Portable.zip` (onedir)
- Entrada: `F7777techMods.exe` (**sin firma** en 0.1.0)
- Build: `python tools/s22_1_build_portable.py`
- **No** se publica instalador Setup/Inno

Puede ser bloqueado por políticas de Code Integrity. Si ocurre, usar el canal runtime Python.

## Datos

Ambos canales usan por defecto `%LOCALAPPDATA%\FourSevenTech\F7777techMods\`.  
Override de pruebas: `SGM_DATA_DIR`. La actualización del programa **no** borra esa carpeta.

## Avisos

- Ver `THIRD_PARTY_NOTICES.md` y `LICENSE`.
- No redistribuir mods de terceros con el paquete.
- Aplicación independiente (no afiliada a Steam / Vortex / Nexus / Square Enix).
