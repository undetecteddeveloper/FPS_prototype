r"""Chạy một lệnh với ổ khoá toàn máy: mỗi lúc chỉ MỘT game/selftest mở cửa sổ.

Dùng:  .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py <lệnh và đối số...>
Ví dụ: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\g3_selftest.py

Nhiều agent/terminal cùng chạy game thì các bài đo theo thời gian (nhịp bắn, FPS) trượt oan. Ổ khoá là khoá tệp của hệ điều hành
(msvcrt.locking): tiến trình chết thì hệ điều hành tự nhả, không bao giờ kẹt khoá. Mã thoát = mã của lệnh con.
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
    cmd[0] = shutil.which(os.path.normpath(cmd[0])) or cmd[0]      # đường dẫn tương đối có '/' không chạy được qua CreateProcess
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
