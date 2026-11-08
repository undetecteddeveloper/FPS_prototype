"""G16 (A3): an unexpected Python error while building or playing ends with a message box + the traceback in logs/crash.log + exit code 1,
never a silent disappearance. Runs the real `main()` in a child process with the build / the frame loop replaced by a failing stand-in (no window)."""
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(tmp_path, body: str):
    child = textwrap.dedent(f'''
        import sys, types
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        import fps.app as app
        from fps.game import sysmem
        app.CRASH_LOG = Path({str(tmp_path / 'crash.log')!r})
        sysmem.free_commit_mb = lambda: 8000.0
        sysmem.commit_limit_mb = lambda: 24000.0
        sysmem.show_error = lambda title, text: print('BOX|' + title + '|' + text.replace(chr(10), ' '))
    ''') + textwrap.dedent(body)
    p = subprocess.run([sys.executable, '-X', 'utf8', '-c', child], capture_output=True, timeout=120)
    log = tmp_path / 'crash.log'
    return p, p.stdout.decode('utf-8', 'replace'), log.read_text(encoding='utf-8') if log.exists() else ''


def test_an_error_while_building_shows_a_box_and_logs(tmp_path):
    p, out, log = _run(tmp_path, '''
        def boom(*a, **k):
            raise RuntimeError('không tạo được buffer cho ống kính')
        app.create_game = boom
        app.main(['--window', '--quit-after', '1'])
    ''')
    assert p.returncode == 1, (out, p.stderr[-800:])
    assert 'BOX|Game không mở được|RuntimeError: không tạo được buffer cho ống kính' in out
    assert r'logs\crash.log' in out
    assert 'lỗi Python: Game không mở được' in log and 'Traceback' in log and 'không tạo được buffer' in log


def test_an_error_in_a_frame_shows_a_box_and_logs(tmp_path):
    p, out, log = _run(tmp_path, '''
        def run():
            raise ZeroDivisionError('chia cho 0 trong Game.update')
        fake = types.SimpleNamespace(app=types.SimpleNamespace(run=run), notice=types.SimpleNamespace(show=lambda *a, **k: None))
        app.create_game = lambda *a, **k: fake
        app.main(['--window', '--quit-after', '1'])
    ''')
    assert p.returncode == 1, (out, p.stderr[-800:])
    assert 'BOX|Game gặp lỗi và phải đóng|ZeroDivisionError: chia cho 0 trong Game.update' in out
    assert 'lỗi Python: Game gặp lỗi và phải đóng' in log and 'ZeroDivisionError' in log


def test_a_long_message_is_cut_for_the_box(tmp_path):
    p, out, log = _run(tmp_path, '''
        def boom(*a, **k):
            raise ValueError('x' * 5000)
        app.create_game = boom
        app.main(['--window'])
    ''')
    box = next(line for line in out.splitlines() if line.startswith('BOX|'))
    assert len(box) < 700 and box.count('x') <= 400
    assert 'x' * 5000 in log                      # the log keeps everything


def test_a_bad_size_argument_is_a_message_not_a_traceback(tmp_path):
    p, out, _ = _run(tmp_path, '''
        app.create_game = lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not build'))
        app.main(['--window', '--size', '1280-720'])
    ''')
    assert p.returncode == 2, (out, p.stderr[-800:])
    assert 'BOX|Tham số không hợp lệ|' in out and 'RỘNGxCAO' in out
    assert b'Traceback' not in p.stderr


def test_an_unreadable_monitor_list_falls_back(monkeypatch):
    import screeninfo
    import fps.app as app

    def boom():
        raise screeninfo.common.ScreenInfoError('no monitors')
    monkeypatch.setattr(screeninfo, 'get_monitors', boom)
    assert app.desktop_size() == (1280, 720)
