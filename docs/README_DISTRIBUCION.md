# F7777techMods — distribución Windows 0.1.0

**Empresa:** Four Seven Tech  
**Autor:** Raúl Ruano Gil  
**Licencia:** GNU GPL v3 o posterior (`LICENSE`)

## Canal público (S22.1)

**Solo portable.** No se distribuye instalador Setup.

Ver `README_PORTABLE.md` y el ZIP `F7777techMods_v0.1.0_Windows_Portable.zip`.

## Artefactos

| Archivo | Descripción |
|---------|-------------|
| `F7777techMods_v0.1.0_Windows_Portable.zip` | Onedir PyInstaller + LICENSE + avisos |
| `packaging/*.iss` | Legado local; **no** forma parte de la release pública |

## Datos del usuario

Por defecto (ejecutable empaquetado):

```text
%LOCALAPPDATA%\FourSevenTech\F7777techMods\
```

Override para pruebas:

```bat
set SGM_DATA_DIR=%TEMP%\f7777techmods_test
F7777techMods.exe
```

La desinstalación **conserva** esa carpeta de datos. No se incluye el perfil del desarrollador en la distribución.

## Portable

1. Descomprimir el ZIP.
2. Ejecutar `F7777techMods.exe`.
3. Los datos siguen yendo a LOCALAPPDATA (no junto al exe), salvo `SGM_DATA_DIR`.

## Avisos

- Ver `THIRD_PARTY_NOTICES.md` y `LICENSE`.
- No redistribuir mods de terceros con este paquete.
- Aplicación independiente (no afiliada a Steam / Vortex / Nexus / Square Enix).
