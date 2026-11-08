"""Atomic file writes (pure Python; tests/test_safeio.py). The file is written to a temporary file in the same folder, then swapped in with os.replace:
a crash, a power cut or a full disk in the middle of a save leaves the OLD file whole instead of a truncated one the next start cannot read (G16, C2)."""
import os
import tempfile
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
