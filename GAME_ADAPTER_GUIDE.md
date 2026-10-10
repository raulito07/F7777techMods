# Guía de adaptadores de juego (comunidad) — F7777techMods

**Empresa:** Four Seven Tech · **Producto:** F7777techMods · **Licencia:** GPL-3.0-or-later  
**API comunitaria:** `1.0` (`COMMUNITY_ADAPTER_API_VERSION`)

## Principio

F7777techMods puede ampliarse a nuevos juegos **sin modificar el núcleo**, mediante documentos JSON revisados.  
**Reconocer un juego, un mod o un formato no implica instalación automática.**

Capas independientes (no las mezcle):

| Capa | Significado |
|------|-------------|
| Juego reconocido | Hay adaptador oficial o comunitario para ese `game_id` |
| Mod reconocido | Hay identidad / payload en Biblioteca |
| Formato reconocido | Extensiones o familia declarada/detectada |
| Destino verificado | Ruta relativa con evidencia *confirmada* y pruebas |
| Instalación automática compatible | Solo motor Apply oficial + formatos ya soportados |

## Cómo añadir un juego

1. Elija un `game_ids` estable en `snake_case` (p. ej. `aurora_legends`).
2. Cree un JSON en `community_adapters/` (vea `examples/`).
3. Cumpla el schema: `schemas/community_game_adapter.v1.schema.json`.
4. Declare detección **solo lectura** (`steam_app_ids`, nombres de carpeta, rutas relativas).
5. Documente limitaciones.
6. Añada pruebas sintéticas (carpetas temporales; nunca datos reales de usuarios).
7. Abra una solicitud de revisión (PR / issue) describiendo evidencias.

No reutilice ids de adaptadores oficiales (`generic_folder`, `ue4_paks_mods`, `ue5_iostore_mods`).

## Cómo declarar formatos

```json
"formats": [
  {
    "id": "mi_formato",
    "extensions": [".ext"],
    "label": "Nombre legible",
    "installer_id": "",
    "notes": "Sin installer_id = reconocido, no instalable automáticamente"
  }
]
```

Un formato **sin** `installer_id` es válido: aparece en inventario e investigación, pero **no** habilita Apply.

## Cómo indicar destinos

- Solo rutas **relativas** al root del juego.
- Prohibido: absolutas, `..`, UNC, sobrescritura de originales.
- `verified: true` exige `evidence: "confirmada"` y referencias de prueba; si no, el cargador degrada `verified`.

## Cómo aportar pruebas

- Fixtures bajo `tests/` con juegos **ficticios**.
- Use `SGM_DATA_DIR` / temporales.
- Cite `test_refs` en `compatibility`.
- Compatibilidad `sin_pruebas` genera aviso: no habilita instalación.

## Cómo documentar limitaciones

Liste en `limitations` y `conflicts_notes` / `dependencies_notes` todo lo que el adaptador **no** hace (herramientas externas, FOMOD, etc.).

## Cómo solicitar revisión

1. PR con JSON + tests + descripción de evidencias.
2. Si necesita código Python futuro: permiso `request_code_extension_review` (no se ejecuta en v1).
3. Seguridad revisará que no omita: validación de rutas, archivos ajenos, backup, confirmación, rollback, restricciones Apply.

## Cómo contribuir sin datos de otros usuarios

- No envíe mods, capturas con rutas `C:\Users\...`, tokens, perfiles Vortex reales ni manifiestos personales.
- Anonymice ids de Steam si aporta logs.
- Prefiera ejemplos sintéticos como en `community_adapters/examples/`.

## Seguridad (no negociable)

Los adaptadores comunitarios **no pueden**:

- Ejecutar Python/scripts/plugins descargados
- Poner `auto_install_allowed: true` con efecto
- Omitir backup / confirmación / rollback
- Sobrescribir archivos originales del juego
- Forzar el motor Apply

Ver `app/core/community_adapter_security.py`.

## Ejemplos

| Archivo | Idea |
|---------|------|
| `aurora_legends_datapack.json` | Un formato propio `.datapack` |
| `nebula_rift_shaders.json` | Instalación externa (shaders) |
| `orbit_tales_mixed.json` | Varios formatos + petición de revisión de código |

## Relación con S49

El investigador universal (`mod_investigator.py`) clasifica mods aunque no haya adaptador.  
El adaptador comunitario aporta **declaraciones** (formatos/destinos/manual); la Biblioteca muestra un resumen claro al jugador y el detalle técnico solo en «Información técnica».
