r"""Launch / close check (G16, A1 + A7): start the real game N times in a row; each time wait for its window, let it run a few seconds, then close it
the way Alt+F4 / the X button does (WM_CLOSE to the window) and check that the process ends quickly with code 0 and leaves no Python error.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\launch_check.py [--runs 10] [--exe build\FPS_prototype\FPS_prototype.exe]
Exit code 1 if any run fails to open, to close, or prints a traceback.
"""
import argparse
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
u32 = ctypes.windll.user32
WM_CLOSE = 0x0010


def process_tree(root_pid: int) -> set:
    """`root_pid` and every process below it: the venv's python.exe is a launcher that starts the real interpreter as a CHILD, which owns the window."""
    class PE(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    parent = {}
    e = PE()
    e.dwSize = ctypes.sizeof(e)
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        parent[e.th32ProcessID] = e.th32ParentProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    tree, grew = {root_pid}, True
    while grew:
        new = {p for p, pp in parent.items() if pp in tree} - tree
        tree |= new
        grew = bool(new)
    return tree


def find_window(pid: int, title: str = 'FPS prototype'):
    found = []
    pids = process_tree(pid)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        owner = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and u32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == title:
                found.append(hwnd)
        return True
    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def one_run(cmd, run_s: float, open_timeout: float = 120.0, close_timeout: float = 15.0) -> tuple:
    """(ok, message, seconds to window, seconds to exit after WM_CLOSE)."""
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    hwnd = None
    while time.time() - t0 < open_timeout and p.poll() is None:
        hwnd = find_window(p.pid)
        if hwnd:
            break
        time.sleep(0.2)
    if not hwnd:
        p.kill()
        out = p.communicate()[0].decode('utf-8', 'replace')
        return False, f'không thấy cửa sổ (mã {p.returncode})\n{out[-1500:]}', None, None
    t_open = time.time() - t0
    time.sleep(run_s)
    if p.poll() is not None:
        out = p.communicate()[0].decode('utf-8', 'replace')
        return False, f'game tự tắt trước khi đóng (mã {p.returncode})\n{out[-1500:]}', t_open, None
    u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    t1 = time.time()
    try:
        out = p.communicate(timeout=close_timeout)[0].decode('utf-8', 'replace')
    except subprocess.TimeoutExpired:
        p.kill()
        return False, f'đóng cửa sổ mà tiến trình còn chạy sau {close_timeout:.0f} s', t_open, None
    t_close = time.time() - t1
    if p.returncode != 0 or 'Traceback' in out:
        return False, f'thoát mã {p.returncode}\n{out[-1500:]}', t_open, t_close
    return True, 'ok', t_open, t_close


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=10)
    ap.add_argument('--run-s', type=float, default=4.0, help='giây chơi trước khi đóng')
    ap.add_argument('--exe', default=None, help='chạy bản exe thay vì main.py')
    args = ap.parse_args()
    game_args = ['--window', '--size', '1280x720', '--mute']
    cmd = [str(Path(args.exe).resolve())] + game_args if args.exe else [sys.executable, '-X', 'utf8', 'main.py'] + game_args
    ok = 0
    for i in range(args.runs):
        good, msg, t_open, t_close = one_run(cmd, args.run_s)
        ok += good
        to = f'{t_open:.1f}' if t_open is not None else '-'
        tc = f'{t_close:.1f}' if t_close is not None else '-'
        print(f'lần {i + 1:2d}: {"QUA" if good else "TRƯỢT"}  cửa sổ sau {to} s, thoát sau {tc} s  {"" if good else msg}')
    print(f'KẾT QUẢ: {ok}/{args.runs} lần mở và đóng sạch')
    return 0 if ok == args.runs else 1


if __name__ == '__main__':
    sys.exit(main())
