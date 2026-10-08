# data/ — runtime local (no publicar)

Esta carpeta contiene datos de la instalación del usuario:

- `games.json`, loadouts, manifiestos, backups, thumbs, caches.

**No** se incluye en el repositorio público. Copiar plantillas desde `examples/`.

Arranque limpio de prueba:

```bat
set SGM_DATA_DIR=%TEMP%\f7777techmods_clean
python -m app
```
