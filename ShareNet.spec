# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

playwright_datas, playwright_bins, playwright_hidden = collect_all("playwright")
ctk_datas, ctk_bins, ctk_hidden = collect_all("customtkinter")

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=playwright_bins + ctk_bins,
    datas=playwright_datas + ctk_datas + [("runtime", "runtime"), ("assets", "assets")],
    hiddenimports=playwright_hidden + ctk_hidden + [
        "keyring.backends.Windows",
        "sharenet.app",
        "sharenet.routers.c80",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ShareNet-v1.0.0-Windows-x64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    uac_admin=True,
    target_arch="x86_64",
    icon="assets/sharenet.ico",
)
