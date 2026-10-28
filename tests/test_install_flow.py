import queue
import threading
from types import SimpleNamespace

from conftest import FakeCore
from legendary.models.downloading import UIUpdate

from rl_launcher.backend import Backend, InstallPlan
from rl_launcher.settings import Settings


class FakeDLM:
    """Behaves like the DLManager process: pushes progress, exits."""

    def __init__(self, q, steps=3, exitcode=0, block=False):
        self.q, self.steps, self._exit, self.block = q, steps, exitcode, block
        self.exitcode = None
        self.pid = None
        self.stopped = threading.Event()
        self._t = None

    def _run(self):
        for i in range(self.steps):
            self.q.put(UIUpdate(progress=(i + 1) / self.steps * 100, download_speed=10 * 1024 * 1024,
                                write_speed=0, read_speed=0, memory_usage=0))
        if self.block:
            self.stopped.wait(10)
        self.exitcode = self._exit

    def start(self):
        self._t = threading.Thread(target=self._run)
        self._t.start()

    def is_alive(self):
        return self._t.is_alive()

    def join(self, timeout=None):
        self._t.join(timeout)


class InstallCore(FakeCore):
    def __init__(self):
        super().__init__()
        self.installed_calls = []

    def install_game(self, igame):
        self.installed_calls.append(igame)
        return {}


def plan(dlm, q):
    igame = SimpleNamespace(app_name='Sugar', install_tags=[], needs_verification=True, install_path='/g/rl')
    game = SimpleNamespace(app_name='Sugar')
    return InstallPlan(game, igame, SimpleNamespace(dl_size=1, install_size=2), dlm, q)


def test_install_success_reports_progress_and_registers_game():
    core = InstallCore()
    b = Backend(Settings(), core)
    q = queue.Queue()
    seen = []
    assert b.run_install(plan(FakeDLM(q), q), lambda p, t: seen.append(p), lambda: False) is True
    assert seen[-1] == 100
    assert core.installed_calls and core.installed_calls[0].needs_verification is False


def test_install_failure_raises():
    import pytest

    from rl_launcher.backend import LauncherError
    q = queue.Queue()
    with pytest.raises(LauncherError, match='Exit-Code 1'):
        Backend(Settings(), InstallCore()).run_install(plan(FakeDLM(q, exitcode=1), q), lambda *a: None,
                                                       lambda: False)


def test_install_cancel(monkeypatch):
    core = InstallCore()
    b = Backend(Settings(), core)
    q = queue.Queue()
    dlm = FakeDLM(q, block=True)
    monkeypatch.setattr(Backend, '_stop_dlm', staticmethod(lambda d: d.stopped.set()))
    assert b.run_install(plan(dlm, q), lambda *a: None, lambda: True) is False
    assert core.installed_calls == []
