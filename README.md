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

> Nombre exacto: **F7777techMods** (cuatro sietes). Carpeta de desarrollo: `02_Steam_Gestor_Mods` (sin renombrar).

---

## Funcionalidades

- Selector multijuego y datos aislados por perfil
- Inventario desde staging Vortex (lectura) y/o biblioteca de trabajo
- Plan de mods, prioridades y **conflictos** por archivo
- **Simular** antes de escribir; **Apply** solo con validaciones del motor
- Modos **COPY / HARDLINK / AUTO**
- Manifiesto, backups y recuperación
- Archivado ZIP propio y ciclo **WORK_LIBRARY**
- UI por paneles; Acerca de con identidad Four Seven Tech y GPL v3

## Compatibilidad (0.1.0 Beta)

| Juego | Estado |
|-------|--------|
| **FINAL FANTASY VII REMAKE** | Instalación controlada de un mod real realizada en desarrollo; **validación visual dentro del juego pendiente**. |
| **FINAL FANTASY VII REBIRTH** | Inventario y simulaciones probados; **despliegue real pendiente**. |
| **Stellar Blade** | Inventario y simulaciones probados; **despliegue real pendiente**. |

No se afirma el mismo procedimiento en todos los juegos ni compatibilidad completa sin más pruebas.

## Instalación portable

1. Descarga `F7777techMods_v0.1.0_Windows_Portable.zip` desde la [pre-release `v0.1.0-beta`](https://github.com/raulito07/F7777techMods/releases/tag/v0.1.0-beta).
2. Extrae la carpeta completa.
3. Ejecuta `F7777techMods\F7777techMods.exe`.
4. Configura juegos y directorios.

Datos: `%LOCALAPPDATA%\FourSevenTech\F7777techMods\` · Override: `SGM_DATA_DIR`.  
Guía: [docs/README_PORTABLE.md](docs/README_PORTABLE.md).

### Advertencias

- Primera **beta** pública.
- Ejecutable **sin firma digital**.
- Algunas políticas de seguridad de Windows pueden impedir la ejecución.
- Compatibilidad con juegos **en validación**.
- **No** se garantiza compatibilidad universal con todos los Windows ni todos los setups de mods.

## Vortex

Vortex (y Nexus) siguen siendo la fuente habitual de **descargas y actualizaciones**. Este gestor **lee** el staging; no ejecuta Deploy/Purge automáticamente. Con `vortex.deployment.json` en destino, Apply queda bloqueado hasta Purge en Vortex.

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) | Uso diario |
| [docs/MODOS_INSTALACION.md](docs/MODOS_INSTALACION.md) | COPY / HARDLINK / AUTO |
| [docs/CONFLICTOS.md](docs/CONFLICTOS.md) | Conflictos |
| [docs/ARCHIVADO_Y_RECUPERACION.md](docs/ARCHIVADO_Y_RECUPERACION.md) | ZIP / WORK_LIBRARY |
| [docs/PRECAUCIONES.md](docs/PRECAUCIONES.md) | Antes de mods reales |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | Problemas conocidos |
| [docs/RELEASE_NOTES_v0.1.0.md](docs/RELEASE_NOTES_v0.1.0.md) | Notas de la beta |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribuciones |
| [SECURITY.md](SECURITY.md) | Seguridad |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Terceros |

## Desarrollo

Requisitos: Windows 10/11, Python 3.11+ (validado con 3.12).

```bat
git clone https://github.com/raulito07/F7777techMods.git
cd F7777techMods
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set SGM_DATA_DIR=%TEMP%\f7777techmods_clean
python -m app
python -m unittest discover -s tests -v
```

### Construir el portable (local)

```bat
pip install -r requirements-build.txt
python tools/s22_1_build_portable.py
```

El ZIP se genera bajo `dist/release/`. No incluye `data/` del desarrollador ni reglas de IDE.  
Scripts Excel antiguos (`legacy/`) no son necesarios para ejecutar ni empaquetar; ver `requirements-legacy.txt`.

## Licencia

GNU GPL v3 — ver [LICENSE](LICENSE).  
Copyright (c) 2026 Raúl Ruano Gil. Desarrollado bajo Four Seven Tech.  
https://fourseven.es/
