# Problemas conocidos — F7777techMods 0.1.0 Beta

## Beta

- Primera distribución pública como **portable** Windows (`v0.1.0-beta` pre-release).
- Web: https://fourseven.es/
- Remake: mod real controlado en desarrollo; validación visual en juego pendiente.
- Rebirth / Stellar Blade: inventario y simulaciones; despliegue real pendiente.

## Windows / ejecutable

- Portable **sin firma Authenticode**.
- En algunos equipos puede bloquearse por SmartScreen, Code Integrity o políticas corporativas (documentado en S22/S22.1).
- No se garantiza ejecución en todos los Windows.

## Vortex

- Estado Enabled/Disabled «actual» a menudo **no verificado** (no se lee LevelDB `state.v2`).
- Apply bloqueado si existe `vortex.deployment.json` en destino.

## Motor

- Conflictos semánticos FF7R por heurística de nombres.
- HARDLINK solo en el mismo volumen NTFS.
- Interrupción dura del SO durante escritura: no demostrada como 100 % segura.

## UI

- Al cerrar tests automatizados pueden aparecer avisos Tcl/Tk (`check_if_scrollbars_needed`); cosméticos.
