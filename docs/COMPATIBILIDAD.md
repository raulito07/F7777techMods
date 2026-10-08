# Compatibilidad y limitaciones — F7777techMods

## Compatible (enfoque actual)

- Windows + rutas locales.
- Juegos con carpeta de mods estilo Unreal (`~mods` / Paks).
- Lectura de staging Vortex (carpetas + algunos backups JSON).
- FF7 Remake (adaptador UE4), perfiles experimentales Rebirth / Stellar Blade.

## Limitaciones

- No lee LevelDB vivo de Vortex (`state.v2`) → enablement «no verificado» salvo evidencias en disco.
- No ejecuta Deploy/Purge de Vortex.
- No modifica Steam.
- Conflictos semánticos por nombre, no por contenido del pak.
- HARDLINK solo mismo volumen NTFS.
- Interrupción dura del SO durante escritura: no demostrada como segura al 100 %.
- Symlinks de escape: pruebas omitidas sin privilegios de administrador.

## Terceros

Steam, Vortex, Nexus Mods y marcas de juegos pertenecen a sus titulares. F7777techMods no las redistribuye ni usa sus logos como marca propia.
