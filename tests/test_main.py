import sys

from rl_launcher.__main__ import restore_child_env


def test_restore_child_env(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    env = {'LD_LIBRARY_PATH': '/tmp/_MEI123', 'LD_LIBRARY_PATH_ORIG': '/opt/lib'}
    restore_child_env(env)
    assert env['LD_LIBRARY_PATH'] == '/opt/lib'

    env = {'LD_LIBRARY_PATH': '/tmp/_MEI123'}
    restore_child_env(env)
    assert 'LD_LIBRARY_PATH' not in env


def test_restore_child_env_noop_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    env = {'LD_LIBRARY_PATH': '/x'}
    restore_child_env(env)
    assert env == {'LD_LIBRARY_PATH': '/x'}
