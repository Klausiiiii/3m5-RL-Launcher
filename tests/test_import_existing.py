"""Importing an existing (Epic Games Launcher) install with a real LegendaryCore, then verifying it."""
import hashlib
import io
import json
import os

import pytest
from legendary.core import LegendaryCore
from legendary.models.game import Game, GameAsset
from legendary.models.manifest import CDL, FML, CustomFields, FileManifest, Manifest, ManifestMeta

from rl_launcher.backend import Backend, LauncherError, find_rl_folder
from rl_launcher.settings import Settings

FILES = {
    'Binaries/Win64/RocketLeague.exe': b'MZ fake exe',
    'TAGame/CookedPCConsole/Park_P.upk': b'map data',
    'TAGame/Config/DefaultInput.ini': b'[input]',
}
GUID = '0123456789ABCDEF0123456789ABCDEF'


def make_egl_install(base) -> str:
    """Create .../Epic Games/rocketleague the way the Epic Games Launcher leaves it."""
    game_dir = os.path.join(base, 'Epic Games', 'rocketleague')
    for name, data in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(game_dir, name)), exist_ok=True)
        with open(os.path.join(game_dir, name), 'wb') as f:
            f.write(data)

    m = Manifest()
    m.meta = ManifestMeta()
    m.meta.app_name, m.meta.build_version, m.meta.launch_exe = 'Sugar', '2.51', 'Binaries/Win64/RocketLeague.exe'
    m.chunk_data_list, m.file_manifest_list, m.custom_fields = CDL(), FML(), CustomFields()
    for name, data in FILES.items():
        fm = FileManifest()
        fm.filename, fm.hash = name, hashlib.sha1(data).digest()
        m.file_manifest_list.elements.append(fm)
    buf = io.BytesIO()
    m.write(buf)

    egstore = os.path.join(game_dir, '.egstore')
    os.makedirs(egstore)
    with open(os.path.join(egstore, f'{GUID}.manifest'), 'wb') as f:
        f.write(buf.getvalue())
    with open(os.path.join(egstore, f'{GUID}.mancpn'), 'w') as f:
        json.dump({'FormatVersion': 0, 'AppName': 'Sugar', 'CatalogItemId': 'c', 'CatalogNamespace': 'sugar'}, f)
    return game_dir


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv('LEGENDARY_CONFIG_PATH', str(tmp_path / 'legendary'))
    core = LegendaryCore()
    asset = GameAsset(app_name='Sugar', asset_id='', build_version='2.51', catalog_item_id='c', label_name='Live',
                      namespace='sugar', metadata={})
    core.lgd.set_game_meta('Sugar', Game(app_name='Sugar', app_title='Rocket League', asset_infos={'Windows': asset},
                                         metadata={'namespace': 'sugar', 'id': 'c'}))
    b = Backend(Settings(install_base=str(tmp_path / 'Epic Games')), core)
    # no network in tests: pretend we are logged in and use the seeded metadata
    monkeypatch.setattr(b, 'try_login', lambda: True)
    monkeypatch.setattr(b, '_find_game', lambda update: core.lgd.get_game_meta('Sugar'))
    return b


def test_find_rl_folder_accepts_parent_game_and_sub_folder(tmp_path):
    game_dir = make_egl_install(tmp_path)
    for picked in (game_dir, os.path.dirname(game_dir), os.path.join(game_dir, 'Binaries', 'Win64')):
        assert find_rl_folder(picked) == game_dir
    assert find_rl_folder(str(tmp_path)) is None
    assert find_rl_folder('') is None


def test_finds_install_automatically(backend, tmp_path):
    game_dir = make_egl_install(tmp_path)
    assert game_dir in backend.find_existing_installs()


def test_import_then_verify_clean(backend, tmp_path):
    game_dir = make_egl_install(tmp_path)
    assert backend.import_install(os.path.dirname(game_dir)) == game_dir  # picked "Epic Games"

    state = backend.refresh_state(online=False)
    assert state.installed and state.install_path == game_dir and state.needs_verification
    assert state.installed_version == '2.51'  # taken from the EGL manifest, nothing downloaded

    progress = []
    assert backend.verify(lambda p, t: progress.append(p)) == (0, 0)
    assert progress[-1] == 100
    assert not backend.refresh_state(online=False).needs_verification


def test_verify_detects_broken_and_missing_files(backend, tmp_path):
    game_dir = make_egl_install(tmp_path)
    backend.import_install(game_dir)
    with open(os.path.join(game_dir, 'TAGame/CookedPCConsole/Park_P.upk'), 'wb') as f:
        f.write(b'corrupted')
    os.remove(os.path.join(game_dir, 'TAGame/Config/DefaultInput.ini'))

    assert backend.verify(lambda *a: None) == (1, 1)
    assert backend.refresh_state(online=False).needs_verification
    # Legendary's repair file lists what can be kept, so only broken/missing files get downloaded
    with open(os.path.join(backend.core.lgd.get_tmp_path(), 'Sugar.repair')) as f:
        repair = f.read()
    assert 'Binaries/Win64/RocketLeague.exe' in repair


def test_verify_can_be_cancelled(backend, tmp_path):
    backend.import_install(make_egl_install(tmp_path))
    with pytest.raises(LauncherError, match='abgebrochen'):
        backend.verify(lambda *a: None, cancelled=lambda: True)


def test_import_rejects_wrong_folder(backend, tmp_path):
    with pytest.raises(LauncherError, match='kein Rocket League'):
        backend.import_install(str(tmp_path))
