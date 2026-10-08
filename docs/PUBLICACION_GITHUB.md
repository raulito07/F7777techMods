# Instrucciones de publicación GitHub — F7777techMods

**NO ejecutar** estos pasos hasta autorización explícita del usuario.  
Sustituye `GITHUB_USER` por el usuario GitHub personal confirmado.

Web oficial: https://fourseven.es/  
Repo: `F7777techMods` (cuenta personal; sin organización empresarial).  
Tag: `v0.1.0-beta` (pre-release).

---

## 0. Prerrequisitos

- Git instalado; autenticación GitHub (HTTPS o SSH) lista.
- Artefacto local verificado:

```text
dist/release/F7777techMods_v0.1.0_Windows_Portable.zip
SHA-256: 1876a7c46aeb4aa25885b3fad14888472e359153f93af1d447eef95f6007dda9
```

```powershell
Get-FileHash -Algorithm SHA256 dist\release\F7777techMods_v0.1.0_Windows_Portable.zip
```

---

## 1. Configurar identidad Git (solo si hace falta en esta máquina)

```powershell
# Solo si aún no hay identidad local de commits (NO forzar si ya existe)
# git config user.name "Raúl Ruano Gil"
# git config user.email "EMAIL_PUBLICO_GITHUB"
```

---

## 2. Primer commit (local)

Desde la raíz del proyecto:

```powershell
cd RUTA\A\02_Steam_Gestor_Mods
git status -sb
python tools/s23_git_privacy_inventory.py
git add -A
git status
git diff --cached --stat
git commit -m "Initial public tree for F7777techMods 0.1.0-beta (GPL-3.0)."
```

Revisar que **no** entren `data/*.json` reales ni `dist/`.

---

## 3. Crear repositorio remoto (cuenta personal)

Opción A — GitHub CLI (logueado como el usuario personal):

```powershell
gh repo create F7777techMods --public --source=. --remote=origin --description "F7777techMods — gestor multijuego de mods para Windows (GPL-3.0). Portable. by Four Seven Tech." --push
```

Opción B — crear vacío en github.com y luego:

```powershell
git remote add origin https://github.com/GITHUB_USER/F7777techMods.git
git push -u origin main
```

---

## 4. Topics / About en GitHub (UI)

- Website: `https://fourseven.es/`
- Topics: ver `GITHUB_REPO.md`
- No crear organización Four Seven Tech en GitHub para este paso.

---

## 5. Pre-release `v0.1.0-beta`

```powershell
# Copiar SHA a archivo de release
Copy-Item docs\SHA256SUMS_v0.1.0.txt dist\release\SHA256SUMS.txt -Force

gh release create v0.1.0-beta `
  "dist/release/F7777techMods_v0.1.0_Windows_Portable.zip" `
  "dist/release/SHA256SUMS.txt" `
  --title "F7777techMods v0.1.0-beta (portable)" `
  --notes-file docs/RELEASE_NOTES_v0.1.0.md `
  --prerelease
```

---

## 6. Tras publicar la URL real

1. Rellenar en `app/branding.py`:
   - `OFFICIAL_GITHUB_URL`
   - `OFFICIAL_RELEASES_URL`
2. Commit de seguimiento (autorizado) actualizando README si hace falta.

---

## 7. Comprobación post-publicación

- [ ] Repo público visible
- [ ] LICENSE / README / web fourseven.es
- [ ] Pre-release con ZIP + SHA
- [ ] Hash del asset = referencia
- [ ] Sin `data/` ni rutas privadas en el árbol
- [ ] Issues templates visibles
