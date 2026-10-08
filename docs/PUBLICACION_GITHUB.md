# Instrucciones de publicación GitHub — F7777techMods

**Estado:** la primera publicación pública ya está hecha.  
Este documento es un **checklist** para releases futuras.

| Campo | Valor |
|-------|--------|
| Usuario | `raulito07` |
| Repo | https://github.com/raulito07/F7777techMods |
| Web | https://fourseven.es/ |
| Tag inicial | `v0.1.0-beta` (pre-release) |

**No** recrear el tag `v0.1.0-beta` ni sustituir sus assets con otro contenido bajo el mismo nombre.

---

## Prerrequisitos (releases futuras)

- Autorización explícita del titular.
- Artefacto local verificado (nuevo nombre/versión si cambia el binario).
- Auditoría de privacidad (`tools/s23_git_privacy_inventory.py`).
- Suite de tests OK.
- Árbol público sin materiales internos de desarrollo (ver `tests/test_s26_3_public_tree.py`).

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
- [ ] Sin reglas de IDE/agentes ni informes internos de sesión
- [ ] `app/branding.py` con URLs reales
- [ ] Sin Setup salvo decisión explícita futura
