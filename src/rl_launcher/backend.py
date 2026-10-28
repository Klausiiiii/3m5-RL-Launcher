"""Rocket League specific wrapper around Legendary's ``LegendaryCore``.

Everything in here is blocking and GUI agnostic; the GUI runs it in worker threads.
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import os
import queue
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urlparse

from legendary.core import LegendaryCore
from legendary.lfs.utils import validate_files
from legendary.models.downloading import AnalysisResult, UIUpdate
from legendary.models.exceptions import InvalidCredentialsError
from legendary.models.game import Game, InstalledGame, VerifyResult

from .runners import Runner
from .settings import Settings

log = logging.getLogger('rl_launcher.backend')

RL_APP_NAME = 'Sugar'  # Epic's internal app name for Rocket League
RL_TITLE = 'Rocket League'
RL_FOLDER = 'rocketleague'  # folder name Epic uses for the install
RL_EXE = 'Binaries/Win64/RocketLeague.exe'
LOGIN_URL = 'https://legendary.gl/epiclogin'
STORE_URL = 'https://store.epicgames.com/p/rocket-league'

ProgressCallback = Callable[[float, str], None]


class LauncherError(Exception):
    """Error with a message meant for the user."""


@dataclass
class GameState:
    logged_in: bool = False
    user: str = ''
    owned: bool = False
    installed: bool = False
    installed_version: str = ''
    latest_version: str = ''
    install_path: str = ''
    needs_verification: bool = False

    @property
    def update_available(self) -> bool:
        return bool(self.installed and self.latest_version and self.installed_version != self.latest_version)


@dataclass
class InstallPlan:
    game: Game
    igame: InstalledGame
    analysis: AnalysisResult
    dlm: object
    status_queue: object
    warnings: list[str] = field(default_factory=list)
    repair_file: str = ''

    @property
    def download_size(self) -> int:
        return self.analysis.dl_size

    @property
    def install_size(self) -> int:
        return self.analysis.install_size


def parse_auth_code(text: str) -> str:
    """Extract the authorization code from whatever the user pasted.

    Accepts the raw code, the JSON shown by Epic (``{"authorizationCode": "..."}`` or, in newer
    responses, only ``{"redirectUrl": "...?code=..."}``) or a URL containing ``code=``.
    """
    text = text.strip().strip('"\'')
    if not text:
        raise LauncherError('Kein Code eingegeben.')
    if text.startswith('{'):
        try:
            data = json.loads(text)
        except ValueError:
            raise LauncherError('Eingefügtes JSON ist ungültig.') from None
        code = data.get('authorizationCode') or _code_from_url(data.get('redirectUrl') or '')
        if not code:
            raise LauncherError('Im JSON fehlt "authorizationCode" – bist du eingeloggt?')
        return code
    if text.startswith('http'):
        code = _code_from_url(text)
        if not code:
            raise LauncherError('Die URL enthält keinen Code.')
        return code
    return text


def _code_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query).get('code', [''])[0]


class Backend:
    def __init__(self, settings: Settings, core: LegendaryCore | None = None):
        self.settings = settings
        self.core = core or LegendaryCore()
        self.app_name = RL_APP_NAME

    # ------------------------------------------------------------------ auth
    def try_login(self) -> bool:
        """Use stored credentials. Returns False if there are none / they expired."""
        try:
            return self.core.login()
        except ValueError:  # no stored credentials
            return False
        except InvalidCredentialsError:
            self.core.lgd.invalidate_userdata()
            return False

    def login_with_code(self, pasted: str) -> str:
        code = parse_auth_code(pasted)
        if not self.core.auth_code(code):
            raise LauncherError('Login fehlgeschlagen. Der Code ist nur kurz gültig – hol dir einen neuen.')
        return self.user_name()

    def import_egl_login(self) -> str:
        try:
            ok = self.core.auth_import()
        except Exception as e:
            raise LauncherError(f'Keine Epic-Launcher-Anmeldung gefunden ({e}).') from None
        if not ok:
            raise LauncherError('Die Anmeldung aus dem Epic Games Launcher ist abgelaufen.')
        return self.user_name()

    def logout(self):
        self.core.lgd.invalidate_userdata()

    def user_name(self) -> str:
        data = self.core.lgd.userdata or {}
        return data.get('displayName', '')

    # ----------------------------------------------------------------- state
    def _find_game(self, update: bool) -> Game | None:
        game = self.core.get_game(self.app_name, update_meta=update)
        if game:
            return game
        # Fall back to a title search in case Epic ever renames the app
        for g in self.core.get_game_list(update_assets=False):
            if g.app_title.lower() == RL_TITLE.lower():
                self.app_name = g.app_name
                return g
        return None

    def refresh_state(self, online: bool = True) -> GameState:
        state = GameState()
        if online:
            state.logged_in = self.try_login()
            state.user = self.user_name() if state.logged_in else ''
        game = self._find_game(update=online and state.logged_in)
        state.owned = game is not None
        if game:
            state.latest_version = game.app_version('Windows') or ''

        igame = self.core.get_installed_game(self.app_name)
        if igame:
            state.installed = True
            state.installed_version = igame.version
            state.install_path = igame.install_path
            state.needs_verification = igame.needs_verification
        return state

    # --------------------------------------------------------------- install
    def _require_game(self) -> Game:
        if not self.try_login():
            raise LauncherError('Nicht eingeloggt.')
        game = self._find_game(update=True)
        if not game:
            raise LauncherError(f'{RL_TITLE} ist nicht in deiner Epic-Bibliothek. '
                                f'Hol es dir kostenlos im Epic Store: {STORE_URL}')
        return game

    def _lock(self):
        if not self.core.lgd.lock_installed():
            raise LauncherError('Eine andere Legendary-Instanz installiert gerade etwas. Bitte schließen.')

    def prepare_install(self, repair: bool = False) -> InstallPlan | None:
        """Prepare install/update/repair. Returns None if there is nothing to download."""
        self._lock()
        game = self._require_game()
        repair_file = ''
        if repair:
            repair_file = os.path.join(self.core.lgd.get_tmp_path(), f'{self.app_name}.repair')

        status_q = multiprocessing.Queue()
        dlm, analysis, igame = self.core.prepare_download(
            game=game,
            base_path=self.settings.install_base,
            status_q=status_q,
            repair=repair,
            repair_use_latest=repair,
        )
        if not analysis.dl_size:
            self._finalize(game, igame, repair_file)
            return None

        res = self.core.check_installation_conditions(
            analysis=analysis, install=igame, game=game, updating=self.core.is_installed(self.app_name))
        if res.failures:
            raise LauncherError('Installation nicht möglich:\n' + '\n'.join(sorted(res.failures)))
        return InstallPlan(game, igame, analysis, dlm, status_q, sorted(res.warnings or []), repair_file)

    def run_install(self, plan: InstallPlan, progress: ProgressCallback, cancelled: Callable[[], bool]) -> bool:
        """Run the download process. Returns True when finished, False if cancelled."""
        dlm = plan.dlm
        dlm.start()
        was_cancelled = False

        def report(update: UIUpdate):
            speed = update.download_speed / 1024 / 1024
            progress(update.progress, f'{update.progress:.1f} %  ·  {speed:.1f} MiB/s')

        while dlm.is_alive():
            if cancelled() and not was_cancelled:
                was_cancelled = True
                self._stop_dlm(dlm)
            try:
                report(plan.status_queue.get(timeout=0.5))
            except queue.Empty:
                continue
        # drain what was sent right before exiting (an unread mp.Queue can also block the child's exit)
        while True:
            try:
                report(plan.status_queue.get_nowait())
            except queue.Empty:
                break
        dlm.join()

        if was_cancelled:
            return False
        if dlm.exitcode != 0:
            raise LauncherError(f'Download abgebrochen (Exit-Code {dlm.exitcode}). '
                                'Erneut starten setzt den Download fort.')
        self._finalize(plan.game, plan.igame, plan.repair_file)
        return True

    @staticmethod
    def _stop_dlm(dlm):
        # DLManager cleans up its workers on KeyboardInterrupt; on Windows we can only terminate.
        if sys.platform == 'win32':
            dlm.terminate()
        else:
            os.kill(dlm.pid, signal.SIGINT)

    def _finalize(self, game: Game, igame: InstalledGame, repair_file: str):
        old = self.core.get_installed_game(game.app_name)
        if old and old.install_tags != igame.install_tags:
            old.install_tags = igame.install_tags
            self.core.uninstall_tag(old)
        igame.needs_verification = False
        postinstall = self.core.install_game(igame)
        if postinstall:
            self._handle_prereqs(igame, postinstall)
        if repair_file and os.path.exists(repair_file):
            os.remove(repair_file)

    def _handle_prereqs(self, igame: InstalledGame, prereq: dict):
        # On Linux Proton/Wine ship the runtimes, so we only mark them as installed.
        if sys.platform == 'win32':
            req_dir, req_exe = os.path.split(prereq['path'])
            work_dir = os.path.join(igame.install_path, req_dir)
            try:
                subprocess.Popen([os.path.join(work_dir, req_exe), prereq.get('args', '')],
                                 cwd=work_dir, shell=True).wait()
            except OSError as e:
                log.warning(f'Prerequisite installer failed: {e!r}')
        self.core.prereq_installed(igame.app_name)

    def verify(self, progress: ProgressCallback, cancelled: Callable[[], bool] = lambda: False) -> tuple[int, int]:
        """Check all files and write Legendary's repair file. Returns (corrupted, missing)."""
        igame = self.core.get_installed_game(self.app_name)
        if not igame:
            raise LauncherError(f'{RL_TITLE} ist nicht installiert.')
        if not os.path.exists(igame.install_path):
            raise LauncherError(f'Installationsordner fehlt: {igame.install_path}')

        manifest_data, _ = self.core.get_installed_manifest(self.app_name)
        secrets = {}
        if manifest_data is None:
            game = self._require_game()
            manifest_data, _, _, secrets = self.core.get_cdn_manifest(game, igame.platform)
        manifest = self.core.load_manifest(manifest_data)
        if not manifest.decrypt(secrets):
            raise LauncherError('Manifest konnte nicht entschlüsselt werden.')

        files = [(f.filename, f.sha_hash.hex()) for f in manifest.file_manifest_list.elements
                 if not f.install_tags or any(t in igame.install_tags for t in f.install_tags)]
        total = sum(manifest.file_manifest_list.get_file_by_path(name).file_size for name, _ in files) or 1
        done = 0
        bad = missing = 0
        repair = []
        last = 0.0
        for result, path, result_hash, read in validate_files(igame.install_path, files, case_insensitive=True):
            if cancelled():
                raise LauncherError('Prüfung abgebrochen. „PRÜFEN“ startet sie erneut.')
            done += read
            if result in (VerifyResult.HASH_MATCH, VerifyResult.HASH_MISMATCH):
                repair.append(f'{result_hash}:{path}')
            if result == VerifyResult.HASH_MISMATCH:
                bad += 1
            elif result != VerifyResult.HASH_MATCH:
                missing += 1
            if time.monotonic() - last > 0.25:
                last = time.monotonic()
                progress(done / total * 100, f'Prüfe Dateien … {done / total * 100:.1f} %')

        repair_file = os.path.join(self.core.lgd.get_tmp_path(), f'{self.app_name}.repair')
        if bad or missing:
            # Legendary's repair mode re-downloads everything not listed as matching in this file
            with open(repair_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(repair))
        else:
            igame.needs_verification = False
            self.core.install_game(igame)
            if os.path.exists(repair_file):
                os.remove(repair_file)
        progress(100, 'Prüfung abgeschlossen')
        return bad, missing

    def find_existing_installs(self) -> list[str]:
        """Rocket League folders found on this machine (Epic Games Launcher, Heroic, Lutris, defaults)."""
        candidates = []
        try:
            for m in self.core.egl.get_manifests():
                if m.app_name == self.app_name and m.install_location:
                    candidates.append(m.install_location)
        except Exception as e:  # noqa: BLE001 - EGL not installed / unreadable manifests
            log.debug('Reading EGL manifests failed: %r', e)

        home = os.path.expanduser('~')
        if sys.platform == 'win32':
            for env in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
                if base := os.environ.get(env):
                    candidates.append(os.path.join(base, 'Epic Games', RL_FOLDER))
            candidates += [f'{d}:\\Epic Games\\{RL_FOLDER}' for d in 'CDEFG']
        else:
            candidates += [
                os.path.join(home, 'Games', 'Heroic', RL_FOLDER),
                os.path.join(home, 'Games', 'epic-games-store', 'drive_c', 'Program Files', 'Epic Games', RL_FOLDER),
            ]
        candidates.append(os.path.join(self.settings.install_base, RL_FOLDER))

        found = []
        for c in candidates:
            path = find_rl_folder(c)
            if path and os.path.normcase(path) not in map(os.path.normcase, found):
                found.append(path)
        return found

    def import_install(self, path: str) -> str:
        """Register an existing Rocket League folder (e.g. from the Epic Games Launcher).

        ``path`` may be the game folder itself, its parent ("Epic Games") or a folder inside it.
        Returns the resolved game folder. Run :meth:`verify` afterwards.
        """
        self._lock()
        resolved = find_rl_folder(path)
        if not resolved:
            raise LauncherError(f'In "{path}" wurde kein Rocket League gefunden '
                                f'(erwartet: …/{RL_FOLDER}/{RL_EXE.replace("/", os.sep)}).')
        game = self._require_game()
        manifest, igame = self.core.import_game(game, resolved)
        exe = os.path.join(resolved, manifest.meta.launch_exe.lstrip('/'))
        if not _exists_case_insensitive(exe):
            raise LauncherError(f'In "{resolved}" fehlt {manifest.meta.launch_exe}.')
        # always verify imported files - we cannot know what another launcher left behind
        igame.needs_verification = True
        self.core.install_game(igame)
        return resolved

    def uninstall(self):
        self._lock()
        igame = self.core.get_installed_game(self.app_name)
        if igame:
            self.core.uninstall_game(igame, delete_files=True, delete_root_directory=True)

    # ---------------------------------------------------------------- launch
    def build_launch(self, runner: Runner | None, offline: bool = False) -> tuple[list[str], str, dict]:
        """Return (command, working dir, full environment) to start Rocket League."""
        igame = self.core.get_installed_game(self.app_name)
        if not igame:
            raise LauncherError(f'{RL_TITLE} ist nicht installiert.')
        if not os.path.exists(igame.install_path):
            raise LauncherError(f'Installationsordner fehlt: {igame.install_path}')
        if runner is None:
            raise LauncherError('Kein Wine/Proton gefunden. Installiere umu-launcher, GE-Proton oder Wine '
                                '(oder trage in den Einstellungen einen Pfad ein).')
        if not offline and not self.try_login():
            raise LauncherError('Login abgelaufen – bitte neu anmelden.')

        extra = shlex.split(self.settings.launch_args) if self.settings.launch_args else []
        params = self.core.get_launch_parameters(app_name=self.app_name, offline=offline,
                                                 extra_args=extra, disable_wine=True)
        exe = os.path.join(params.game_directory, params.game_executable)
        args = [*params.game_parameters, *params.user_parameters, *params.egl_parameters]
        cmd, runner_env = runner.build(exe, args, self.settings.prefix_root)

        env = os.environ.copy()
        env.update(params.environment)
        env.update(runner_env)
        return cmd, params.working_directory, env

    def launch(self, runner: Runner | None, offline: bool = False) -> subprocess.Popen:
        cmd, cwd, env = self.build_launch(runner, offline)
        log.info('Launching: %s', shlex.join(_redact(cmd)))
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True  # keep the game running if the launcher closes
        return subprocess.Popen(cmd, cwd=cwd, env=env, **kwargs)


def _redact(cmd: list[str]) -> list[str]:
    return ['-AUTH_PASSWORD=***' if c.startswith('-AUTH_PASSWORD=') else c for c in cmd]


def find_rl_folder(path: str) -> str | None:
    """Resolve a user-picked folder to the Rocket League game folder, or None.

    Accepts the game folder, its parent (e.g. "Epic Games") or a folder below it (e.g. "Binaries/Win64").
    """
    if not path:
        return None
    path = os.path.abspath(path)
    candidates = [path, os.path.join(path, RL_FOLDER)]
    parent = path
    for _ in range(3):  # e.g. picked .../rocketleague/Binaries/Win64
        parent = os.path.dirname(parent)
        candidates.append(parent)
    for c in candidates:
        if os.path.isdir(c) and _exists_case_insensitive(os.path.join(c, RL_EXE)):
            return c
    return None


def _exists_case_insensitive(path: str) -> bool:
    if os.path.exists(path):
        return True
    if sys.platform == 'win32':
        return False
    from legendary.lfs.wine_helpers import case_insensitive_file_search
    try:
        return os.path.exists(case_insensitive_file_search(path))
    except OSError:  # unreadable directory on the way
        return False
