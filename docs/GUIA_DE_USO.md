# Guía de uso — F7777techMods

## Flujo seguro recomendado

1. **Actualizar** — lee staging y estado en destino.
2. **Biblioteca** — activa/desactiva mods en el plan del gestor.
3. **Conflictos** — revisa solapes y prioridades.
4. **Simular** — no escribe; muestra ADD/UPDATE/REMOVE y método COPY/HARDLINK.
5. **Aplicar** — escribe solo tras confirmación y validaciones del motor.

## Paneles

| Panel | Función |
|-------|---------|
| Resumen | Estado del juego activo e identidad del producto |
| Biblioteca | Inventario, filtros, plan |
| Conflictos | Solapes y resoluciones |
| Instalados | Qué hay en destino |
| Almacenamiento | Archivo / biblioteca de trabajo |
| Historial | Operaciones y backups |
| Juegos y ajustes | Perfiles, modo instalación, zoom |
| Acerca de | Identidad, licencia, enlaces oficiales |

## Estados de mod (UI)

Ciclo resumido: DESCARGADO → PREPARADO → SELECCIONADO (plan) → INSTALADO (destino).

En la biblioteca (S27) además se muestran **dimensiones independientes** que pueden coexistir:

| Flag | Significado |
|------|-------------|
| ACTIVO_EN_PLAN | Marcado para futura aplicación |
| INSTALADO_REAL | Detectado en destino / manifiesto |
| ARCHIVADO_VERIFICADO | ZIP propio conocido |
| DISPONIBLE_EN_WORK | Copia en WORK_LIBRARY |
| STAGING_VORTEX | Presente en staging (lectura) |
| CONFLICTO / VARIANTE_PENDIENTE | Bloqueos de plan |

«Activo» en el plan del gestor **no** implica Enabled en Vortex ni instalación real.
