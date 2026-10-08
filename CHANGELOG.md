# Changelog — F7777techMods

Formato orientativo [Keep a Changelog](https://keepachangelog.com/). Versión de producto: `app/version.py`.

## [0.1.0] — 2026-10

### Añadido
- Gestor multijuego (FF7 Remake, FF7 Rebirth, Stellar Blade) con perfiles aislados.
- Plan / simulación / Apply con manifiesto, backups y recuperación.
- Conflictos por archivo, variantes, modos COPY / HARDLINK / AUTO.
- Archivado ZIP propio y ciclo WORK_LIBRARY.
- Detección de estructura de mods (clasificación, grupos IoStore, seguridad de rutas/ZIP).
- Distribución diaria con runtime Python firmado (PSF) + launcher VBS (canal recomendado bajo WDAC estricto).
- Canal portable PyInstaller onedir (ZIP) como alternativa de publicación.

### Seguridad
- Apply bloqueado sin destino verificado, con deployment Vortex presente, o con estructura incompleta/ambigua.
- No se ejecuta Deploy/Purge de Vortex automáticamente.
- Datos de usuario en `%LOCALAPPDATA%\FourSevenTech\F7777techMods\`.

### Notas
- Beta pública: validación visual in-game pendiente en varios títulos.
- El bootloader PyInstaller sin firma puede ser bloqueado por WDAC; usar el canal runtime Python en esos equipos.
