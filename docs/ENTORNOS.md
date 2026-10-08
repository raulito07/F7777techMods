# Entornos F7777techMods

Tres entornos separados. Ninguno debe depender de archivos privados de los otros.

## Desarrollo

- Repositorio local del producto (código, tests, tools).
- Arranque: `python run_f7777techmods.py` — ver [DESARROLLO.md](DESARROLLO.md).

## Aplicación diaria

- `%LOCALAPPDATA%\Programs\FourSevenTech\F7777techMods\`
- Runtime Python firmado + `app/` + launcher VBS.
- No importa módulos del repositorio de desarrollo.
- Actualización solo con `--install` explícito.

## Datos personales

- `%LOCALAPPDATA%\FourSevenTech\F7777techMods\`
- Perfiles, historial, manifiestos, backups, WORK_LIBRARY.
- Nunca se sobrescribe al actualizar el programa.

## GitHub

- Solo lo rastreado por Git.
- Excluido: configuración local de IDE, informes internos, datos runtime, builds, mods y logs.

Distribución: [DISTRIBUCION.md](DISTRIBUCION.md).
