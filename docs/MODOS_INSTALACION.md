# Modos de instalación — COPY / HARDLINK / AUTO

Configurables por juego en **Juegos y ajustes**.

## COPY

- Copia independiente del origen (staging / biblioteca de trabajo).
- Más seguro si el origen cambia o se borra.
- Usa más espacio en disco.
- **Recomendado** para primeros usos y mods críticos.

## HARDLINK

- Enlace duro al mismo contenido en el mismo volumen NTFS.
- Ahorra espacio; el archivo en destino y origen comparten datos.
- Si el origen se modifica/borra, el destino puede verse afectado.
- Backups del gestor se hacen siempre como copia independiente (anti-hardlink).
- No elegible entre volúmenes distintos.

## AUTO

- El motor elige COPY o HARDLINK según elegibilidad (mismo volumen, permisos, política).
- Ante duda, prioriza integridad (COPY).

## Prioridad

La integridad del staging y del destino mandan sobre el ahorro de espacio.
