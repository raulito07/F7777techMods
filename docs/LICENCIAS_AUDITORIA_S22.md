# Auditoría de licencias — S22 (F7777techMods 0.1.0)

**Fecha:** 2026-10-08  
**Objetivo:** comprobar compatibilidad con distribución bajo **GNU GPL v3**.

## Veredicto

**FAVORABLE** — no se detectaron dependencias de runtime incompatibles con GPL v3. Se autoriza incorporar `LICENSE` (GPL-3.0) y empaquetar.

## Componentes propios

| Componente | Titular | Licencia propuesta |
|------------|---------|-------------------|
| Código F7777techMods (`app/`, UI, motor S01–S21) | Raúl Ruano Gil / Four Seven Tech | GNU GPL v3 (o posterior) |

No hay iconos, tipografías ni imágenes propias empaquetadas aparte de las que aporta CustomTkinter en su paquete.

## Dependencias de runtime (distribuidas con el ejecutable)

| Paquete | Versión auditada | Licencia | Compatible GPL v3 |
|---------|------------------|----------|-------------------|
| customtkinter | 6.0.0 | MIT / CC0-1.0 (metadatos) | Sí |
| darkdetect | 0.8.0 | BSD-3-Clause | Sí |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Sí |
| Pillow | 12.3.0 | MIT-CMU (HPND-style) | Sí |
| Python (runtime PyInstaller) | 3.12.x | PSF License | Sí (excepción habitual binarios) |

## Dependencias de desarrollo / tools (no requeridas en el exe de usuario)

| Paquete | Licencia | Nota |
|---------|----------|------|
| openpyxl | MIT | Solo `legacy/`; ver `requirements-legacy.txt`; excluido del portable |
| et_xmlfile | MIT | Dependencia de openpyxl |
| PyInstaller | GPLv2 + exception / Apache 2.0 (bootloader) | Herramienta de build; ver avisos PyInstaller |

## Recursos de terceros en UI

- Temas/assets de **CustomTkinter** (se recopilan con `--collect-all customtkinter`).
- Sin logos de Steam, Nexus Mods ni Vortex.
- Sin fuentes propietarias añadidas por Four Seven Tech.

## Incompatibilidades

Ninguna bloqueante detectada en el conjunto a distribuir.

## Acciones

1. Incluir texto oficial GPL v3 en `LICENSE`.
2. Incluir `THIRD_PARTY_NOTICES.md` en artefactos.
3. Actualizar cabeceras PI del código propio (copyright + GPL).
4. No redistribuir `data/` del desarrollador ni mods.
