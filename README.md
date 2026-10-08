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
- Inventario desde staging Vortex (lectura) y/o biblioteca de trabajo
- Plan, prioridades, conflictos y detección de estructura
- **Simular** antes de escribir; **Apply** con validaciones del motor
- Modos **COPY / HARDLINK / AUTO**
- Manifiesto, backups y recuperación
- Archivado ZIP propio y ciclo **WORK_LIBRARY**

## Compatibilidad (0.1.0 Beta)

| Juego | Estado |
|-------|--------|
| **FINAL FANTASY VII REMAKE** | Instalación controlada de un mod real en desarrollo; **validación visual in-game pendiente**. |
| **FINAL FANTASY VII REBIRTH** | Inventario y simulaciones; **despliegue real pendiente**. |
| **Stellar Blade** | Inventario y simulaciones; **despliegue real pendiente**. |

## Uso

1. Configurar juego, staging y destino en **Juegos y ajustes**.
2. **Actualizar** → plan en Biblioteca → **Simular** → **Aplicar** (solo tras confirmar).

Datos: `%LOCALAPPDATA%\FourSevenTech\F7777techMods\` · Override: `SGM_DATA_DIR`.

## Distribución

| Canal | Entrada | Notas |
|-------|---------|--------|
| **Diario (recomendado bajo WDAC)** | `pythonw` firmado + VBS | [docs/DISTRIBUCION.md](docs/DISTRIBUCION.md) · [docs/DESARROLLO.md](docs/DESARROLLO.md) |
| **Portable GitHub** | `F7777techMods.exe` (PyInstaller, sin firma) | ZIP `v0.1.0-beta`; puede bloquearse por políticas Windows |

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
