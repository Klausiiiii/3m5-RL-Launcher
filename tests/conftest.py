import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Never touch the real user config."""
    for var in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'APPDATA', 'LOCALAPPDATA'):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'home'))
    return tmp_path


class FakeLgd:
    def __init__(self, installed=None):
        self.userdata = {'displayName': 'Klaus', 'account_id': 'abc'}
        self.installed = installed
        self.invalidated = False

    def invalidate_userdata(self):
        self.invalidated = True
        self.userdata = None

    def lock_installed(self):
        return True

    def get_tmp_path(self):
        return '/tmp'


class FakeCore:
    """Minimal stand-in for LegendaryCore."""

    def __init__(self, logged_in=True, owned=True, installed=None, latest='1.2', install_dir='/games/rl'):
        self.lgd = FakeLgd(installed)
        self._logged_in = logged_in
        self.owned = owned
        self.latest = latest
        self.install_dir = install_dir
        self.codes = []

    def login(self):
        if not self._logged_in:
            raise ValueError('no creds')
        return True

    def auth_code(self, code):
        self.codes.append(code)
        self._logged_in = code == 'good'
        return self._logged_in

    def get_game(self, app_name, update_meta=False):
        if not self.owned or app_name != 'Sugar':
            return None
        return SimpleNamespace(app_name='Sugar', app_title='Rocket League', metadata={},
                               app_version=lambda platform='Windows': self.latest)

    def get_game_list(self, update_assets=False):
        return []

    def get_installed_game(self, app_name):
        return self.lgd.installed

    def get_launch_parameters(self, **kw):
        self.launch_kwargs = kw
        return SimpleNamespace(
            game_directory=self.install_dir, game_executable='Binaries/Win64/RocketLeague.exe',
            working_directory=self.install_dir + '/Binaries/Win64', environment={'FOO': 'bar'},
            game_parameters=['-nomovie'], user_parameters=list(kw.get('extra_args') or []),
            egl_parameters=['-AUTH_PASSWORD=secret', '-epicapp=Sugar'])


@pytest.fixture
def installed_game(tmp_path):
    path = tmp_path / 'rl'
    path.mkdir()
    return SimpleNamespace(app_name='Sugar', version='1.1', install_path=str(path), needs_verification=False,
                           install_tags=[], platform='Windows')
