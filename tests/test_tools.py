import hashlib
import io
import os
import tarfile

import pytest

from rl_launcher import tools
from rl_launcher.backend import LauncherError
from rl_launcher.runners import find_proton_builds, own_proton_dir


class FakeResponse:
    def __init__(self, body: bytes = b'', data=None):
        self.body, self.data = body, data
        self.headers = {'content-length': str(len(body))}
        self.text = body.decode(errors='ignore')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body

    def json(self):
        return self.data


def ge_proton_tarball(name: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        script = b'#!/bin/sh\n'
        info = tarfile.TarInfo(f'{name}/proton')
        info.size, info.mode = len(script), 0o755
        tar.addfile(info, io.BytesIO(script))
    return buf.getvalue()


def fake_github(monkeypatch, name='GE-Proton10-3', checksum=None):
    body = ge_proton_tarball(name)
    checksum = checksum or hashlib.sha512(body).hexdigest()
    release = {'tag_name': name, 'assets': [
        {'name': f'{name}.tar.gz', 'browser_download_url': 'https://x/tar'},
        {'name': f'{name}.sha512sum', 'browser_download_url': 'https://x/sum'},
    ]}
    calls = []

    def get(url, **kw):
        calls.append(url)
        if url == tools.GE_PROTON_API:
            return FakeResponse(data=release)
        return FakeResponse(f'{checksum}  {name}.tar.gz\n'.encode() if url.endswith('sum') else body)
    monkeypatch.setattr(tools.requests, 'get', get)
    return calls


@pytest.mark.skipif(os.name == 'nt', reason='Linux only')
def test_install_ge_proton(monkeypatch):
    calls = fake_github(monkeypatch)
    assert tools.install_ge_proton(lambda *a: None) == 'GE-Proton10-3'
    assert os.access(os.path.join(own_proton_dir(), 'GE-Proton10-3', 'proton'), os.X_OK)
    assert [r.name for r in find_proton_builds()] == ['GE-Proton10-3']
    assert os.listdir(own_proton_dir()) == ['GE-Proton10-3']  # no leftover download dir

    calls.clear()
    assert tools.install_ge_proton(lambda *a: None) == 'GE-Proton10-3'
    assert calls == [tools.GE_PROTON_API]  # already installed: nothing downloaded


def test_install_ge_proton_bad_checksum(monkeypatch):
    fake_github(monkeypatch, checksum='0' * 128)
    with pytest.raises(LauncherError, match='Prüfsumme'):
        tools.install_ge_proton(lambda *a: None)
    assert not os.path.exists(os.path.join(own_proton_dir(), 'GE-Proton10-3'))


def test_wine_mono_version(tmp_path):
    wine = tmp_path / 'usr' / 'bin' / 'wine'
    wine.parent.mkdir(parents=True)
    wine.write_text('')
    assert tools.wine_mono_version(str(wine)) is None

    cpl = tmp_path / 'usr' / 'lib' / 'x86_64-linux-gnu' / 'wine' / 'x86_64-windows' / 'appwiz.cpl'
    cpl.parent.mkdir(parents=True)
    cpl.write_bytes(b'MZ\x00' + 'wine-mono-9.4.0-x86.msi'.encode('utf-16-le'))  # odd offset on purpose
    assert tools.wine_mono_version(str(wine)) == '9.4.0'


def test_install_wine_mono(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'wine_mono_version', lambda wine: '9.4.0')
    monkeypatch.setattr(tools, '_download', lambda url, dest, *a: open(dest, 'wb').close())
    runs = []

    def run(cmd, env, **kw):
        runs.append((cmd, env['WINEPREFIX']))
        os.makedirs(os.path.join(env['WINEPREFIX'], 'drive_c', 'windows', 'mono'), exist_ok=True)
    monkeypatch.setattr(tools.subprocess, 'run', run)

    assert tools.install_wine_mono('/usr/bin/wine', str(tmp_path), lambda *a: None) == '9.4.0'
    cmd, prefix = runs[0]
    assert cmd[:3] == ['/usr/bin/wine', 'msiexec', '/i'] and cmd[3].endswith('wine-mono-9.4.0-x86.msi')
    assert prefix == str(tmp_path / 'pfx')


def test_install_wine_mono_unknown_version(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'wine_mono_version', lambda wine: None)
    with pytest.raises(LauncherError, match='manuell'):
        tools.install_wine_mono('/usr/bin/wine', str(tmp_path), lambda *a: None)
