# Adaptadores comunitarios (S50)

Coloque aquí documentos JSON que sigan
[`schemas/community_game_adapter.v1.schema.json`](../schemas/community_game_adapter.v1.schema.json).

- Ejemplos sintéticos: [`examples/`](examples/)
- Guía: [`GAME_ADAPTER_GUIDE.md`](../GAME_ADAPTER_GUIDE.md)
- Contribuir: [`CONTRIBUTING.md`](../CONTRIBUTING.md)

**Importante**

- Solo JSON declarativo en v1.
- No se ejecuta Python ni plugins de terceros.
- `auto_install_allowed` debe ser `false`.
- No omiten backup, confirmación, rollback ni validación de rutas del motor Apply.
- No envíe datos de su instalación real ni rutas personales.
