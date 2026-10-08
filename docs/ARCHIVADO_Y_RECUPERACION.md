# Archivado y recuperación — F7777techMods

## Archivo propio

El gestor puede generar paquetes propios (ZIP) con metadatos e integridad, independientes del staging de Vortex.

## Biblioteca de trabajo

Extracción controlada a una carpeta de trabajo del gestor para instalar sin depender de mutar Vortex.

## Liberación / independencia

Políticas de plan para dejar de depender del staging: **no** borran staging real sin autorización explícita del usuario.

## Recuperación

- Manifiesto + backups por operación.
- Restauración coherente (archivos + manifiesto previo) cuando el backup lo permite.
- Recuperación idempotente de operaciones `IN_PROGRESS` si la primera recuperación tuvo éxito.
- Backups antiguos sin `pre_manifest.json` pueden no ser restaurables de forma completa.
