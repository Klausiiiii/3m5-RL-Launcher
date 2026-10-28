import pytest
from conftest import FakeCore

from rl_launcher.backend import Backend, LauncherError, _redact, parse_auth_code
from rl_launcher.runners import Runner
from rl_launcher.settings import Settings


@pytest.mark.parametrize('text,expected', [
    ('abc123', 'abc123'),
    ('  "abc123"  ', 'abc123'),
    ('{"redirectUrl":"x","authorizationCode":"abc123","sid":null}', 'abc123'),
    ('https://localhost/launcher/authorized?code=abc123', 'abc123'),
])
def test_parse_auth_code(text, expected):
    assert parse_auth_code(text) == expected


@pytest.mark.parametrize('text', ['', '{"authorizationCode": null}', '{broken', 'https://x/?foo=1'])
def test_parse_auth_code_invalid(text):
    with pytest.raises(LauncherError):
        parse_auth_code(text)


def test_login_with_code():
    core = FakeCore(logged_in=False)
    b = Backend(Settings(), core)
    assert b.try_login() is False
    with pytest.raises(LauncherError):
        b.login_with_code('bad')
    assert b.login_with_code('{"authorizationCode": "good"}') == 'Klaus'
    assert core.codes == ['bad', 'good']


def test_state_not_installed():
    s = Backend(Settings(), FakeCore()).refresh_state()
    assert s.logged_in and s.owned and not s.installed
    assert s.user == 'Klaus' and s.latest_version == '1.2'
    assert not s.update_available


def test_state_update_available(installed_game):
    s = Backend(Settings(), FakeCore(installed=installed_game)).refresh_state()
    assert s.installed and s.installed_version == '1.1'
    assert s.update_available


def test_state_not_owned():
    s = Backend(Settings(), FakeCore(owned=False)).refresh_state()
    assert not s.owned


def test_install_requires_ownership():
    with pytest.raises(LauncherError, match='Store'):
        Backend(Settings(), FakeCore(owned=False))._require_game()


def test_build_launch_wine(installed_game, tmp_path):
    core = FakeCore(installed=installed_game, install_dir=installed_game.install_path)
    settings = Settings(prefix_root=str(tmp_path / 'pfxroot'), launch_args='-high "-foo bar"')
    cmd, cwd, env = Backend(settings, core).build_launch(Runner('wine', 'Wine', '/usr/bin/wine'))
    assert cmd[0] == '/usr/bin/wine'
    assert cmd[1].endswith('Binaries/Win64/RocketLeague.exe')
    assert cmd[2:] == ['-nomovie', '-high', '-foo bar', '-AUTH_PASSWORD=secret', '-epicapp=Sugar']
    assert env['WINEPREFIX'] == str(tmp_path / 'pfxroot' / 'pfx')
    assert env['FOO'] == 'bar'
    assert core.launch_kwargs['disable_wine'] is True
    assert '-AUTH_PASSWORD=***' in _redact(cmd)


def test_build_launch_errors(installed_game):
    with pytest.raises(LauncherError, match='nicht installiert'):
        Backend(Settings(), FakeCore()).build_launch(Runner('native', 'n'))
    with pytest.raises(LauncherError, match='Wine'):
        Backend(Settings(), FakeCore(installed=installed_game)).build_launch(None)
