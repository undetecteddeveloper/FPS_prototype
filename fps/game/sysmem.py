"""Windows probes for start-up (no Ursina, no Panda): the machine's free commit, a message box, and the crash log. The decisions are in fps/core/memplan.py.

`install_crash_log` is why a native crash no longer disappears without a trace (before G11's fix the only evidence was the Windows Event Log): it writes the Python stack of
every thread to `logs/crash.log`, and stops Windows from holding the dead process for ~10 s to build an error report (the sound device kept looping its last buffer during that time).
"""
import datetime
import faulthandler
import sys
from pathlib import Path

LOG_LIMIT = 200_000                  # bytes: a bigger log is started again (it only ever needs the last few crashes)
_log_file = None                     # kept open on purpose: faulthandler writes to it from inside a crash, when nothing can be opened any more


def _memory_status():
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in (
            'TotalPhys', 'AvailPhys', 'TotalPageFile', 'AvailPageFile', 'TotalVirtual', 'AvailVirtual', 'AvailExtendedVirtual')]
    s = Status()
    s.dwLength = ctypes.sizeof(s)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        return None
    return s


def free_commit_mb():
    """MB of commit still free for new allocations (Windows: AvailPageFile of GlobalMemoryStatusEx); None on other systems or if the call fails."""
    if sys.platform != 'win32':
        return None
    try:
        s = _memory_status()
        return None if s is None else s.AvailPageFile / 2 ** 20
    except (OSError, AttributeError):
        return None


def commit_limit_mb():
    if sys.platform != 'win32':
        return None
    try:
        s = _memory_status()
        return None if s is None else s.TotalPageFile / 2 ** 20
    except (OSError, AttributeError):
        return None


def show_error(title: str, text: str):
    """A message box (the game window is not open yet, and a double-clicked run.bat has no console worth reading). Falls back to the console."""
    print(f'[{title}] {text}', file=sys.stderr)
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)         # MB_ICONERROR
    except (OSError, AttributeError):
        pass


def header_line(argv, free_mb, limit_mb, mode: str, now=None) -> str:
    """The line that opens each run in the crash log: when, how it was launched, and the memory it started with (so a crash can be read against its conditions)."""
    now = now or datetime.datetime.now()
    free = 'không rõ' if free_mb is None else f'{free_mb:.0f} MB'
    limit = 'không rõ' if limit_mb is None else f'{limit_mb:.0f} MB'
    return f'=== {now:%Y-%m-%d %H:%M:%S} | lệnh: {" ".join(argv)} | commit trống {free} / giới hạn {limit} | chế độ {mode}\n'


def install_crash_log(path: Path, header: str):
    """Enable faulthandler into `path` (appended, header first) and, on Windows, switch off the error-report window so a crashed process ends at once."""
    global _log_file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.write_text('', encoding='utf-8')
        _log_file = open(path, 'a', encoding='utf-8', buffering=1)
        _log_file.write(header)
        faulthandler.enable(_log_file, all_threads=True)
    except OSError as e:
        print(f'[crash log] không mở được {path}: {e}', file=sys.stderr)
        faulthandler.enable(all_threads=True)
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)         # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX
        except (OSError, AttributeError):
            pass


def start_watchdog(seconds: float):
    """If the build has not finished after `seconds`, write where every thread is stuck into the crash log (the game goes on; it is a note, not a kill). A hang is how running out of
    memory looked half of the time (black window, nothing in the console), and nothing else would say where it stopped."""
    if _log_file is not None:                  # nothing is written now: a run that starts in time must leave no trace; faulthandler itself writes "Timeout (0:02:30)!" and the stacks
        faulthandler.dump_traceback_later(seconds, repeat=False, file=_log_file)


def stop_watchdog():
    faulthandler.cancel_dump_traceback_later()
