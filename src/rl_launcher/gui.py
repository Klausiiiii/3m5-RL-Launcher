"""PySide6 user interface of the 3m5 Rocket League Launcher."""
from __future__ import annotations

import logging
import os
import shutil
import sys
import traceback
import webbrowser
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .backend import LOGIN_URL, RL_TITLE, STORE_URL, Backend, GameState, LauncherError
from .runners import PROTON, UMU, WINE, Runner, detect_runners, runner_id, select_runner
from .settings import Settings, data_dir
from .tools import install_ge_proton, install_wine_mono

log = logging.getLogger('rl_launcher.gui')


def fmt_size(num: float) -> str:
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if num < 1024:
            return f'{num:.1f} {unit}'
        num /= 1024
    return f'{num:.1f} TiB'


def custom_runner(path: str) -> Runner:
    base = os.path.basename(path).lower()
    if base == 'proton':
        return Runner(PROTON, f'Proton ({path})', path)
    if base.startswith('umu-run'):
        return Runner(UMU, f'umu ({path})', path)
    return Runner(WINE, f'Wine ({path})', path)


# ---------------------------------------------------------------------- worker
class Worker(QThread):
    """Runs ``fn(worker)`` in a thread. ``fn`` may call ``worker.report`` and check ``worker.cancelled``."""
    progress = Signal(float, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[['Worker'], object], parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def report(self, percent: float, text: str):
        self.progress.emit(percent, text)

    def run(self):
        try:
            self.succeeded.emit(self._fn(self))
        except LauncherError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 - show anything unexpected instead of crashing the UI
            log.error('Unexpected error:\n%s', traceback.format_exc())
            self.failed.emit(f'Unerwarteter Fehler: {e!r}\nDetails im Log: {data_dir()}')


# ----------------------------------------------------------------------- pages
class LoginPage(QWidget):
    login_code = Signal(str)
    login_import = Signal()

    def __init__(self):
        super().__init__()
        card = QFrame(objectName='card')
        card.setFixedWidth(580)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(14)

        title = QLabel('Mit Epic Games anmelden', objectName='heroSub')
        title.setStyleSheet('font-size: 22px; font-weight: 700;')
        lay.addWidget(title)
        steps = QLabel(
            '1. Öffne den Epic-Login im Browser und melde dich an.<br>'
            '2. Du siehst danach eine Textseite (JSON).<br>'
            '3. Kopiere den Wert von <b>authorizationCode</b> – oder einfach die ganze Seite – hier hinein.',
            objectName='muted')
        steps.setWordWrap(True)
        lay.addWidget(steps)

        open_btn = QPushButton('Epic-Login im Browser öffnen')
        open_btn.clicked.connect(lambda: webbrowser.open(LOGIN_URL))
        lay.addWidget(open_btn)

        self.code = QLineEdit(placeholderText='authorizationCode einfügen')
        self.code.returnPressed.connect(self._submit)
        lay.addWidget(self.code)

        self.submit = QPushButton('Anmelden', objectName='primary')
        self.submit.clicked.connect(self._submit)
        lay.addWidget(self.submit)

        self.error = QLabel(objectName='error')
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)

        imp = QPushButton('Anmeldung aus installiertem Epic Games Launcher übernehmen', objectName='link')
        imp.clicked.connect(self.login_import)
        lay.addWidget(imp, alignment=Qt.AlignLeft)

        outer = QVBoxLayout(self)
        outer.addStretch()
        outer.addWidget(card, alignment=Qt.AlignHCenter)
        outer.addStretch()

    def _submit(self):
        self.login_code.emit(self.code.text())

    def set_busy(self, busy: bool):
        self.submit.setEnabled(not busy)
        self.code.setEnabled(not busy)

    def show_error(self, msg: str):
        self.error.setText(msg)
        self.error.setVisible(bool(msg))


