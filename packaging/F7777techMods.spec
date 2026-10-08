# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — F7777techMods 0.1.0
# No incluir data/ del desarrollador ni mods.

from PyInstaller.utils.hooks import collect_all

block_cipher = None

ctk_datas, ctk_binaries, ctk_hidden = collect_all('customtkinter')

a = Analysis(
    ['../run_f7777techmods.py'],
    pathex=['..'],
    binaries=ctk_binaries,
    datas=[
        ('../LICENSE', '.'),
        ('../THIRD_PARTY_NOTICES.md', '.'),
        ('../docs/README_PORTABLE.md', '.'),
        ('../docs/PRECAUCIONES.md', 'docs'),
        ('../docs/LICENCIAS_AUDITORIA_S22.md', 'docs'),
    ] + ctk_datas,
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'PIL',
        'PIL.Image',
        'packaging',
        'packaging.version',
    ] + list(ctk_hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'openpyxl',
        'et_xmlfile',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='F7777techMods',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='F7777techMods',
)
