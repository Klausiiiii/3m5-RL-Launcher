"""Detection and command building for the program that actually runs the game.

On Windows Rocket League is started directly. On Linux it needs a Windows
compatibility layer; we support (in order of preference):

* ``umu``    - umu-launcher (``umu-run``), runs Proton outside of Steam properly
* ``proton`` - a Proton build (GE-Proton or Valve Proton) called directly
* ``wine``   - plain system Wine
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
from dataclasses import dataclass, field

# Rocket League's Steam app id - used by umu/protonfixes to apply game specific fixes.
RL_STEAM_APP_ID = '252950'

NATIVE = 'native'
UMU = 'umu'
PROTON = 'proton'
WINE = 'wine'


@dataclass
class Runner:
    kind: str
    name: str
    path: str = ''
    # extra environment the runner always needs
    env: dict = field(default_factory=dict)

    def build(self, exe_path: str, args: list[str], prefix_root: str) -> tuple[list[str], dict]:
        """Return (command, environment overrides) to start ``exe_path`` with ``args``.

        ``prefix_root`` is a directory owned by the launcher; the actual Wine prefix lives in
        ``<prefix_root>/pfx`` which is the layout Proton uses, so all runners share one prefix.
        """
        env = dict(self.env)
        if self.kind == NATIVE:
            return [exe_path, *args], env

        wine_prefix = os.path.join(prefix_root, 'pfx')
        os.makedirs(wine_prefix, exist_ok=True)

        if self.kind == UMU:
            env.setdefault('PROTONPATH', 'GE-Proton')
            env.update(WINEPREFIX=wine_prefix, GAMEID=f'umu-{RL_STEAM_APP_ID}', STORE='egs')
            return [self.path, exe_path, *args], env

        if self.kind == PROTON:
            env.update(
                STEAM_COMPAT_DATA_PATH=prefix_root,
                STEAM_COMPAT_CLIENT_INSTALL_PATH=find_steam_root() or prefix_root,
                SteamAppId=RL_STEAM_APP_ID,
                SteamGameId=RL_STEAM_APP_ID,
            )
            return [self.path, 'run', exe_path, *args], env

        if self.kind == WINE:
            env['WINEPREFIX'] = wine_prefix
            return [self.path, exe_path, *args], env

        raise ValueError(f'Unknown runner kind: {self.kind}')


def _steam_roots() -> list[str]:
    home = os.path.expanduser('~')
    return [
        os.path.join(home, '.steam', 'root'),
        os.path.join(home, '.steam', 'steam'),
        os.path.join(home, '.local', 'share', 'Steam'),
        os.path.join(home, '.var', 'app', 'com.valvesoftware.Steam', 'data', 'Steam'),
    ]


def find_steam_root() -> str | None:
    for root in _steam_roots():
        if os.path.isdir(root):
            return os.path.realpath(root)
    return None


def find_proton_builds() -> list[Runner]:
    """Find Proton builds; GE-Proton (compatibilitytools.d) first, newest name first."""
    seen = set()
    custom, valve = [], []
    for root in _steam_roots():
        for script in glob.glob(os.path.join(root, 'compatibilitytools.d', '*', 'proton')):
            custom.append(script)
        for script in glob.glob(os.path.join(root, 'steamapps', 'common', 'Proton*', 'proton')):
            valve.append(script)

    runners = []
    for script in sorted(custom, reverse=True) + sorted(valve, reverse=True):
        real = os.path.realpath(script)
        if real in seen:
            continue
        seen.add(real)
        name = os.path.basename(os.path.dirname(script))
        runners.append(Runner(PROTON, name, script))
    return runners


def detect_runners() -> list[Runner]:
    """All usable runners on this machine, best first."""
    if sys.platform == 'win32':
        return [Runner(NATIVE, 'Windows (nativ)')]

    runners = []
    protons = find_proton_builds()
    if umu := shutil.which('umu-run'):
        runners.append(Runner(UMU, 'umu-launcher (GE-Proton, automatisch)', umu))
        # umu can also use any locally installed Proton build
        for p in protons:
            runners.append(Runner(UMU, f'umu-launcher + {p.name}', umu, {'PROTONPATH': os.path.dirname(p.path)}))
    runners.extend(protons)
    if wine := shutil.which('wine'):
        runners.append(Runner(WINE, 'System-Wine', wine))
    return runners


def runner_id(runner: Runner) -> str:
    """Stable identifier used to remember the selected runner in the settings."""
    return f'{runner.kind}:{runner.env.get("PROTONPATH") or runner.path}'


def select_runner(runners: list[Runner], wanted_id: str | None) -> Runner | None:
    if wanted_id:
        for r in runners:
            if runner_id(r) == wanted_id:
                return r
    return runners[0] if runners else None
