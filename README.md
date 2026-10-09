# F7777techMods

**by Four Seven Tech**  
**Autor:** Raúl Ruano Gil  
**Versión:** 0.1.0 Beta  
**Licencia:** [GNU GPL v3](LICENSE)  
**Web oficial:** https://fourseven.es/  
**GitHub:** https://github.com/raulito07/F7777techMods  
**Releases:** https://github.com/raulito07/F7777techMods/releases

Gestor local **multijuego** de mods para Windows: inventaria packs desde un staging (p. ej. carpeta de mods de Vortex), prepara un plan, simula, aplica con manifiesto/backup y permite archivado / biblioteca de trabajo.

Aplicación **independiente**; no afiliada a Square Enix, Steam, Nexus Mods ni Vortex.

> Nombre exacto del producto: **F7777techMods** (cuatro sietes consecutivos).

## Funcionalidades

- Selector multijuego y datos aislados por perfil
- **Biblioteca universal** del catálogo local: vistas **TABLA**, **CATÁLOGO** y **LISTA VISUAL**, con lista completa paginada y miniaturas asíncronas
- Selección por **componentes independientes** (packs con varias piezas opcionales)
- Inventario desde staging **Vortex (solo lectura)** y/o biblioteca de trabajo; sin Deploy/Purge automático
- Plan, prioridades, **conflictos**, fusión de manifiesto y detección de estructura
- **Simulación opcional** antes de escribir; **Apply** con confirmación y validaciones del motor (destino, deployment ajeno, estructura ambigua)
- Modos **COPY / HARDLINK / AUTO**
- Manifiesto, backups, estado instalado y recuperación
- Archivado ZIP propio y ciclo **WORK_LIBRARY**
- Identidad de paquetes y contexto de mods importados desde Vortex (modelo de lectura, no sustituye a Vortex)

> La interfaz y el motor están pensados para ampliarse a más juegos, pero los **adaptadores de instalación disponibles siguen siendo limitados** (ver tabla de compatibilidad). No es soporte universal de instalación.

## Compatibilidad (0.1.0 Beta)

Estado **validado por juego** (tests automatizados + pruebas locales; no implica certificación del editor):

| Juego | Inventario / biblioteca | Plan / conflictos | Apply real | Notas |
|-------|-------------------------|-------------------|------------|-------|
| **FINAL FANTASY VII REMAKE** | Sí | Sí | Parcial | Mod real en desarrollo; **validación visual in-game pendiente**. |
| **FINAL FANTASY VII REBIRTH** | Sí | Sí | No | **Despliegue real pendiente**. |
| **Stellar Blade** | Sí | Sí | No | **Despliegue real pendiente**. |

### EMOV y multidestino (experimental)

Rutas **EMOV** (estructuras especiales en staging) y despliegue **multidestino** tienen cobertura de tests, pero el comportamiento en mods reales puede variar. Tratar como **soporte experimental**: revisar simulación, manifiesto y backups antes de Apply.

## Uso

1. Configurar juego, staging y destino en **Juegos y ajustes**.
2. **Actualizar** → plan en Biblioteca → **Simular** → **Aplicar** (solo tras confirmar).

Datos: `%LOCALAPPDATA%\FourSevenTech\F7777techMods\` · Override: `SGM_DATA_DIR`.

## Distribución

| Canal | Entrada | Notas |
|-------|---------|--------|
| **Diario (recomendado bajo WDAC)** | `pythonw` firmado + VBS | [docs/DISTRIBUCION.md](docs/DISTRIBUCION.md) · [docs/DESARROLLO.md](docs/DESARROLLO.md) |
| **Portable GitHub** | `F7777techMods.exe` (PyInstaller, sin firma) | Release **v0.1.0-beta** existente; el código fuente puede ir por delante de un ZIP instalable |

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) | Uso diario |
| [docs/ENTORNOS.md](docs/ENTORNOS.md) | Desarrollo / instalación / datos |
| [docs/DESARROLLO.md](docs/DESARROLLO.md) | Tests, build, update, rollback, release |
| [docs/DISTRIBUCION.md](docs/DISTRIBUCION.md) | Runtime Python vs PyInstaller |
| [docs/MODOS_INSTALACION.md](docs/MODOS_INSTALACION.md) | COPY / HARDLINK / AUTO |
| [docs/CONFLICTOS.md](docs/CONFLICTOS.md) | Conflictos |
| [docs/ARCHIVADO_Y_RECUPERACION.md](docs/ARCHIVADO_Y_RECUPERACION.md) | ZIP / WORK |
| [docs/PRECAUCIONES.md](docs/PRECAUCIONES.md) | Antes de mods reales |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Problemas conocidos |
| [CHANGELOG.md](CHANGELOG.md) | Cambios |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribuciones |
| [SECURITY.md](SECURITY.md) | Seguridad |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Terceros |

## Desarrollo

```bat
git clone https://github.com/raulito07/F7777techMods.git
cd F7777techMods
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set SGM_DATA_DIR=%TEMP%\f7777techmods_clean
python run_f7777techmods.py
python -m unittest discover -s tests
```

Detalle: [docs/DESARROLLO.md](docs/DESARROLLO.md).

## Licencia

GNU GPL v3 — ver [LICENSE](LICENSE).  
Copyright (c) 2026 Raúl Ruano Gil. Desarrollado bajo Four Seven Tech.  
https://fourseven.es/
