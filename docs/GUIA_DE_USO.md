# Guía de uso — F7777techMods

## Flujo seguro

1. **Actualizar** — lee staging y destino.
2. **Biblioteca** — activa/desactiva mods en el plan; revisa formato/clasificación.
3. **Conflictos** — solapes, prioridades y variantes.
4. **Simular** — no escribe; lista ADD/UPDATE/REMOVE y método.
5. **Aplicar** — solo tras confirmación y validaciones del motor.

## Juegos

| Juego | Adaptador típico |
|-------|------------------|
| FF7 Remake | `ue4_paks_mods` |
| FF7 Rebirth | `ue5_iostore_mods` |
| Stellar Blade | `ue5_iostore_mods` |

Detalle de estado: [KNOWN_ISSUES.md](../KNOWN_ISSUES.md) y [COMPATIBILIDAD.md](COMPATIBILIDAD.md).

## Vortex

Fuente habitual de descargas. Este gestor **lee** el staging; no ejecuta Deploy/Purge. Con `vortex.deployment.json` en destino, Apply queda bloqueado hasta Purge en Vortex.

## Modos de instalación

COPY / HARDLINK / AUTO — ver [MODOS_INSTALACION.md](MODOS_INSTALACION.md).

## Archivado y WORK_LIBRARY

ZIP propio y biblioteca de trabajo — ver [ARCHIVADO_Y_RECUPERACION.md](ARCHIVADO_Y_RECUPERACION.md).

## Backups y rollback

Cada Apply genera historial/backup en los datos del juego. Rollback de **programa** (instalación diaria): `python tools/s30_3_install_runtime_daily.py --rollback`.

## Paneles

Resumen · Biblioteca · Conflictos · Instalados · Almacenamiento · Historial · Juegos y ajustes · Acerca de.

## Estados de mod (UI)

| Flag | Significado |
|------|-------------|
| ACTIVO_EN_PLAN | Marcado para futura aplicación |
| INSTALADO_REAL | Detectado en destino / manifiesto |
| ARCHIVADO_VERIFICADO | ZIP propio conocido |
| DISPONIBLE_EN_WORK | Copia en WORK_LIBRARY |
| STAGING_VORTEX | Presente en staging (lectura) |
| CONFLICTO / VARIANTE_PENDIENTE | Bloqueos de plan |
| ESTRUCTURA_* | Clasificación/bloqueo de estructura |

«Activo» en el plan **no** implica Enabled en Vortex ni instalación real.
