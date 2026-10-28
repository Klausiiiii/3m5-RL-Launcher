from rl_launcher.settings import Settings


def test_roundtrip():
    s = Settings.load()
    assert s.install_base and s.prefix_root
    s.launch_args = '-nomovie'
    s.runner = 'wine:/usr/bin/wine'
    s.save()
    again = Settings.load()
    assert again.launch_args == '-nomovie' and again.runner == 'wine:/usr/bin/wine'


def test_corrupt_and_unknown_keys():
    with open(_mk(Settings.path()), 'w') as f:
        f.write('{"launch_args": "-x", "unknown": 1}')
    assert Settings.load().launch_args == '-x'
    with open(Settings.path(), 'w') as f:
        f.write('not json')
    assert Settings.load().launch_args == ''


def _mk(path):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
