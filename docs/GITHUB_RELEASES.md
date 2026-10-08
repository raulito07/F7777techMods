# Estructura para GitHub Releases — F7777techMods

**Estado:** preparación local. No crear remoto ni publicar releases en S21.

## Convención de tags

```text
v0.1.0
```

Alineado con `app/version.py`.

## Artefactos sugeridos (futuro)

```text
F7777techMods-0.1.0-win64.zip
F7777techMods-0.1.0-Setup.exe   (opcional)
SHA256SUMS.txt
```

Contenido del ZIP:

- Ejecutable / carpeta empaquetada
- `README.md` / licencia elegida
- `examples/` (sin datos personales)
- **Sin** `data/` del autor, **sin** mods, **sin** capturas privadas

## Notas de release (plantilla)

```markdown
## F7777techMods vX.Y.Z

### Cambios
- …

### Requisitos
- Windows 10/11

### Precauciones
- Leer docs/PRECAUCIONES.md antes de Apply real.
```

## Checklist pre-release

- [ ] Versión en `app/version.py`
- [ ] Cabeceras actualizadas
- [ ] Auditoría de privacidad limpia en el árbol a publicar
- [ ] `.gitignore` aplicado; nada de `data/` real trackeado
- [ ] Licencia decidida (si aplica)
- [ ] Enlaces en `app/branding.py` rellenados (o siguen ocultos)
- [ ] Suite de tests en verde
