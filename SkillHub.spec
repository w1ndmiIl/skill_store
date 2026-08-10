# -*- mode: python ; coding: utf-8 -*-

from importlib.util import find_spec


if find_spec('yaml') is None:
    raise RuntimeError(
        'PyYAML is required for packaging. Build with '
        r'.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm SkillHub.spec'
    )


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('app.ico', '.')],
    hiddenimports=['yaml', 'ddgs', 'requests', 'lxml', 'httpx', 'h2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SkillHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)
