# Instalación — F7777techMods

**Producto:** F7777techMods  
**Empresa:** Four Seven Tech  
**Versión documentada:** 0.1.0

## Desarrollo desde código

1. Clonar o copiar el repositorio (cuando exista remoto).
2. Crear entorno virtual e instalar `requirements.txt`.
3. Arrancar con `python -m app`.
4. Opcional: `SGM_DATA_DIR` apunta a una carpeta vacía para perfil limpio.

## Primer uso

1. Abrir **Juegos y ajustes** → añadir o seleccionar juego.
2. Indicar carpeta destino de mods (p. ej. `~mods`) y staging (p. ej. Vortex `mods`).
3. Elegir adaptador adecuado (`ue4_paks_mods`, `ue5_iostore_mods`, `generic_folder`).
4. **Actualizar** inventario → preparar plan en Biblioteca → **Simular** → **Aplicar**.

## Datos

- Por defecto: `data/` junto al código.
- Con `SGM_DATA_DIR`: esa carpeta sustituye `data/`.
- Plantilla: `examples/games.example.json`.

## Variables opcionales

| Variable | Uso |
|----------|-----|
| `SGM_DATA_DIR` | Raíz de datos del gestor |
| `SGM_STEAM_COMMON` | Override de `steamapps/common` |
| `SGM_LEGACY_FF7R_GAME_ROOT` | Override raíz FF7 Remake |
| `SGM_LEGACY_FF7R_STAGE` | Override staging Vortex Remake |
| `SGM_VORTEX_MODS_<ID>` | Override staging por gameId Vortex |
| `SGM_VORTEX_DL_<ID>` | Override downloads Vortex |

## Ejecutable (futuro)

El nombre previsto del ejecutable es `F7777techMods` (`app/version.py` → `__executable_name__`). El instalador no debe empaquetar el `data/` del desarrollador.
