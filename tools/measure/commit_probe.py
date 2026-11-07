r"""How much of the machine's free COMMIT (RAM + page file not yet promised to any program) a command takes: the game's footprint on the thing that ran out (G11 session).

Samples `AvailPageFile` (GlobalMemoryStatusEx) before the command starts and while it runs, then kills only that command (a Job Object with kill-on-close: nothing else is touched).
The other programs on the machine keep changing their own use, so repeat a few times and read the lowest values, not one run.

Run: .venv\Scripts\python.exe -X utf8 tools\measure\commit_probe.py 14 .venv\Scripts\python.exe -X utf8 main.py [--low-memory]
     (14 = seconds to watch; everything after it is the command; paths relative to the project root)
Prints: free commit before / lowest / steady, and the game's peak and steady footprint (MB).
Measured 7/11/2026 (1920x1080, borderless, sound on): full game 0.72-0.75 GB with 4x MSAA, 0.62 GB without; --low-memory 0.50-0.61 GB. docs/notes/troubleshooting.md has the story.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', wt.DWORD), ('dwMemoryLoad', wt.DWORD)] + [(n, ctypes.c_ulonglong) for n in (
        'TotalPhys', 'AvailPhys', 'TotalPageFile', 'AvailPageFile', 'TotalVirtual', 'AvailVirtual', 'AvailExtendedVirtual')]


def free_commit_mb() -> float:
    m = MemoryStatus()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.AvailPageFile / 2 ** 20


class JobBasic(ctypes.Structure):
    _fields_ = [('a', ctypes.c_longlong), ('b', ctypes.c_longlong), ('LimitFlags', wt.DWORD), ('c', ctypes.c_size_t), ('d', ctypes.c_size_t), ('e', wt.DWORD),
                ('f', ctypes.c_size_t), ('g', wt.DWORD), ('h', wt.DWORD)]


class JobExtended(ctypes.Structure):
    _fields_ = [('Basic', JobBasic), ('Io', ctypes.c_ulonglong * 6), ('ProcessLimit', ctypes.c_size_t), ('JobLimit', ctypes.c_size_t),
                ('PeakProcess', ctypes.c_size_t), ('PeakJob', ctypes.c_size_t)]


def main():
    seconds, cmd = float(sys.argv[1]), sys.argv[2:]
    if not cmd:
        sys.exit(__doc__)
    if (ROOT / cmd[0]).exists():                                           # a path relative to the project root (CreateProcess would not find it with '/')
        cmd[0] = str((ROOT / cmd[0]).resolve())
    before = min(free_commit_mb(), (time.sleep(0.5), free_commit_mb())[1])
    k32 = ctypes.WinDLL('kernel32')
    job = k32.CreateJobObjectW(None, None)
    info = JobExtended()
    info.Basic.LimitFlags = 0x2000                                         # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)
    k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.AssignProcessToJobObject(job, ctypes.c_void_p(int(p._handle)))
    t0, lowest, samples = time.time(), before, []
    while time.time() - t0 < seconds and p.poll() is None:
        free = free_commit_mb()
        lowest = min(lowest, free)
        samples.append(free)
        time.sleep(0.4)
    state = 'alive' if p.poll() is None else f'EXITED rc={p.returncode & 0xffffffff:#x}'
    second_half = sorted(samples[len(samples) // 2:])
    steady = second_half[len(second_half) // 2] if second_half else before
    k32.TerminateJobObject(job, 1)
    print(f'{state:14s} | free commit before {before:6.0f} MB | lowest {lowest:6.0f} MB | steady {steady:6.0f} MB  => takes {before - lowest:5.0f} MB peak, {before - steady:5.0f} MB steady')


if __name__ == '__main__':
    main()
