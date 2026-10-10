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
- **Adaptadores comunitarios JSON (S50)** bajo `community_adapters/` — ver [GAME_ADAPTER_GUIDE.md](GAME_ADAPTER_GUIDE.md)

## Adaptadores comunitarios (S50)

1. Formato: JSON validado (`schemas/community_game_adapter.v1.schema.json`), API `1.0`.
2. Solo declarativo: formatos, destinos relativos, detección, instrucciones, limitaciones.
3. **No** se ejecuta Python ni plugins de terceros en v1. Código futuro = permiso `request_code_extension_review` + revisión de seguridad.
4. `auto_install_allowed` debe ser `false`. No habilita Apply.
5. No puede omitir validación de rutas, protección de archivos ajenos, backup, confirmación ni rollback.
6. No envíe datos de instalaciones reales ni rutas personales.
7. Incluya pruebas sintéticas (juegos ficticios). Ejemplos en `community_adapters/examples/`.
8. Solicite revisión en el PR indicando evidencias y limitaciones.

Capas a no confundir: juego reconocido ≠ mod reconocido ≠ formato reconocido ≠ destino verificado ≠ instalación automática.

## Cambios que requieren cuidado especial

- Cualquier escritura en destino de mods
- Liberación / borrado respecto a Vortex staging
- Empaquetado Windows
- Extensiones con código (fuera del modelo JSON v1)

## Cabeceras

El código propio lleva cabecera Four Seven Tech + GPL. Usa `tools/_apply_headers_s031.py` tras cambios masivos.

## Pull requests

- Describe el problema y la prueba realizada.
- No incluir `data/`, `dist/`, ni binarios salvo acuerdo explícito para una release.
- Mantén el nombre del producto **F7777techMods**.

## Licencia de contribuciones

Al contribuir, aceptas que tu código se licencie bajo GPL v3 (o posterior), con copyright atribuible según el historial del repo.
