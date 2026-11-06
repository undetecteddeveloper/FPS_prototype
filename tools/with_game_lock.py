r"""Runs a command under a machine-wide lock: only ONE game or selftest opens a window at a time.

Usage:  .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <command and arguments...>
Example: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\selftests\g3_selftest.py

When several agents or terminals run games at once, time-based measurements (fire rate, FPS) fail falsely. The lock is an OS file lock
(msvcrt.locking): if the process dies the OS releases it, so it never sticks. Exit code = the exit code of the child command.
"""
import msvcrt
import os
import shutil
import subprocess
import sys
import tempfile
import time

LOCK_PATH = os.path.join(tempfile.gettempdir(), 'fps_prototype_game.lock')


def main() -> int:
    cmd = sys.argv[1:]
    if not cmd:
        print(__doc__)
        return 2
    cmd[0] = shutil.which(os.path.normpath(cmd[0])) or cmd[0]      # a relative path containing '/' does not run through CreateProcess
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT)
    waited = 0.0
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if waited == 0.0:
                print('[with_game_lock] có game khác đang chạy, chờ tới lượt...', flush=True)
            time.sleep(1.0)
            waited += 1.0
    if waited:
        print(f'[with_game_lock] đã chờ {waited:.0f} s', flush=True)
    try:
        return subprocess.call(cmd)
    finally:
        try:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


if __name__ == '__main__':
    sys.exit(main())
