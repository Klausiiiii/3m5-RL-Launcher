"""Entry point: ``python -m rl_launcher`` / ``3m5-rl-launcher``."""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import shlex
import sys
from logging.handlers import RotatingFileHandler

from . import __version__
from .settings import Settings, data_dir


def setup_logging(debug: bool):
    os.makedirs(data_dir(), exist_ok=True)
    handlers = [RotatingFileHandler(os.path.join(data_dir(), 'launcher.log'), maxBytes=2_000_000, backupCount=2,
                                    encoding='utf-8')]
    if sys.stderr:  # windowed PyInstaller builds have no stderr
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers,
                        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')


def restore_child_env(env=os.environ):
    """Undo PyInstaller's LD_LIBRARY_PATH so child processes (browser, kde-open, Wine) use system libs.

    The bootloader points it at the bundle and keeps the original in LD_LIBRARY_PATH_ORIG; our own
    process is unaffected by changing it, the dynamic loader only reads it at startup.
    """
    if not getattr(sys, 'frozen', False) or sys.platform != 'linux':
        return
    orig = env.get('LD_LIBRARY_PATH_ORIG')
    if orig is not None:
        env['LD_LIBRARY_PATH'] = orig
    else:
        env.pop('LD_LIBRARY_PATH', None)


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    restore_child_env()
    # windowed PyInstaller builds have no console; keep print()/argparse from crashing
    sys.stdout = sys.stdout or open(os.devnull, 'w')
    # Legendary's downloader is a multiprocessing.Process. Use "spawn" everywhere so Linux behaves like
    # Windows and we never fork a process that has Qt threads running.
    multiprocessing.set_start_method('spawn', force=True)

    parser = argparse.ArgumentParser(prog='3m5-rl-launcher', description='3m5 Rocket League Launcher')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--debug', action='store_true', help='verbose logging')
    parser.add_argument('--print-launch', action='store_true',
                        help='print the command that would start Rocket League and exit (token redacted)')
    args = parser.parse_args(argv)
    setup_logging(args.debug)

    from .backend import Backend, LauncherError, _redact
    backend = Backend(Settings.load())

    if args.print_launch:
        from .gui import custom_runner
        from .runners import detect_runners, select_runner
        s = backend.settings
        runner = custom_runner(s.custom_runner_path) if s.custom_runner_path else \
            select_runner(detect_runners(), s.runner)
        try:
            cmd, cwd, _ = backend.build_launch(runner)
        except LauncherError as e:
            print(f'Fehler: {e}', file=sys.stderr)
            return 1
        print(f'cwd: {cwd}\n{shlex.join(_redact(cmd))}')
        return 0

    from .gui import run_gui
    return run_gui(backend)


if __name__ == '__main__':
    sys.exit(main())
