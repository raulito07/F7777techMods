# Problemas conocidos — F7777techMods 0.1.0 Beta

## Beta

- Primera distribución pública; validación visual in-game pendiente en varios títulos.
- Remake: instalación controlada de un mod real en desarrollo; validación visual pendiente.
- Rebirth / Stellar Blade: inventario y simulaciones; despliegue real pendiente.

## Windows / distribución

- Canal **PyInstaller portable**: ejecutable **sin firma**; puede bloquearse por WDAC / Code Integrity / SmartScreen.
- Canal **runtime Python** (recomendado en esos equipos): host `pythonw.exe` firmado por Python Software Foundation + launcher VBS.
- No se garantiza ejecución en todos los Windows ni bajo todas las políticas corporativas.

## Vortex

- Estado Enabled/Disabled «actual» a menudo no verificado (no se lee LevelDB `state.v2`).
- Apply bloqueado si existe `vortex.deployment.json` en destino.

## Motor

- Conflictos semánticos FF7R por heurística de nombres.
- HARDLINK solo en el mismo volumen NTFS.
- Interrupción dura del SO durante escritura: no demostrada como 100 % segura.

## UI

- Al cerrar tests automatizados pueden aparecer avisos Tcl/Tk cosméticos.
