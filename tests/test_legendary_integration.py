"""Runs our backend against a real LegendaryCore (offline, with seeded local data)."""
import os
import sys

import pytest
from legendary.core import LegendaryCore
from legendary.models.game import Game, GameAsset, InstalledGame

from rl_launcher.backend import Backend
from rl_launcher.runners import Runner
from rl_launcher.settings import Settings


@pytest.fixture
def core(tmp_path, monkeypatch):
    monkeypatch.setenv('LEGENDARY_CONFIG_PATH', str(tmp_path / 'legendary'))
    c = LegendaryCore()
    with c.lgd.userdata_lock as lock:
        lock.data = {'displayName': 'Klaus', 'account_id': 'acc123'}
    asset = GameAsset(app_name='Sugar', asset_id='', build_version='2.51', catalog_item_id='cat',
                      label_name='Live', namespace='sugar', metadata={})
    c.lgd.set_game_meta('Sugar', Game(app_name='Sugar', app_title='Rocket League',
                                      asset_infos={'Windows': asset},
                                      metadata={'namespace': 'sugar', 'id': 'cat'}))
    return c


def test_offline_launch_with_real_core(core, tmp_path):
    install = tmp_path / 'rocketleague'
    (install / 'Binaries' / 'Win64').mkdir(parents=True)
    (install / 'Binaries' / 'Win64' / 'RocketLeague.exe').write_text('')
    core.lgd.set_installed_game('Sugar', InstalledGame(
        app_name='Sugar', install_path=str(install), title='Rocket League', version='2.51',
        executable='Binaries/Win64/RocketLeague.exe', can_run_offline=True))

    backend = Backend(Settings(prefix_root=str(tmp_path / 'pfx'), launch_args='-nomovie'), core)
    state = backend.refresh_state(online=False)
    assert state.installed and state.owned and not state.update_available

    runner = Runner('native', 'n') if sys.platform == 'win32' else Runner('wine', 'w', '/usr/bin/wine')
    cmd, cwd, env = backend.build_launch(runner, offline=True)
    exe = os.path.join(str(install), 'Binaries/Win64/RocketLeague.exe')
    assert exe in cmd
    assert cwd == os.path.dirname(exe)
    assert '-epicapp=Sugar' in cmd and '-epicusername=Klaus' in cmd and '-nomovie' in cmd
    assert '-epicuserid=acc123' in cmd and '-epicsandboxid=sugar' in cmd
    if sys.platform != 'win32':
        assert cmd[0] == '/usr/bin/wine' and 'WINEPREFIX' in env


def test_dlmanager_starts_with_spawn(tmp_path):
    """We force the 'spawn' start method; the DLManager process object must survive pickling."""
    import multiprocessing

    from legendary.downloader.mp.manager import DLManager
    ctx = multiprocessing.get_context('spawn')
    dlm = DLManager(str(tmp_path), 'https://example.invalid', {}, status_q=ctx.Queue())
    old = multiprocessing.get_start_method(allow_none=True)
    multiprocessing.set_start_method('spawn', force=True)
    try:
        dlm.start()  # pickling errors would raise here, in the parent
        dlm.join(60)
    finally:
        multiprocessing.set_start_method(old, force=True)
    # child got unpickled and ran: it fails only because no analysis was run
    assert dlm.exitcode == 1