class GamePage(QWidget):
    def __init__(self):
        super().__init__()
        hero = QFrame(objectName='hero')
        hero.setMinimumHeight(260)
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(40, 36, 40, 36)
        hl.addStretch()
        hl.addWidget(QLabel(RL_TITLE.upper(), objectName='heroTitle'))
        self.version = QLabel('', objectName='heroSub')
        hl.addWidget(self.version)

        self.primary = QPushButton('…', objectName='primary')
        self.primary.setCursor(Qt.PointingHandCursor)
        self.cancel = QPushButton('Abbrechen', objectName='danger')
        self.cancel.hide()

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.status = QLabel('', objectName='status')
        self.status.setWordWrap(True)

        self.import_btn = QPushButton('Vorhandene Installation wählen')
        self.import_btn.setToolTip('Rocket League ist schon installiert (z. B. über den Epic Games Launcher)? '
                                   'Ordner wählen – die Dateien werden nur geprüft, nicht neu geladen.')
        action_row = QHBoxLayout()
        action_row.addWidget(self.primary)
        action_row.addWidget(self.import_btn)
        action_row.addWidget(self.cancel)
        action_row.addStretch()

        self.repair = QPushButton('Reparieren')
        self.open_dir = QPushButton('Spielordner öffnen')
        self.reload = QPushButton('Neu laden')
        self.uninstall = QPushButton('Deinstallieren', objectName='danger')
        tools = QHBoxLayout()
        for b in (self.reload, self.repair, self.open_dir):
            tools.addWidget(b)
        tools.addStretch()
        tools.addWidget(self.uninstall)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)
        lay.addWidget(hero)
        lay.addLayout(action_row)
        lay.addWidget(self.progress)
        lay.addWidget(self.status)
        lay.addStretch()
        lay.addLayout(tools)


