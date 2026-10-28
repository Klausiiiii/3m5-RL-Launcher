"""Installers for the Linux compatibility tools the launcher can set up on its own (no root needed).

* GE-Proton - latest release from GitHub, unpacked into the launcher's data dir
* Wine Mono - the version the installed Wine expects, installed into the launcher's prefix
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Callable

import requests

from .backend import LauncherError
from .runners import own_proton_dir, wine_mono_missing

GE_PROTON_API = 'https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest'
WINE_MONO_URL = 'https://dl.winehq.org/wine/wine-mono/{v}/wine-mono-{v}-x86.msi'

# report(percent 0-100, text); cancelled() -> True aborts a download
Report = Callable[[float, str], None]


def _download(url: str, dest: str, report: Report, cancelled: Callable[[], bool], label: str) -> str:
    """Download ``url`` to ``dest`` and return its sha512 hex digest."""
    digest = hashlib.sha512()
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length') or 0)
        done = 0
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                if cancelled():
                    raise LauncherError('Abgebrochen.')
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                report(done * 100 / total if total else 0, f'{label} … {done >> 20} MiB')
    return digest.hexdigest()


def install_ge_proton(report: Report, cancelled: Callable[[], bool] = lambda: False) -> str:
    """Install the latest GE-Proton unless it is already there. Returns its name (e.g. ``GE-Proton10-3``)."""
    try:
        release = requests.get(GE_PROTON_API, timeout=30).json()
        assets = {a['name']: a['browser_download_url'] for a in release['assets']}
    except (requests.RequestException, ValueError, KeyError) as e:
        raise LauncherError(f'GE-Proton-Release nicht abrufbar ({e}).') from None
    name = release.get('tag_name', '')
    tarball = next((n for n in assets if n.endswith('.tar.gz') and 'aarch64' not in n), None)
    if not name or not tarball:
        raise LauncherError('Im GE-Proton-Release fehlt das Linux-Archiv.')

    target_root = own_proton_dir()
    if os.path.isfile(os.path.join(target_root, name, 'proton')):
        return name
    os.makedirs(target_root, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=target_root, prefix='.download-') as tmp:
        archive = os.path.join(tmp, tarball)
        try:
            digest = _download(assets[tarball], archive, report, cancelled, f'Lade {name}')
            checksum = assets.get(tarball.removesuffix('.tar.gz') + '.sha512sum')
            if checksum:
                expected = requests.get(checksum, timeout=30).text.split()[0]
                if digest != expected:
                    raise LauncherError('GE-Proton-Download beschädigt (Prüfsumme stimmt nicht).')
        except requests.RequestException as e:
            raise LauncherError(f'GE-Proton-Download fehlgeschlagen ({e}).') from None

        report(100, f'Entpacke {name} …')
        unpacked = os.path.join(tmp, 'x')
        with tarfile.open(archive) as tar:
            if hasattr(tarfile, 'data_filter'):
                tar.extractall(unpacked, filter='data')
            else:  # Python < 3.10.12 without extraction filters
                tar.extractall(unpacked)
        src = os.path.join(unpacked, name)
        if not os.path.isfile(os.path.join(src, 'proton')):
            raise LauncherError(f'Unerwarteter Inhalt im Archiv {tarball}.')
        os.replace(src, os.path.join(target_root, name))
    return name


def wine_mono_version(wine: str) -> str | None:
    """The Wine Mono version this Wine asks for, read from its appwiz.cpl (where Wine itself takes it from)."""
    prefix = os.path.dirname(os.path.dirname(os.path.realpath(wine)))  # /usr/bin/wine -> /usr
    patterns = ('lib*/wine/*-windows/appwiz.cpl', 'lib*/*/wine/*-windows/appwiz.cpl')
    pattern = re.compile(r'wine-mono-(\d+\.\d+\.\d+)-x86\.msi')
    for path in (p for pat in patterns for p in glob.glob(os.path.join(prefix, pat))):
        with open(path, 'rb') as f:
            data = f.read()
        for offset in (0, 1):  # the UTF-16 string may start on an odd byte
            if m := pattern.search(data[offset:].decode('utf-16-le', errors='ignore')):
                return m.group(1)
    return None


def install_wine_mono(wine: str, prefix_root: str, report: Report,
                      cancelled: Callable[[], bool] = lambda: False) -> str:
    """Install the matching Wine Mono into ``<prefix_root>/pfx``. Returns the installed version."""
    version = wine_mono_version(wine)
    if not version:
        raise LauncherError('Konnte nicht erkennen, welche Wine-Mono-Version dein Wine braucht. '
                            'Bitte manuell installieren (siehe README).')
    wine_prefix = os.path.join(prefix_root, 'pfx')
    os.makedirs(wine_prefix, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wine-mono-') as tmp:
        msi = os.path.join(tmp, f'wine-mono-{version}-x86.msi')
        try:
            _download(WINE_MONO_URL.format(v=version), msi, report, cancelled, f'Lade Wine Mono {version}')
        except requests.RequestException as e:
            raise LauncherError(f'Wine-Mono-Download fehlgeschlagen ({e}).') from None
        report(100, f'Installiere Wine Mono {version} …')
        env = {**os.environ, 'WINEPREFIX': wine_prefix, 'WINEDEBUG': '-all'}
        subprocess.run([wine, 'msiexec', '/i', msi, '/qn'], env=env, check=False, timeout=600)
        # msiexec returns before wineserver has flushed everything to disk
        if wineserver := shutil.which('wineserver', path=os.path.dirname(wine)):
            subprocess.run([wineserver, '-w'], env=env, check=False, timeout=120)
    if wine_mono_missing(prefix_root):
        raise LauncherError('Wine Mono wurde nicht installiert. Details im Log.')
    return version
