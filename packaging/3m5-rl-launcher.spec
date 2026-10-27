# PyInstaller spec - build with: pyinstaller packaging/3m5-rl-launcher.spec
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

here = os.path.abspath(SPECPATH)
assets = os.path.join(here, '..', 'src', 'rl_launcher', 'assets')

a = Analysis(
    [os.path.join(here, 'launcher.py')],
    pathex=[os.path.join(here, '..', 'src')],
    datas=[(assets, 'rl_launcher/assets')],
    hiddenimports=collect_submodules('legendary'),
    excludes=['tkinter', 'webview'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='3m5-rl-launcher',
    console=False,
    upx=False,
    icon=os.path.join(here, 'icon.ico') if sys.platform == 'win32' else None,
)
