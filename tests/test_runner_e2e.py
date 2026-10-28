"""End-to-end on Linux: real LegendaryCore + Backend + a real runner (Wine, Proton, umu) starting a Windows exe.

The "game" is cmd.exe with predefined launch parameters ``/c exit 7``. Getting exit code 7 back proves that
Legendary's launch parameters, our runner command/environment and the prefix handling work together.
Each runner is used when available locally or provided via WINE_BIN / PROTON_BIN / UMU_BIN (CI sets them,
so there the tests cannot be skipped silently).
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

from rl_launcher.runners import PROTON, UMU, WINE, Runner

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='Linux only')

_WINE_CANDIDATES = (shutil.which('wine'), shutil.which('wine64'), '/usr/lib/wine/wine64')
WINE_BIN = os.environ.get('WINE_BIN') or next((p for p in _WINE_CANDIDATES if p and os.path.exists(p)), None)
PROTON_BIN = os.environ.get('PROTON_BIN')
UMU_BIN = os.environ.get('UMU_BIN') or shutil.which('umu-run')
# first umu run downloads the Steam Runtime, so allow some minutes
LAUNCH_TIMEOUT = int(os.environ.get('LAUNCH_TIMEOUT', '420'))


def _seed_core(install_dir: str):
    from legendary.core import LegendaryCore
    from legendary.models.game import Game, GameAsset, InstalledGame

    core = LegendaryCore()
    with core.lgd.userdata_lock as lock:
        lock.data = {'displayName': 'Klaus', 'account_id': 'acc'}
    asset = GameAsset(app_name='Sugar', asset_id='', build_version='1', catalog_item_id='c', label_name='Live',
                      namespace='sugar', metadata={})
    core.lgd.set_game_meta('Sugar', Game(app_name='Sugar', app_title='Rocket League', asset_infos={'Windows': asset},
                                         metadata={'namespace': 'sugar', 'id': 'c'}))
    core.lgd.set_installed_game('Sugar', InstalledGame(
        app_name='Sugar', install_path=install_dir, title='Rocket League', version='1', executable='cmd.exe',
        can_run_offline=True, launch_parameters='/c exit 7'))
    return core


def _proton_cmd_dir(proton_script: str) -> str:
    found = glob.glob(os.path.join(os.path.dirname(proton_script), 'files', 'lib*', 'wine', 'x86_64-windows',
                                   'cmd.exe'))
    assert found, 'cmd.exe not found in Proton build'
    return os.path.dirname(found[0])


def _launch(runner: Runner, install_dir: str, prefix_root: str) -> int:
    """Start via the exact command/env the launcher builds; output is captured so CI shows why it fails."""
    from rl_launcher.backend import Backend
    from rl_launcher.settings import Settings

    backend = Backend(Settings(prefix_root=prefix_root), _seed_core(install_dir))
    cmd, cwd, env = backend.build_launch(runner, offline=True)
    # files instead of pipes: wineserver outlives the game and would keep a pipe open
    log = os.path.join(prefix_root, f'{runner.kind}.log')
    os.makedirs(prefix_root, exist_ok=True)
    with open(log, 'w') as f:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        try:
            code = proc.wait(timeout=LAUNCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = None
    with open(log, errors='replace') as f:
        output = f.read()[-6000:]
    print(output)
    assert code is not None, f'{runner.kind} did not exit within {LAUNCH_TIMEOUT}s:\n{output}'
    return code


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv('LEGENDARY_CONFIG_PATH', str(tmp_path / 'legendary'))
    monkeypatch.setenv('WINEDEBUG', '-all')
    monkeypatch.setenv('UMU_LOG', '1')


@pytest.mark.skipif(not WINE_BIN, reason='needs Wine')
def test_wine(tmp_path):
    runner = Runner(WINE, 'Wine', WINE_BIN)
    prefix_root = str(tmp_path / 'prefix')
    _, env = runner.build('wineboot', [], prefix_root)
    subprocess.run([WINE_BIN, 'wineboot', '-i'], env={**os.environ, **env}, check=True, timeout=600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys32 = os.path.join(prefix_root, 'pfx', 'drive_c', 'windows', 'system32')
    assert _launch(runner, sys32, prefix_root) == 7


@pytest.mark.skipif(not PROTON_BIN, reason='needs PROTON_BIN')
def test_proton(tmp_path):
    prefix_root = str(tmp_path / 'prefix')
    assert _launch(Runner(PROTON, 'Proton', PROTON_BIN), _proton_cmd_dir(PROTON_BIN), prefix_root) == 7
    assert os.path.isdir(os.path.join(prefix_root, 'pfx', 'drive_c'))


@pytest.mark.skipif(not (UMU_BIN and PROTON_BIN), reason='needs UMU_BIN and PROTON_BIN')
def test_umu(tmp_path):
    runner = Runner(UMU, 'umu', UMU_BIN, {'PROTONPATH': os.path.dirname(PROTON_BIN)})
    prefix_root = str(tmp_path / 'prefix')
    assert _launch(runner, _proton_cmd_dir(PROTON_BIN), prefix_root) == 7
    assert os.path.isdir(os.path.join(prefix_root, 'pfx', 'drive_c'))
