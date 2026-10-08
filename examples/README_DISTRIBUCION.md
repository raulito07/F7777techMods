# Preparación para distribución — F7777techMods

**Empresa:** Four Seven Tech  
**Autor:** Raúl Ruano Gil  
**Estado:** primera publicación pública completada (S25).  
**Repo:** https://github.com/raulito07/F7777techMods  

Esta carpeta solo aporta **plantillas** (`games.example.json`).  
La guía de distribución vigente está en [docs/README_DISTRIBUCION.md](../docs/README_DISTRIBUCION.md).

## Qué NO debe ir al repositorio público

- `data/` real (games.json, manifiestos, backups, thumbs, caches, resultados `_s*`).
- Capturas `_s*_captures/` con rutas de usuario.
- Informes internos no exceptuados en `.gitignore`.
- Logs, tokens, `.env`, credenciales.
- Mods (`.pak` / IoStore) ni carpetas Vortex/Steam.

## Identidad

- Producto: **F7777techMods** (cuatro sietes)
- Empresa: Four Seven Tech
- Autor / copyright: Raúl Ruano Gil (c) 2026
- Web: https://fourseven.es/
- Licencia: GNU GPL v3 (`LICENSE`)
- Enlaces oficiales: `app/branding.py`

## Arranque limpio de prueba

```bat
set SGM_DATA_DIR=%TEMP%\f7777techmods_clean
python -m app
```
