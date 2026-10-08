# Instrucciones de publicación GitHub — F7777techMods

**Estado:** la primera publicación (S25) ya está hecha.  
Este documento queda como **histórico / checklist** para releases futuras.

| Campo | Valor real |
|-------|------------|
| Usuario | `raulito07` |
| Repo | https://github.com/raulito07/F7777techMods |
| Web | https://fourseven.es/ |
| Tag inicial | `v0.1.0-beta` (pre-release) |
| Informe | `INFORME_S25_PUBLICACION.md` |

**No** recrear el tag `v0.1.0-beta` ni sustituir sus assets con otro contenido bajo el mismo nombre.

---

## Prerrequisitos (releases futuras)

- Autorización explícita del titular.
- Artefacto local verificado (nuevo nombre/versión si cambia el binario).
- Auditoría de privacidad (`tools/s23_git_privacy_inventory.py`).
- Suite de tests OK.

```powershell
Get-FileHash -Algorithm SHA256 dist\release\<NUEVO_ZIP>
```

---

## Checklist post-release

- [ ] Repo público visible
- [ ] LICENSE / README / web fourseven.es
- [ ] Pre-release o release con ZIP + SHA
- [ ] Hash del asset = referencia documentada
- [ ] Sin `data/` ni rutas privadas en el árbol
- [ ] `app/branding.py` con URLs reales
- [ ] Sin Setup salvo decisión explícita futura

Procedimiento detallado original de S24/S25: ver historial Git e `INFORME_S25_PUBLICACION.md`.
