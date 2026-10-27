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
