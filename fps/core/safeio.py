"""Atomic file writes (pure Python; tests/test_safeio.py). The file is written to a temporary file in the same folder, then swapped in with os.replace:
a crash, a power cut or a full disk in the middle of a save leaves the OLD file whole instead of a truncated one the next start cannot read (G16, C2)."""
import os
import tempfile
import threading
from pathlib import Path


def write_bytes_atomic(path, data: bytes):
    """Write `data` to `path` atomically. Raises OSError (the old file, if any, is untouched and no temporary file is left behind).
    The folder must exist (a missing folder is reported, like a plain write)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text_atomic(path, text: str, encoding: str = 'utf-8'):
    write_bytes_atomic(path, text.encode(encoding))


_bg_lock = threading.Lock()
_bg_latest = {}                # path -> number of the newest background save asked for it


def write_text_atomic_background(path, text: str, on_error=None, encoding: str = 'utf-8') -> threading.Thread:
    """Same write on a background thread: on the game's drive a temp file + rename costs 30-70 ms (antivirus), a hitch when it ran in the frame
    (closing the F2 panel). Saves of one path asked in quick succession: only the NEWEST is written, whatever order the threads run in. The thread is
    not a daemon: quitting right after a save still finishes it. `on_error(OSError)` is called on the thread."""
    data = text.encode(encoding)
    key = str(Path(path).resolve())
    with _bg_lock:
        n = _bg_latest.get(key, 0) + 1
        _bg_latest[key] = n

    def run():
        with _bg_lock:
            if _bg_latest.get(key) != n:
                return                    # a newer save of this path is queued: it writes the newer text
            try:
                write_bytes_atomic(path, data)
            except OSError as e:
                if on_error is not None:
                    on_error(e)

    t = threading.Thread(target=run, name=f'save {Path(path).name}')
    t.start()
    return t