# --------------------------------------------------------------------- dialogs
class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, runners: list[Runner], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Einstellungen')
        self.setMinimumWidth(620)
        self.settings = settings
        form = QFormLayout()
        form.setSpacing(12)

        self.install_base = QLineEdit(settings.install_base)
        form.addRow('Installationsordner', self._with_browse(self.install_base))

        self.runner = QComboBox()
        self.custom = QLineEdit(settings.custom_runner_path,
                                placeholderText='optional: Pfad zu wine / proton / umu-run')
        self.prefix = QLineEdit(settings.prefix_root)
        if sys.platform != 'win32':
            for r in runners:
                self.runner.addItem(r.name, runner_id(r))
            if not runners:
                self.runner.addItem('Nichts gefunden – bitte Pfad unten angeben', '')
            selected = select_runner(runners, settings.runner)
            if selected:
                self.runner.setCurrentIndex(self.runner.findData(runner_id(selected)))
            form.addRow('Wine / Proton', self.runner)
            form.addRow('Eigener Runner', self._with_browse(self.custom, file=True))
            form.addRow('Wine-Prefix', self._with_browse(self.prefix))

            tools = QHBoxLayout()
            self.ge_btn = QPushButton('GE-Proton installieren')
            self.ge_btn.setToolTip('Neueste GE-Proton-Version (bringt Mono und DXVK mit, kein Root nötig)')
            self.ge_btn.clicked.connect(self.install_ge_proton)
            self.mono_btn = QPushButton('Wine Mono installieren')
            self.mono_btn.setToolTip('Nur für System-Wine: installiert Wine Mono in den Wine-Prefix')
            self.mono_btn.clicked.connect(self.install_wine_mono)
            tools.addWidget(self.ge_btn)
            tools.addWidget(self.mono_btn)
            tools.addStretch()
            form.addRow('Nachinstallieren', tools)
            self.tool_status = QLabel(objectName='muted')
            self.tool_status.setWordWrap(True)
            form.addRow('', self.tool_status)

        self.launch_args = QLineEdit(settings.launch_args, placeholderText='z. B. -nomovie')
        form.addRow('Startparameter', self.launch_args)
        self.skip_update = QCheckBox('Vor dem Start nicht nach Updates suchen')
        self.skip_update.setChecked(settings.skip_update_check)
        form.addRow('', self.skip_update)

        logs = QPushButton('Log-Ordner öffnen', objectName='link')
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(data_dir())))
        form.addRow('', logs)

        self.worker: Worker | None = None
        self.buttons = buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _with_browse(self, edit: QLineEdit, file: bool = False) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        btn = QPushButton('…')
        btn.setFixedWidth(44)

        def browse():
            if file:
                path, _ = QFileDialog.getOpenFileName(self, 'Datei wählen', edit.text())
            else:
                path = QFileDialog.getExistingDirectory(self, 'Ordner wählen', edit.text())
            if path:
                edit.setText(path)
        btn.clicked.connect(browse)
        row.addWidget(btn)
        return w

    # ---------------------------------------------------------- tool installers
    def _run_tool(self, fn, on_done):
        self.ge_btn.setEnabled(False)
        self.mono_btn.setEnabled(False)
        self.buttons.setEnabled(False)
        self.worker = w = Worker(fn, self)
        w.progress.connect(lambda pct, text: self.tool_status.setText(text))
        w.succeeded.connect(lambda res: self._tool_finished(on_done, res))
        w.failed.connect(self._tool_failed)
        w.start()

    def _tool_finished(self, cb, res):
        self._tools_enabled()
        cb(res)

    def _tool_failed(self, msg: str):
        self._tools_enabled()
        self.tool_status.setText('')
        QMessageBox.warning(self, 'Fehler', msg)

    def _tools_enabled(self):
        self.ge_btn.setEnabled(True)
        self.mono_btn.setEnabled(True)
        self.buttons.setEnabled(True)

    def reject(self):
        if self.worker and self.worker.isRunning():
            return  # keep the dialog (and its worker) alive until the install is through
        super().reject()

    def install_ge_proton(self):
        def done(name: str):
            runners = detect_runners()
            self.runner.clear()
            for r in runners:
                self.runner.addItem(r.name, runner_id(r))
            new = next((r for r in runners if r.kind == PROTON and r.name == name), None)
            if new:
                self.runner.setCurrentIndex(self.runner.findData(runner_id(new)))
            self.tool_status.setText(f'{name} ist installiert und ausgewählt – mit „Speichern“ übernehmen.')
        self._run_tool(lambda w: install_ge_proton(w.report, w.cancelled), done)

    def install_wine_mono(self):
        custom = self.custom.text().strip()
        wine = custom if custom and custom_runner(custom).kind == WINE else shutil.which('wine')
        if not wine:
            QMessageBox.warning(self, 'Fehler', 'System-Wine nicht gefunden. Installiere es über deine '
                                'Distribution (z. B. „sudo apt install wine“) – oder nimm GE-Proton.')
            return
        prefix_root = self.prefix.text().strip() or self.settings.prefix_root
        self._run_tool(lambda w: install_wine_mono(wine, prefix_root, w.report, w.cancelled),
                       lambda v: self.tool_status.setText(f'Wine Mono {v} ist im Prefix installiert.'))

    def apply(self):
        s = self.settings
        s.install_base = self.install_base.text().strip() or s.install_base
        s.runner = self.runner.currentData() or ''
        s.custom_runner_path = self.custom.text().strip()
        s.prefix_root = self.prefix.text().strip() or s.prefix_root
        s.launch_args = self.launch_args.text().strip()
        s.skip_update_check = self.skip_update.isChecked()
        s.save()


