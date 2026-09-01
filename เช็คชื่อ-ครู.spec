# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['admin.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/alert_thai.mp3', '.'), ('assets/alert_thai2.mp3', '.'), ('assets/alert_thai3.mp3', '.'), ('assets/logo_small.png', '.')],
    hiddenimports=[],
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
    name='กระดิ่งทองมรณะ-แอดมิน',
    icon='assets/logo.ico',
    version='version_admin.txt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
