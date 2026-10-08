# Desarrollo y mantenimiento — F7777techMods

Procedimiento vigente (S32). Ver también [ENTORNOS.md](ENTORNOS.md).

## A. Ejecutar en desarrollo

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_f7777techmods.py
```

Datos de desarrollo: carpeta `data/` del repo, o `set SGM_DATA_DIR=...`.

## B. Tests

```bat
python -m unittest discover -s tests
```

## C. Construir runtime redistribuible

Requiere Python 3.12 oficial (firmado) en la máquina de build. El venv **se regenera**; no se copia entre PCs.

```bat
python tools\s30_3_install_runtime_daily.py --build
```

Salida: `dist/F7777techMods_runtime/` (gitignored).

## D. Actualizar instalación diaria (autorización explícita)

1. Cerrar F7777techMods.
2. Suite de tests en verde.
3. `--build` correcto.
4. Solo entonces:

```bat
python tools\s30_3_install_runtime_daily.py --install --shortcut
```

No automatizar esto en cada cambio de código.

## E. Rollback de la instalación diaria

```bat
python tools\s30_3_install_runtime_daily.py --rollback
```

Restaura `%LOCALAPPDATA%\Programs\FourSevenTech\F7777techMods_prev`. Los datos de usuario no se tocan.

## F. Preparar release portable (GitHub)

Canal ZIP PyInstaller (alternativa al runtime diario):

```bat
pip install -r requirements-build.txt
python tools\s22_1_build_portable.py
```

Ver [DISTRIBUCION.md](DISTRIBUCION.md). No incluye Setup/Inno en el canal público.
