# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Original_Python_Project\\campus_login_optimized.pyw'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['customtkinter', 'pystray', 'PIL', 'win10toast', 'psutil', 'cryptography'],
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
    name='CampusLogin',
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
)
