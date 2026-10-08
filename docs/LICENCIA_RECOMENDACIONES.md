# Recomendaciones de licencia — F7777techMods

**Estado:** la licencia **GNU GPL v3** fue aplicada en S22 (`LICENSE`). Este documento conserva el análisis previo de opciones.

**Titularidad declarada:** Raúl Ruano Gil — Copyright (c) 2026. Desarrollado bajo Four Seven Tech.

Las cabeceras de código actuales declaran *todos los derechos reservados*. Cualquier licencia futura debe ser una decisión explícita del titular y, si abre derechos, actualizar cabeceras / aviso LICENSE de forma coherente.

## Tres modelos distintos

### A) Publicar código visible (fuente en GitHub)

- El código se ve; eso **no** implica automáticamente permiso de uso/modificación comercial.
- Sin LICENSE clara, terceros suelen asumir «all rights reserved» → no pueden usar legalmente el código.
- Útil si se quiere transparencia sin abrir derechos aún.

### B) Open source (uso y modificación bajo licencia)

Opciones frecuentes:

| Licencia | Notas |
|----------|--------|
| MIT / Apache-2.0 | Permisivas; fácil adopción; menos control sobre derivados |
| MPL-2.0 | Copyleft de archivo; equilibrio razonable para apps de escritorio |
| GPL-3.0 | Copyleft fuerte; obliga a abrir derivados al distribuir |

Si se elige OSS, hay que **sustituir o complementar** el texto «todos los derechos reservados» para no contradecir la licencia.

### C) Distribución de ejecutables con derechos reservados

- Publicar `.exe` / instalador **sin** abrir el código, o con código visible pero licencia propietaria.
- Compatible con las cabeceras actuales.
- GitHub Releases puede hospedar binarios; el repo puede ser privado o público con LICENSE propietaria.

## Dependencias

Al empaquetar, incluir avisos de **customtkinter**, **Pillow** y demás según sus licencias (`requirements.txt` / metadatos de paquetes).

## Recomendación práctica (no vinculante)

1. Fase actual: mantener derechos reservados; no publicar aún.
2. Si se quiere comunidad: MPL-2.0 o Apache-2.0 + NOTICE, y actualizar cabeceras.
3. Si solo se quiere instalador: licencia propietaria + Releases; código privado o público «visible sin OSS».
