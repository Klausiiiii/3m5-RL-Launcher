"""End-to-end on Linux: real LegendaryCore + Backend + real Wine, launching a real Windows executable.

The "game" is Wine's cmd.exe with predefined launch parameters ``/c exit 7``; getting exit code 7 back proves
that Legendary's launch parameters, our runner command and the Wine prefix handling work together.
"""
import os
import shutil
import subprocess
import sys

import pytest

WINE = next((p for p in (shutil.which('wine'), '/usr/lib/wine/wine64') if p and os.path.exists(p)), None)
pytestmark = pytest.mark.skipif(sys.platform == 'win32' or not WINE, reason='needs Wine on Linux')


def test_launch_windows_exe_through_wine(tmp_path, monkeypatch):
    monkeypatch.setenv('LEGENDARY_CONFIG_PATH', str(tmp_path / 'legendary'))
    monkeypatch.setenv('WINEDEBUG', '-all')
    from legendary.core import LegendaryCore
    from legendary.models.game import Game, GameAsset, InstalledGame

    from rl_launcher.backend import Backend
    from rl_launcher.runners import Runner
    from rl_launcher.settings import Settings

    runner = Runner('wine', 'Wine', WINE)
    prefix_root = str(tmp_path / 'prefix')
    _, env = runner.build('wineboot', [], prefix_root)
    subprocess.run([WINE, 'wineboot', '-i'], env={**os.environ, **env}, check=True, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys32 = os.path.join(prefix_root, 'pfx', 'drive_c', 'windows', 'system32')

    core = LegendaryCore()
    with core.lgd.userdata_lock as lock:
        lock.data = {'displayName': 'Klaus', 'account_id': 'acc'}
    asset = GameAsset(app_name='Sugar', asset_id='', build_version='1', catalog_item_id='c', label_name='Live',
                      namespace='sugar', metadata={})
    core.lgd.set_game_meta('Sugar', Game(app_name='Sugar', app_title='Rocket League', asset_infos={'Windows': asset},
                                         metadata={'namespace': 'sugar', 'id': 'c'}))
    core.lgd.set_installed_game('Sugar', InstalledGame(
        app_name='Sugar', install_path=sys32, title='Rocket League', version='1', executable='cmd.exe',
        can_run_offline=True, launch_parameters='/c exit 7'))

    proc = Backend(Settings(prefix_root=prefix_root), core).launch(runner, offline=True)
    assert proc.wait(timeout=300) == 7
