# Preparación para distribución — F7777techMods

**Empresa:** Four Seven Tech  
**Autor:** Raúl Ruano Gil  
**Estado:** preparación S21 — no publicar todavía.

## Qué NO debe ir al repositorio público

- `data/` real (games.json, manifiestos, backups, thumbs, caches, resultados `_s*`).
- Capturas `_s*_captures/` con rutas de usuario.
- Informes internos `INFORME_S0*`–`INFORME_S2*` (excepto el informe de publicación acordado).
- Logs, tokens, `.env`, credenciales.
- Mods (`.pak` / IoStore) ni carpetas Vortex/Steam.

Usar `.gitignore`. Plantilla: `games.example.json` → `data/games.json` (local).

## Identidad

- Producto: **F7777techMods**
- Empresa: Four Seven Tech
- Autor / copyright: Raúl Ruano Gil (c) 2026
- Enlaces: `app/branding.py` (vacíos = ocultos)
- Ejecutable futuro: `F7777techMods`

## Licencia

Ver `docs/LICENCIA_RECOMENDACIONES.md`. No aplicada automáticamente.

## Arranque limpio

```bat
set SGM_DATA_DIR=%TEMP%\f7777techmods_clean
python -m app
```
