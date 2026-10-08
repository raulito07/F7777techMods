# F7777techMods 0.1.0 — versión portable (Windows)

**Empresa:** Four Seven Tech — https://fourseven.es/  
**Autor:** Raúl Ruano Gil  
**Licencia:** GNU GPL v3 (o posterior) — ver `LICENSE`  
**Canal:** primera distribución pública = **solo portable** (sin instalador Setup).  
**Tag previsto:** `v0.1.0-beta` (pre-release).

## Cómo usar

1. Descarga `F7777techMods_v0.1.0_Windows_Portable.zip`.
2. Extrae la carpeta completa (debe quedar `F7777techMods\F7777techMods.exe` junto a `_internal\`).
3. Ejecuta `F7777techMods.exe`.
4. Configura tus juegos y carpetas en la aplicación.

No necesitas Python ni un instalador externo.

## Datos persistentes

Por defecto:

```text
%LOCALAPPDATA%\FourSevenTech\F7777techMods\
```

Opción avanzada (pruebas / perfiles aislados):

```bat
set SGM_DATA_DIR=C:\ruta\a\datos
F7777techMods.exe
```

Los datos **no** se escriben dentro del ZIP ni dentro de `_internal`.

## Advertencias (beta)

- Primera **beta** pública.
- Ejecutable **sin firma digital** (Authenticode).
- Algunas políticas de seguridad de Windows (SmartScreen, Code Integrity, WDAC, AppLocker, etc.) pueden **impedir** la ejecución.
- Compatibilidad con juegos **todavía en validación**.
- **No** se garantiza compatibilidad universal.

Four Seven Tech **no** recomienda desactivar protecciones del sistema para forzar el uso.  
Si Windows bloquea el archivo, anota el mensaje exacto; la decisión de política es del administrador del PC.

## Contenido del paquete

- `F7777techMods.exe` + `_internal\` (runtime embebido)
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `README_PORTABLE.md` (este archivo)

No incluye mods, staging Vortex, backups ni configuraciones del desarrollador.

## Limitaciones conocidas

- Primera beta 0.1.0: leer `docs/PRECAUCIONES.md` antes de Apply real.
- Vortex / Steam no se modifican automáticamente.
- Aplicación independiente (no afiliada a Square Enix, Steam, Nexus Mods ni Vortex).
