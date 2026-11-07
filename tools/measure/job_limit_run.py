r"""Run a command with a limit on ITS OWN commit (private memory), to see how it behaves when memory requests start to fail (G11 session). Nothing else on the machine is affected.

Windows lets a Job Object cap the commit of each process in it; a request over the cap fails exactly like one over the machine's commit limit. That is how the game's start-up crash was
reproduced on demand (full game under ~400 MB: dies inside gltf/_converter.py while loading the gun, the same stack as the real crash; ~280 MB: hangs in Viewmodel.prewarm).

Run: .venv\Scripts\python.exe -X utf8 tools\measure\job_limit_run.py 380 20 .venv\Scripts\python.exe -X utf8 main.py
     (380 = MB per process, 0 = no cap, only the peak is reported; 20 = seconds to wait; the rest is the command; paths relative to the project root)
Prints: whether it was still alive at the end or how it exited, its PEAK commit, and (if it exited) the tail of its output. PYTHONFAULTHANDLER is on for the command.
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in 'abcdef']


class JobBasic(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong), ('LimitFlags', wt.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wt.DWORD),
                ('Affinity', ctypes.c_size_t), ('PriorityClass', wt.DWORD), ('SchedulingClass', wt.DWORD)]


class JobExtended(ctypes.Structure):
    _fields_ = [('Basic', JobBasic), ('Io', IoCounters), ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


LIMIT_PROCESS_MEMORY = 0x100
LIMIT_KILL_ON_JOB_CLOSE = 0x2000
EXTENDED_LIMIT_INFORMATION = 9


def main():
    limit_mb, seconds, cmd = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3:]
    if not cmd:
        sys.exit(__doc__)
    if (ROOT / cmd[0]).exists():                                           # a path relative to the project root (CreateProcess would not find it with '/')
        cmd[0] = str((ROOT / cmd[0]).resolve())
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    job = k32.CreateJobObjectW(None, None)
    info = JobExtended()
    info.Basic.LimitFlags = LIMIT_KILL_ON_JOB_CLOSE | (LIMIT_PROCESS_MEMORY if limit_mb > 0 else 0)
    info.ProcessMemoryLimit = limit_mb * 2 ** 20
    if not k32.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
        sys.exit(f'SetInformationJobObject failed: {ctypes.get_last_error()}')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONFAULTHANDLER='1'), cwd=ROOT)
    k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    assigned = k32.AssignProcessToJobObject(job, ctypes.c_void_p(int(p._handle)))
    t0 = time.time()
    while p.poll() is None and time.time() - t0 < seconds:
        time.sleep(0.2)
    state = 'ALIVE at timeout (stopped by this tool)' if p.poll() is None else f'EXITED rc={p.returncode & 0xffffffff:#x}'
    q, size = JobExtended(), wt.DWORD()
    k32.QueryInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, ctypes.byref(q), ctypes.sizeof(q), ctypes.byref(size))
    k32.TerminateJobObject(job, 1)
    out = p.stdout.read().decode('utf-8', 'replace')
    print(f'limit={limit_mb or "none"} MB | assigned={bool(assigned)} | {state} | after {time.time() - t0:.1f} s | PEAK process commit {q.PeakProcessMemoryUsed / 2 ** 20:.0f} MB')
    if 'EXITED' in state:
        print('\n'.join(line for line in out.splitlines() if line.strip())[-1500:])


if __name__ == '__main__':
    main()
