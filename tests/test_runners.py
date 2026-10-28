import os

import pytest

from rl_launcher import runners
from rl_launcher.runners import Runner, find_proton_builds, runner_id, select_runner


def test_native_command(tmp_path):
    cmd, env = Runner('native', 'n').build('C:/rl.exe', ['-a'], str(tmp_path))
    assert cmd == ['C:/rl.exe', '-a'] and env == {}


def test_umu_command(tmp_path):
    cmd, env = Runner('umu', 'u', '/usr/bin/umu-run').build('/g/rl.exe', ['-a'], str(tmp_path))
    assert cmd == ['/usr/bin/umu-run', '/g/rl.exe', '-a']
    assert env['GAMEID'] == 'umu-252950' and env['STORE'] == 'egs'
    assert env['PROTONPATH'] == 'GE-Proton'
    assert env['WINEPREFIX'] == os.path.join(str(tmp_path), 'pfx')


def test_umu_keeps_explicit_proton(tmp_path):
    _, env = Runner('umu', 'u', 'umu-run', {'PROTONPATH': '/p/GE'}).build('x.exe', [], str(tmp_path))
    assert env['PROTONPATH'] == '/p/GE'


def test_proton_command(tmp_path):
    cmd, env = Runner('proton', 'p', '/p/proton').build('/g/rl.exe', [], str(tmp_path))
    assert cmd == ['/p/proton', 'run', '/g/rl.exe']
    assert env['STEAM_COMPAT_DATA_PATH'] == str(tmp_path)
    assert env['STEAM_COMPAT_CLIENT_INSTALL_PATH']


@pytest.mark.skipif(os.name == 'nt', reason='Linux only')
def test_detect_proton(isolated_dirs):
    home = isolated_dirs / 'home'
    for name in ('GE-Proton9-1', 'GE-Proton10-3'):
        d = home / '.steam' / 'root' / 'compatibilitytools.d' / name
        d.mkdir(parents=True)
        (d / 'proton').write_text('')
    valve = home / '.local' / 'share' / 'Steam' / 'steamapps' / 'common' / 'Proton 9.0'
    valve.mkdir(parents=True)
    (valve / 'proton').write_text('')

    found = [r.name for r in find_proton_builds()]
    assert found == ['GE-Proton9-1', 'GE-Proton10-3', 'Proton 9.0']


@pytest.mark.skipif(os.name == 'nt', reason='Linux only')
def test_detect_runners_prefers_umu(monkeypatch):
    monkeypatch.setattr(runners.shutil, 'which', lambda n: f'/usr/bin/{n}')
    kinds = [r.kind for r in runners.detect_runners()]
    assert kinds[0] == 'umu' and kinds[-1] == 'wine'


def test_select_runner():
    a, b = Runner('umu', 'a', 'umu-run'), Runner('wine', 'b', '/usr/bin/wine')
    assert select_runner([a, b], runner_id(b)) is b
    assert select_runner([a, b], 'gone') is a
    assert select_runner([], '') is None


def test_wine_mono_missing(tmp_path):
    assert runners.wine_mono_missing(str(tmp_path))
    (tmp_path / 'pfx' / 'drive_c' / 'windows' / 'mono').mkdir(parents=True)
    assert not runners.wine_mono_missing(str(tmp_path))
