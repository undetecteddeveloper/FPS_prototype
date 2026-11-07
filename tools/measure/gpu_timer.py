"""GPU time per frame (and per drawing pass) with OpenGL timestamp queries, plus the CPU time of the frame. Measuring aid only (tools/measure), never imported by the game.

How: every display region of every graphics output gets a Panda draw callback that brackets the region's normal drawing (`cbdata.upcall()`) with two
`glQueryCounter(GL_TIMESTAMP)` (core GL 3.3 / ARB_timer_query). A timestamp is written when the GPU has fully finished every earlier command, so
(last end - first begin) of a frame = GPU time of the frame (the span; includes buffer clears and the mipmap generation that run between regions, which the
per-region sums miss). Results are read 6 frames later and only when GL_QUERY_RESULT_AVAILABLE says so: reading earlier would stall the CPU on the GPU.
GL entry points come from `wglGetProcAddress` through ctypes (no PyOpenGL); the GL context is current inside a draw callback (single-threaded pipeline).

CPU time of a frame = Python tasks before Panda's render task (frame start at sort -1000 .. sort 49, igLoop is 50) + every region's cull callback +
every region's draw submission (CPU side of the upcalls). The flip, where the CPU waits for the GPU when the GPU is the bottleneck, is left out on purpose.

GPU time: `span` = last end - first begin; `busy` = sum of the regions. In a window (DWM composited) a GPU that is FASTER than the display sometimes waits
~one refresh between regions for the window's buffer (the span's 99th percentile was ~16 ms in every scene, 2026-11-07): an artefact of being too fast that a
GPU-bound weak machine never sees. `gpu_ms` = busy + the scene's MEDIAN gap (clears / mipmap generation between regions), see `finish`.
"""
import ctypes
import time as pytime
from collections import deque

from direct.task.TaskManagerGlobal import taskMgr
from panda3d.core import ClockObject

GL_TIMESTAMP = 0x8E28
GL_QUERY_RESULT = 0x8866
GL_QUERY_RESULT_AVAILABLE = 0x8867
READ_DELAY = 6                    # frames between issuing and reading a frame's queries


class _GL:
    def __init__(self):
        wgl = ctypes.WinDLL('opengl32')
        wgl.wglGetProcAddress.restype = ctypes.c_void_p
        wgl.wglGetProcAddress.argtypes = [ctypes.c_char_p]

        def fn(name, *argtypes):
            p = wgl.wglGetProcAddress(name.encode())
            if p in (None, 0, 1, 2, 3, -1):                 # wglGetProcAddress failure values
                raise RuntimeError(f'{name} not available (no GL 3.3 timer queries?)')
            return ctypes.WINFUNCTYPE(None, *argtypes)(p)
        u32p, u64p = ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint64)
        self.gen = fn('glGenQueries', ctypes.c_int, u32p)
        self.counter = fn('glQueryCounter', ctypes.c_uint, ctypes.c_uint)
        self.get_iv = fn('glGetQueryObjectiv', ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int))
        self.get_u64 = fn('glGetQueryObjectui64v', ctypes.c_uint, ctypes.c_uint, u64p)


class GpuTimer:
    """`hook(engine)` once the outputs exist (and again after any output is rebuilt). `frames` collects finished frames:
    dict(frame, gpu_ms (span), cpu_ms, passes={label: ms})."""

    def __init__(self):
        self.gl = None
        self.free = []
        self.pending = deque()          # (frame, cpu_ms, [(label, q0, q1)])
        self.cur_frame = -1
        self.cur = []
        self.frames = []
        self._t0 = pytime.perf_counter()
        self._engine = None
        self._app = 0.0                 # s of Python tasks this frame
        self._render_cpu = 0.0          # s of cull + draw submission this frame
        taskMgr.add(self._frame_start, 'gpu-timer-start', sort=-1000)
        taskMgr.add(self._app_end, 'gpu-timer-app-end', sort=49)

    def _frame_start(self, task):
        if self._engine is not None:
            self.hook(self._engine)         # outputs made later (the lens rebuilds its buffers on an F2 change) get callbacks too; hooked regions are skipped
        if self.cur:
            self._close((self._app + self._render_cpu) * 1000.0)
        self._render_cpu = 0.0
        self._t0 = pytime.perf_counter()
        return task.cont

    def _app_end(self, task):
        self._app = pytime.perf_counter() - self._t0
        return task.cont

    def hook(self, engine):
        self._engine = engine
        for i in range(engine.get_num_windows()):
            out = engine.get_window(i)
            for k in range(out.get_num_display_regions()):
                dr = out.get_display_region(k)
                cam = dr.get_camera()
                label = f'{out.get_name()}#{k}:' + (cam.get_name() if not cam.is_empty() else '-')
                if dr.get_draw_callback() is not None:
                    continue
                dr.set_draw_callback(self._make_cb(label))
                if dr.get_cull_callback() is None:
                    dr.set_cull_callback(self._cull_cb)

    def _cull_cb(self, cbdata):
        t = pytime.perf_counter()
        cbdata.upcall()
        self._render_cpu += pytime.perf_counter() - t

    def _query(self):
        if not self.free:
            ids = (ctypes.c_uint * 64)()
            self.gl.gen(64, ids)
            self.free.extend(ids)
        return self.free.pop()

    def _make_cb(self, label):
        def cb(cbdata):
            if self.gl is None:
                self.gl = _GL()
            q0, q1 = self._query(), self._query()
            t = pytime.perf_counter()
            self.gl.counter(q0, GL_TIMESTAMP)
            cbdata.upcall()
            self.gl.counter(q1, GL_TIMESTAMP)
            self._render_cpu += pytime.perf_counter() - t
            self.cur.append((label, q0, q1))
            self._read_ready()
        return cb

    def _close(self, cpu_ms):
        self.pending.append((ClockObject.get_global_clock().get_frame_count(), cpu_ms, self.cur))
        self.cur = []

    def _read_ready(self):
        gl = self.gl
        while len(self.pending) > READ_DELAY:
            frame, cpu_ms, qs = self.pending[0]
            ok = ctypes.c_int(0)
            gl.get_iv(qs[-1][2], GL_QUERY_RESULT_AVAILABLE, ctypes.byref(ok))
            if not ok.value:
                return
            self.pending.popleft()
            v = ctypes.c_uint64(0)
            stamps = []
            for label, q0, q1 in qs:
                gl.get_u64(q0, GL_QUERY_RESULT, ctypes.byref(v))
                a = v.value
                gl.get_u64(q1, GL_QUERY_RESULT, ctypes.byref(v))
                stamps.append((label, a, v.value))
                self.free.extend((q0, q1))
            span = (max(s[2] for s in stamps) - min(s[1] for s in stamps)) / 1e6
            passes = {}
            for label, a, b in stamps:
                passes[label] = passes.get(label, 0.0) + (b - a) / 1e6
            self.frames.append({'frame': frame, 'span_ms': span, 'busy_ms': sum(passes.values()), 'cpu_ms': cpu_ms, 'passes': passes})

    def take(self):
        """The frames finished since the last call, each with `gpu_ms` = busy + the median gap of these frames."""
        out, self.frames = self.frames, []
        if out:
            gaps = sorted(f['span_ms'] - f['busy_ms'] for f in out)
            gap = gaps[len(gaps) // 2]
            for f in out:
                f['gpu_ms'] = f['busy_ms'] + gap
                f['gap_ms'] = gap
        return out
