"""Start-up memory plan (fps/core/memplan.py), the looping room tone staying out of Panda's streaming path, and the crash log (fps/game/sysmem.py)."""
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from fps.app import AUDIO_PRELOAD_BYTES
from fps.core import memplan
from fps.game import sysmem
from fps.weapon_data import AudioData

ROOT = Path(__file__).resolve().parent.parent


def test_plenty_of_commit_builds_everything():
    p = memplan.plan(4000.0)
    assert (p.mode, p.low_memory, p.message, p.notice) == ('full', False, '', '')


def test_unknown_commit_changes_nothing():
    """Not Windows, or the call failed: the game as it always was."""
    assert memplan.plan(None) == memplan.MemoryPlan('full', False, -1.0, '')


def test_thresholds_are_ordered_and_pick_the_mode():
    assert memplan.REDUCED_MB < memplan.FULL_MB
    assert memplan.plan(memplan.FULL_MB).mode == 'full'
    assert memplan.plan(memplan.FULL_MB - 1).mode == 'reduced'
    assert memplan.plan(memplan.REDUCED_MB).mode == 'reduced'
    assert memplan.plan(memplan.REDUCED_MB - 1).mode == 'critical'


def test_reduced_says_what_it_does_and_how_to_fix_it():
    p = memplan.plan(800.0)
    assert p.low_memory and 'giảm tải' in p.message and 'troubleshooting.md' in p.message and p.notice == memplan.NOTICE_REDUCED


def test_critical_does_not_start_and_tells_the_free_amount():
    p = memplan.plan(300.0)
    assert p.mode == 'critical' and '300' in p.message and 'pagefile' in p.message and p.notice == ''


def test_the_flag_forces_the_reduced_game_even_with_plenty():
    p = memplan.plan(4000.0, force_reduced=True)
    assert p.mode == 'reduced' and p.low_memory and '--low-memory' in p.message
    assert memplan.plan(None, force_reduced=True).low_memory


def test_notice_fits_on_one_line():
    assert len(memplan.NOTICE_REDUCED) <= 100


def test_every_sound_the_game_loops_stays_in_memory():
    """A file over the threshold is streamed (a 3 s queue the main thread refills each frame); a game stall then breaks the loop. The room tone is the biggest sound."""
    tone = ROOT / AudioData().ambience_file
    assert tone.exists() and tone.stat().st_size < AUDIO_PRELOAD_BYTES
    assert AUDIO_PRELOAD_BYTES > 1_000_000                       # Panda's own default: the reason this constant exists


def test_free_commit_probe_is_sane_on_this_machine():
    free, limit = sysmem.free_commit_mb(), sysmem.commit_limit_mb()
    if sys.platform != 'win32':
        assert free is None and limit is None
    else:
        assert 0 < free <= limit


def test_header_line_has_what_a_crash_needs_to_be_read_against():
    import datetime
    h = sysmem.header_line(['main.py', '--window'], 712.4, 19076.0, 'reduced', now=datetime.datetime(2026, 11, 7, 6, 9, 33))
    assert h.startswith('=== 2026-11-07 06:09:33') and 'main.py --window' in h and '712 MB' in h and '19076 MB' in h and 'reduced' in h and h.endswith('\n')
    assert 'không rõ' in sysmem.header_line([], None, None, 'full')


@pytest.mark.skipif(sys.platform != 'win32', reason='SetErrorMode / access violation behaviour is Windows-specific')
def test_a_native_crash_writes_the_log_and_ends_the_process_at_once(tmp_path):
    """Crash for real in a child process: the log has the header and the Python stack of the crash, and Windows does not hold the dead process for an error report."""
    log = tmp_path / 'logs' / 'crash.log'
    child = textwrap.dedent(f'''
        import faulthandler, sys
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from fps.game import sysmem
        sysmem.install_crash_log(Path({str(log)!r}), sysmem.header_line(['child'], 123.0, 456.0, 'full'))
        def boom():
            faulthandler._read_null()                             # a real native access violation (ctypes would catch it and raise OSError; _sigsegv goes through the C signal path instead), like the glb loader's memcpy
        boom()
    ''')
    t0 = time.time()
    p = subprocess.run([sys.executable, '-X', 'utf8', '-c', child], capture_output=True, timeout=60)
    took = time.time() - t0
    assert p.returncode != 0, p.returncode                       # (faulthandler ends the process itself after writing the log)
    text = log.read_text(encoding='utf-8')
    assert text.startswith('=== ') and 'commit trống 123 MB' in text
    assert 'access violation' in text and 'in boom' in text, text
    assert took < 8.0, f'the dead process lingered {took:.1f} s (Windows error reporting?)'


def test_a_big_log_is_started_again(tmp_path):
    log = tmp_path / 'crash.log'
    log.write_text('x' * (sysmem.LOG_LIMIT + 1), encoding='utf-8')
    child = f'import sys; sys.path.insert(0, {str(ROOT)!r}); from pathlib import Path; from fps.game import sysmem; sysmem.install_crash_log(Path({str(log)!r}), "=== new\\n")'
    subprocess.run([sys.executable, '-c', child], check=True, timeout=60)
    assert log.read_text(encoding='utf-8') == '=== new\n'


def test_main_refuses_to_start_when_not_even_the_reduced_game_fits(tmp_path):
    """Run the real `main()` with a pretend free commit of 300 MB: it must show the message and exit with code 1 BEFORE any window or model exists."""
    child = textwrap.dedent(f'''
        import sys
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        import fps.app as app
        from fps.game import sysmem
        app.CRASH_LOG = Path({str(tmp_path / 'crash.log')!r})
        sysmem.free_commit_mb = lambda: 300.0
        sysmem.commit_limit_mb = lambda: 18000.0
        sysmem.show_error = lambda title, text: print('BOX|' + title + '|' + text)
        app.create_game = lambda *a, **k: (_ for _ in ()).throw(AssertionError('the game must not be built'))
        app.main(['--quit-after', '1'])
    ''')
    p = subprocess.run([sys.executable, '-X', 'utf8', '-c', child], capture_output=True, timeout=120)
    out = p.stdout.decode('utf-8', 'replace')
    assert p.returncode == 1, (p.returncode, out, p.stderr.decode('utf-8', 'replace')[-800:])
    assert 'BOX|Không đủ bộ nhớ để mở game|' in out and '300' in out
    assert 'chế độ critical' in (tmp_path / 'crash.log').read_text(encoding='utf-8')


def _watchdog_child(log, stop: bool) -> str:
    return textwrap.dedent(f'''
        import sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from fps.game import sysmem
        sysmem.install_crash_log(Path({str(log)!r}), "=== watchdog test")
        sysmem.start_watchdog(1.0)
        {"sysmem.stop_watchdog()" if stop else "pass"}
        def stuck_here():
            time.sleep(2.5)
        stuck_here()
    ''')


def test_watchdog_says_where_a_slow_start_up_is_stuck(tmp_path):
    log = tmp_path / 'crash.log'
    subprocess.run([sys.executable, '-X', 'utf8', '-c', _watchdog_child(log, stop=False)], check=True, timeout=60)
    text = log.read_text(encoding='utf-8')
    assert 'Timeout' in text and 'in stuck_here' in text, text


def test_a_start_up_that_finishes_in_time_leaves_no_watchdog_note(tmp_path):
    log = tmp_path / 'crash.log'
    subprocess.run([sys.executable, '-X', 'utf8', '-c', _watchdog_child(log, stop=True)], check=True, timeout=60)
    assert log.read_text(encoding='utf-8') == '=== watchdog test'          # the header only: a start-up that finishes in time leaves nothing else behind
