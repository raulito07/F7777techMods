# Contribuir a F7777techMods

Gracias por tu interés. Este proyecto es software libre bajo **GNU GPL v3**.

## Antes de contribuir

1. Lee [docs/PRECAUCIONES.md](docs/PRECAUCIONES.md) y [SECURITY.md](SECURITY.md).
2. No envíes mods, capturas con rutas personales, tokens ni datos de tu instalación real.
3. Las pruebas de escritura deben usar carpetas temporales (`SGM_DATA_DIR` / sandboxes).

## Desarrollo local

Ver [docs/DESARROLLO.md](docs/DESARROLLO.md) (ejecutar, tests, runtime diario, rollback, release portable).

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests
python run_f7777techmods.py
```

Scripts en `legacy/` (Excel FF7R): `pip install -r requirements-legacy.txt` — no forman parte del runtime.

## Cambios aceptables

- Correcciones de bugs del motor o UI
- Mejoras de documentación
- Pruebas automatizadas en temporales
- Adaptadores nuevos **sin** tocar instalaciones ajenas por defecto

## Cambios que requieren cuidado especial

- Cualquier escritura en destino de mods
- Liberación / borrado respecto a Vortex staging
- Empaquetado Windows

## Cabeceras

El código propio lleva cabecera Four Seven Tech + GPL. Usa `tools/_apply_headers_s031.py` tras cambios masivos.

## Pull requests

- Describe el problema y la prueba realizada.
- No incluir `data/`, `dist/`, ni binarios salvo acuerdo explícito para una release.
- Mantén el nombre del producto **F7777techMods**.

## Licencia de contribuciones

Al contribuir, aceptas que tu código se licencie bajo GPL v3 (o posterior), con copyright atribuible según el historial del repo.
