# Entornos F7777techMods

Tres entornos separados. Ninguno debe depender de archivos privados de los otros.

## Desarrollo

- Ruta típica: clon/repositorio local de desarrollo del producto
- Aquí se edita código, se ejecutan tests y scripts de mantenimiento
- Datos de desarrollo: `data/` del repo (gitignored) o `SGM_DATA_DIR`

## Aplicación diaria

- `%LOCALAPPDATA%\Programs\FourSevenTech\F7777techMods\`
- Contiene `runtime/` (Python firmado PSF), `app/`, launchers VBS/CMD, `resources/`, `licenses/`
- **No** importa módulos desde el repositorio de desarrollo
- **No** requiere Python global en el PATH del usuario al usar el launcher
- Actualización solo con autorización explícita vía `tools/s30_3_install_runtime_daily.py --install`

## Datos personales

- `%LOCALAPPDATA%\FourSevenTech\F7777techMods\`
- Perfiles, historial, manifiestos, backups, WORK_LIBRARY
- Nunca se sobrescribe al actualizar el programa

## GitHub (público)

- Solo lo rastreado por Git (código, tests públicos, docs públicas, tools de build, LICENSE)
- Excluido: configuración local de IDE, informes internos, datos runtime, builds, mods y logs

## Construcción reproducible

1. Python 3.12 oficial en la máquina de build (firmado PSF)
2. `python -m unittest discover -s tests`
3. `python tools/s30_3_install_runtime_daily.py --build` → `dist/F7777techMods_runtime/`
4. El artefacto incluye su propio `runtime/`; no se publica el venv del desarrollador
5. El venv **no** se copia entre PCs: siempre se regenera en build

PyInstaller (`tools/s22_1_build_portable.py`) queda como canal portable alternativo; en equipos con WDAC estricto el canal diario es el runtime Python.
