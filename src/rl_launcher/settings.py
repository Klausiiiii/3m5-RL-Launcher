"""Persistent launcher settings (separate from Legendary's own config)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields

APP_DIR_NAME = '3m5-rl-launcher'


def config_dir() -> str:
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, APP_DIR_NAME)


def data_dir() -> str:
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, APP_DIR_NAME)


def default_install_base() -> str:
    # same default as Legendary; writable without admin rights on Windows
    return os.path.expanduser('~/Games')


@dataclass
class Settings:
    install_base: str = ''
    # id of the selected runner (see runners.runner_id), empty = best detected
    runner: str = ''
    # path to a custom wine/proton/umu-run binary, overrides ``runner``
    custom_runner_path: str = ''
    prefix_root: str = ''
    launch_args: str = ''
    skip_update_check: bool = False

    def __post_init__(self):
        self.install_base = self.install_base or default_install_base()
        self.prefix_root = self.prefix_root or os.path.join(data_dir(), 'prefix')

    @classmethod
    def path(cls) -> str:
        return os.path.join(config_dir(), 'settings.json')

    @classmethod
    def load(cls) -> Settings:
        try:
            with open(cls.path(), encoding='utf-8') as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self):
        os.makedirs(config_dir(), exist_ok=True)
        tmp = self.path() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, self.path())
