import pytest

pytest.importorskip('PySide6')

from conftest import FakeCore  # noqa: E402

from rl_launcher import theme  # noqa: E402
from rl_launcher.backend import Backend  # noqa: E402
from rl_launcher.gui import MainWindow, load_fonts  # noqa: E402
from rl_launcher.settings import Settings  # noqa: E402


def make(qtbot, core):
    from PySide6.QtWidgets import QApplication
    QApplication.instance().setStyleSheet(theme.stylesheet())
    load_fonts()
    win = MainWindow(Backend(Settings(), core))
    qtbot.addWidget(win)
    qtbot.waitUntil(lambda: not win.busy(), timeout=5000)
    return win


def test_login_page_when_logged_out(qtbot):
    win = make(qtbot, FakeCore(logged_in=False))
    assert win.stack.currentWidget() is win.login_page


def test_login_flow(qtbot):
    core = FakeCore(logged_in=False)
    win = make(qtbot, core)
    win.login_page.code.setText('{"authorizationCode": "good"}')
    win.login_page.submit.click()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.game_page, timeout=5000)
    assert win.game_page.primary.text() == 'INSTALLIEREN'
    assert 'Klaus' in win.user_label.text()


def test_login_error_shown(qtbot):
    win = make(qtbot, FakeCore(logged_in=False))
    win.login_page.code.setText('bad')
    win.login_page.submit.click()
    qtbot.waitUntil(lambda: not win.login_page.error.isHidden(), timeout=5000)
    assert 'fehlgeschlagen' in win.login_page.error.text()


def test_play_and_update_states(qtbot, installed_game):
    win = make(qtbot, FakeCore(installed=installed_game, latest='1.1'))
    assert win.game_page.primary.text() == 'SPIELEN'
    win2 = make(qtbot, FakeCore(installed=installed_game, latest='1.2'))
    assert win2.game_page.primary.text() == 'UPDATE'


def test_not_owned(qtbot):
    win = make(qtbot, FakeCore(owned=False))
    assert 'STORE' in win.game_page.primary.text()


def test_install_then_play_flow(qtbot, monkeypatch, installed_game):
    import subprocess
    import sys
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox


    core = FakeCore(latest='1.1')
    win = make(qtbot, core)
    assert win.game_page.primary.text() == 'INSTALLIEREN'
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))

    fake_plan = SimpleNamespace(download_size=10, install_size=20, warnings=['Hinweis'],
                                igame=SimpleNamespace(install_path='/g/rl'))
    monkeypatch.setattr(win.backend, 'prepare_install', lambda repair=False: fake_plan)

    def run_install(plan, progress, cancelled):
        progress(50.0, '50 %')
        core.lgd.installed = installed_game  # now registered as installed (version 1.1)
        return True
    monkeypatch.setattr(win.backend, 'run_install', run_install)

    win.game_page.primary.click()
    qtbot.waitUntil(lambda: win.game_page.primary.text() == 'SPIELEN' and not win.busy(), timeout=5000)

    win.settings.custom_runner_path = '/usr/bin/wine'
    monkeypatch.setattr(win.backend, 'launch',
                        lambda runner, offline=False: subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1)']))  # noqa: E501
    win.game_page.primary.click()
    qtbot.waitUntil(lambda: win.game_page.primary.text() == 'LÄUFT …', timeout=5000)
    qtbot.waitUntil(lambda: win.game_page.primary.text() == 'SPIELEN', timeout=8000)
    assert 'beendet' in win.game_page.status.text()


@pytest.mark.parametrize('broken', [False, True])
def test_import_existing_install_runs_verify(qtbot, monkeypatch, installed_game, broken):
    core = FakeCore(latest='1.1')
    win = make(qtbot, core)
    assert not win.game_page.import_btn.isHidden()
    calls = []

    def import_install(path):
        calls.append(('import', path))
        core.lgd.installed = installed_game
        return '/games/rocketleague'

    def verify(progress, cancelled):
        calls.append('verify')
        progress(100, 'ok')
        return (2, 1) if broken else (0, 0)

    monkeypatch.setattr(win, '_pick_install_dir', lambda: '/games')
    monkeypatch.setattr(win.backend, 'import_install', import_install)
    monkeypatch.setattr(win.backend, 'verify', verify)
    monkeypatch.setattr(win.backend, 'prepare_install', lambda repair=False: calls.append(('plan', repair)) or 'PLAN')
    confirmed = []
    monkeypatch.setattr(win, '_confirm_install', confirmed.append)

    win.game_page.import_btn.click()
    qtbot.waitUntil(lambda: not win.busy() and ('verify' in calls), timeout=5000)
    qtbot.waitUntil(lambda: not win.busy(), timeout=5000)
    assert calls[:2] == [('import', '/games'), 'verify']
    if broken:
        assert ('plan', True) in calls and confirmed == ['PLAN']
        assert 'nachgeladen' in win.game_page.status.text()
    else:
        assert confirmed == [] and win.game_page.primary.text() == 'SPIELEN'