# ------------------------------------------------------------------ main window
class MainWindow(QMainWindow):
    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend
        self.settings = backend.settings
        self.runners = detect_runners()
        self.state = GameState()
        self.worker: Worker | None = None
        self.game_proc = None

        self.setWindowTitle(f'3m5 RL Launcher {__version__}')
        self.setWindowIcon(QIcon(theme.asset_path('icon.svg')))
        self.resize(1000, 680)

        central = QWidget(objectName='central')
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.login_page = LoginPage()
        self.game_page = GamePage()
        self.loading = QLabel('Lade …', alignment=Qt.AlignCenter, objectName='muted')
        for w in (self.loading, self.login_page, self.game_page):
            self.stack.addWidget(w)
        root.addWidget(self.stack)
        self.setCentralWidget(central)

        self.login_page.login_code.connect(self.do_login_code)
        self.login_page.login_import.connect(self.do_login_import)
        gp = self.game_page
        gp.primary.clicked.connect(self.on_primary)
        gp.cancel.clicked.connect(self.on_cancel)
        gp.repair.clicked.connect(self.do_repair)
        gp.reload.clicked.connect(self.refresh)
        gp.import_btn.clicked.connect(self.do_import)
        gp.uninstall.clicked.connect(self.do_uninstall)
        gp.open_dir.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.state.install_path)))

        self.proc_timer = QTimer(self, interval=1000)
        self.proc_timer.timeout.connect(self._poll_game)

        self.refresh()

    def _build_header(self) -> QWidget:
        header = QFrame(objectName='header')
        header.setFixedHeight(64)
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 0, 24, 0)
        row.addWidget(QLabel(f'3m5<span style="color:{theme.HIGHLIGHT}">.</span>', objectName='wordmark'))
        sub = QLabel('  Rocket League Launcher', objectName='headerSub')
        row.addWidget(sub)
        row.addStretch()
        self.user_label = QLabel('', objectName='muted')
        row.addWidget(self.user_label)
        self.settings_btn = QPushButton('Einstellungen')
        self.settings_btn.clicked.connect(self.open_settings)
        row.addWidget(self.settings_btn)
        self.logout_btn = QPushButton('Abmelden')
        self.logout_btn.clicked.connect(self.do_logout)
        row.addWidget(self.logout_btn)
        return header

    # ------------------------------------------------------------- helpers
    def runner(self) -> Runner | None:
        if self.settings.custom_runner_path:
            return custom_runner(self.settings.custom_runner_path)
        return select_runner(self.runners, self.settings.runner)

    def busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def run_task(self, fn, on_done=None, on_fail=None, cancellable=False, label='', show_progress=None):
        gp = self.game_page
        self.worker = w = Worker(fn, self)
        w.progress.connect(self._on_progress)
        w.succeeded.connect(lambda res: self._task_finished(on_done, res))
        w.failed.connect(lambda msg: self._task_failed(on_fail, msg))
        gp.cancel.setVisible(cancellable)
        gp.progress.setVisible(cancellable if show_progress is None else show_progress)
        gp.progress.setValue(0)
        if label:
            gp.status.setText(label)
        self._set_enabled(False)
        w.start()

    def _on_progress(self, percent: float, text: str):
        self.game_page.progress.setValue(int(percent * 10))
        self.game_page.status.setText(text)

    def _task_finished(self, cb, res):
        self._end_task()
        if cb:
            cb(res)

    def _task_failed(self, cb, msg):
        self._end_task()
        if cb:
            cb(msg)
        else:
            self.game_page.status.setText('')
            QMessageBox.warning(self, 'Fehler', msg)
            self.refresh()

    def _end_task(self):
        gp = self.game_page
        gp.cancel.hide()
        gp.progress.hide()
        self._set_enabled(True)

    def _set_enabled(self, enabled: bool):
        gp = self.game_page
        for b in (gp.primary, gp.reload, gp.repair, gp.import_btn, gp.uninstall, gp.open_dir, self.settings_btn,
                  self.logout_btn):
            b.setEnabled(enabled)
        self.login_page.set_busy(not enabled)
        if enabled:
            self._apply_state()

    # --------------------------------------------------------------- state
    def refresh(self):
        self.run_task(lambda w: self.backend.refresh_state(), self._got_state, self._state_failed)

    def _state_failed(self, msg):
        # Offline / Epic down: still allow playing an installed game.
        log.warning('State refresh failed: %s', msg)
        try:
            self.state = self.backend.refresh_state(online=False)
        except Exception:  # noqa: BLE001
            self.state = GameState()
        self.state.logged_in = self.state.installed
        self._apply_state()
        self.game_page.status.setText(f'Offline-Modus: {msg}')

    def _got_state(self, state: GameState):
        self.state = state
        self._apply_state()

    def _apply_state(self):
        s = self.state
        gp = self.game_page
        if not s.logged_in:
            self.stack.setCurrentWidget(self.login_page)
            self.user_label.setText('')
            self.logout_btn.hide()
            return
        self.logout_btn.show()
        self.user_label.setText(f'Angemeldet als {s.user}  ' if s.user else '')
        self.stack.setCurrentWidget(self.game_page)

        if s.installed:
            v = f'Installiert: {s.installed_version}'
            if s.update_available:
                v += f'   ·   Neu: {s.latest_version}'
            gp.version.setText(v)
        else:
            gp.version.setText('Nicht installiert')

        running = self.game_proc is not None
        gp.repair.setVisible(s.installed)
        gp.open_dir.setVisible(s.installed)
        gp.uninstall.setVisible(s.installed)
        gp.import_btn.setVisible(s.owned and not s.installed)

        if running:
            gp.primary.setText('LÄUFT …')
            gp.primary.setEnabled(False)
        elif not s.owned and not s.installed:
            gp.primary.setText('IM EPIC STORE HOLEN')
            gp.status.setText(f'{RL_TITLE} ist nicht in deiner Bibliothek. Es ist kostenlos – '
                              'füge es im Store hinzu und klicke danach auf „Neu laden“.')
        elif not s.installed:
            gp.primary.setText('INSTALLIEREN')
        elif s.needs_verification:
            gp.primary.setText('PRÜFEN')
        elif s.update_available:
            gp.primary.setText('UPDATE')
        else:
            gp.primary.setText('SPIELEN')

    # ----------------------------------------------------------- auth actions
    def do_login_code(self, text: str):
        self.login_page.show_error('')
        self.run_task(lambda w: self.backend.login_with_code(text), lambda _: self.refresh(),
                      self.login_page.show_error)

    def do_login_import(self):
        self.login_page.show_error('')
        self.run_task(lambda w: self.backend.import_egl_login(), lambda _: self.refresh(),
                      self.login_page.show_error)

    def do_logout(self):
        if QMessageBox.question(self, 'Abmelden', 'Wirklich abmelden?') != QMessageBox.Yes:
            return
        self.backend.logout()
        self.state = GameState()
        self._apply_state()

    def open_settings(self):
        self.runners = detect_runners()
        dlg = SettingsDialog(self.settings, self.runners, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply()
            self.refresh()

    # ----------------------------------------------------------- game actions
    def on_primary(self):
        s = self.state
        if not s.owned and not s.installed:
            webbrowser.open(STORE_URL)
        elif not s.installed:
            self.do_install()
        elif s.needs_verification:
            self.do_repair()
        elif s.update_available:
            self.do_install()
        else:
            self.do_play()

    def on_cancel(self):
        if self.worker:
            self.worker.cancel()
            self.game_page.status.setText('Breche ab …')

    def do_install(self, repair: bool = False):
        def prepare(w: Worker):
            if repair:
                bad, missing = self.backend.verify(w.report, w.cancelled)
                log.info('Verification: %d corrupted, %d missing', bad, missing)
                if not bad and not missing:
                    # files are intact: a normal (delta) update is far cheaper than repair mode, which
                    # re-downloads every file that differs from the latest version in full
                    w.report(0, 'Dateien in Ordnung – suche nach Updates …')
                    return self.backend.prepare_install(repair=False)
            w.report(0, 'Bereite Download vor …')
            return self.backend.prepare_install(repair=repair)
        self.run_task(prepare, self._confirm_install, cancellable=repair, label='Bereite vor …')

    def _confirm_install(self, plan):
        if plan is None:
            self.game_page.status.setText('Alles aktuell – nichts herunterzuladen.')
            self.refresh()
            return
        text = (f'Download: {fmt_size(plan.download_size)}\n'
                f'Größe installiert: {fmt_size(plan.install_size)}\n'
                f'Ziel: {plan.igame.install_path}')
        if plan.warnings:
            text += '\n\nHinweise:\n' + '\n'.join(f'• {w}' for w in plan.warnings)
        if QMessageBox.question(self, f'{RL_TITLE} herunterladen?', text) != QMessageBox.Yes:
            self.game_page.status.setText('')
            return

        def run(w: Worker):
            return self.backend.run_install(plan, w.report, w.cancelled)

        def done(finished: bool):
            self.game_page.status.setText('Fertig installiert. Viel Spaß!' if finished else
                                          'Abgebrochen – beim nächsten Start geht es da weiter.')
            self.refresh()
        self.run_task(run, done, cancellable=True, label='Starte Download …')

    def do_repair(self):
        self.do_install(repair=True)

    def do_import(self):
        path = self._pick_install_dir()
        if not path:
            return

        def work(w: Worker):
            folder = self.backend.import_install(path)
            w.report(0, f'Prüfe Dateien in {folder} …')
            bad, missing = self.backend.verify(w.report, w.cancelled)
            log.info('Imported %s: %d corrupted, %d missing', folder, bad, missing)
            plan = self.backend.prepare_install(repair=True) if bad or missing else None
            return folder, bad, missing, plan

        def done(result):
            folder, bad, missing, plan = result
            if not bad and not missing:
                self.game_page.status.setText(f'Installation übernommen: {folder} – alle Dateien sind in Ordnung.')
                self.refresh()
                return
            self.game_page.status.setText(f'{bad} Datei(en) beschädigt, {missing} fehlen – werden nachgeladen.')
            self._confirm_install(plan)
        self.run_task(work, done, cancellable=True, label='Übernehme Installation …')

    def _pick_install_dir(self) -> str:
        found = self.backend.find_existing_installs()
        if found:
            box = QMessageBox(QMessageBox.Question, 'Installation gefunden',
                              f'Rocket League gefunden in:\n{found[0]}\n\nDiese Installation verwenden?', parent=self)
            use = box.addButton('Verwenden', QMessageBox.AcceptRole)
            other = box.addButton('Anderen Ordner wählen …', QMessageBox.ActionRole)
            box.addButton('Abbrechen', QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is use:
                return found[0]
            if box.clickedButton() is not other:
                return ''
        start = os.path.dirname(found[0]) if found else self.settings.install_base
        return QFileDialog.getExistingDirectory(self, 'Rocket-League-Ordner wählen (z. B. …/Epic Games/rocketleague)',
                                                start)

    def do_uninstall(self):
        if QMessageBox.question(self, 'Deinstallieren',
                                f'{RL_TITLE} inkl. aller Dateien in\n{self.state.install_path}\nlöschen?') \
                != QMessageBox.Yes:
            return
        self.run_task(lambda w: self.backend.uninstall(), lambda _: self.refresh(), label='Deinstalliere …')

    def do_play(self):
        def check(w: Worker):
            if not self.settings.skip_update_check:
                w.report(0, 'Suche nach Updates …')
                return self.backend.refresh_state()
            return self.state

        def checked(state: GameState):
            self.state = state
            if state.update_available:
                if QMessageBox.question(self, 'Update verfügbar',
                                        f'Version {state.latest_version} ist verfügbar. Jetzt aktualisieren?\n'
                                        '(Online-Spiele funktionieren meist nur mit aktueller Version.)') \
                        == QMessageBox.Yes:
                    self.do_install()
                    return
            self._launch()
        self.run_task(check, checked, label='')

    def _launch(self):
        runner = self.runner()

        def start(w: Worker):
            w.report(0, 'Starte Rocket League …')
            return self.backend.launch(runner)

        def started(proc):
            self.game_proc = proc
            self.proc_timer.start()
            self.game_page.status.setText(f'Rocket League läuft ({runner.name}).')
            self._apply_state()
        self.run_task(start, started)

    def _poll_game(self):
        if self.game_proc and self.game_proc.poll() is not None:
            code = self.game_proc.returncode
            self.game_proc = None
            self.proc_timer.stop()
            self.game_page.status.setText('Spiel beendet.' if code == 0 else f'Spiel beendet (Code {code}).')
            self._apply_state()

    def closeEvent(self, event):
        if self.busy():
            if QMessageBox.question(self, 'Beenden', 'Es läuft noch ein Vorgang. Abbrechen und beenden?') \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(15000)
        event.accept()


def load_fonts():
    QFontDatabase.addApplicationFont(theme.asset_path(os.path.join('fonts', 'Cabin.ttf')))


def run_gui(backend: Backend) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('3m5 RL Launcher')
    app.setWindowIcon(QIcon(theme.asset_path('icon.svg')))
    load_fonts()
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow(backend)
    win.show()
    return app.exec()
