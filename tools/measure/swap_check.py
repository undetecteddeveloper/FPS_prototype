r"""Gun draw / switch check (7/11/2026): the gun must never be on screen before its draw clip starts.

Records every frame the engine draws (the main loop AND the viewmodel's dry-run frames): is the gun shown, is the window drawing (a window that sits a frame out
shows nothing new), which clip the viewmodel plays. At game start and after each weapon switch the FIRST frame that shows the gun on screen must be the draw clip's
first frame. Also prints how long the switch freezes the game and whether frames after the draw start hitch.

Run: .venv\Scripts\python.exe -X utf8 tools\measure\swap_check.py        (exit code 1 if a check fails)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

import fps.app as app_mod  # noqa: E402
from fps.game import viewmodel as vm_mod  # noqa: E402
from main import create_game  # noqa: E402
from fps.weapon_data import GUNS  # noqa: E402
from ursina import Entity, application, mouse, time  # noqa: E402

records = []          # (source, gun shown, window drawing, clip key, gun key) per frame the engine draws
state = {'game': None, 'apply_ms': 0.0, 'prewarm_frames': 0}


class EngineProxy:
    """Wraps the graphics engine: notes the gun / window state of every drawn frame."""

    def __init__(self, engine):
        self._e = engine

    def _note(self, source):
        game = state['game']
        if game is None:
            return
        vm = game.viewmodel
        records.append((source, not vm.sway.is_hidden(), application.base.win.is_active(), vm.clip_key, next(k for k, g in GUNS.items() if g.name == vm.gun.name)))     # the key in GUNS

    def renderFrame(self):
        self._note('frame')
        self._e.renderFrame()

    def render_frame(self):
        self._note('dry-run')
        self._e.render_frame()

    def __getattr__(self, name):
        return getattr(self._e, name)


_orig_prewarm = vm_mod.Viewmodel.prewarm


def prewarm(self, frames=2):
    if not isinstance(application.base.graphicsEngine, EngineProxy):        # first call is inside create_game: install before it
        application.base.graphicsEngine = EngineProxy(application.base.graphicsEngine)
    _orig_prewarm(self, frames)


vm_mod.Viewmodel.prewarm = prewarm
_orig_apply = app_mod.Game._apply_gun


def apply_timed(self, name):
    t0 = pytime.perf_counter()
    _orig_apply(self, name)
    state['apply_ms'] = (pytime.perf_counter() - t0) * 1000


app_mod.Game._apply_gun = apply_timed

_orig_game_init = app_mod.Game.__init__


def game_init(self, *a, **k):
    _orig_game_init(self, *a, **k)
    state['game'] = self                                  # from here on every frame is recorded, including the dry-run frames of `create_game`


app_mod.Game.__init__ = game_init
game = create_game(vsync=True, size=(1280, 720), sound=False, draw=True, gun='m4')
mouse.locked = False
game.combat.require_locked_mouse = False
failures = []


def first_visible_clip(frames, gun):
    """Clip key of the first frame that shows `gun` on screen (gun shown AND window drawing); None if there was no such frame."""
    for source, shown, active, clip, name in frames:
        if name == gun and shown and active:
            return clip
    return 'never shown'


def check(title, frames, gun):
    clip = first_visible_clip(frames, gun)
    dry = sum(1 for r in frames if r[0] == 'dry-run' and r[4] == gun)
    ok = clip == 'draw'
    print(f'{title:34s} khung đầu tiên hiện súng chạy clip: {clip!s:12s} (khung chạy thử {dry})  {"ĐẠT" if ok else "TRƯỢT"}')
    if not ok:
        failures.append(title)


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.dts = []

    def update(self):
        self.dts.append(time.dt)
        try:
            next(self.gen)
        except StopIteration:
            print('\n' + ('ĐỦ BƯỚC: mọi kiểm tra đạt' if not failures else 'TRƯỢT: ' + ', '.join(failures)))
            sys.exit(1 if failures else 0)

    def wait(self, seconds):
        t0 = pytime.time()
        while pytime.time() - t0 < seconds:
            yield

    def run(self):
        yield from self.wait(2.0)                         # the draw clip finishes
        check('mở game (M4)', records, 'm4')
        for target in ('glock', 'm4', 'glock', 'm1014', 'm4', 'm1014', 'glock'):
            records.clear()
            self.dts.clear()
            game.request_gun(target)
            yield from self.wait(4.0)
            check(f'đổi sang {target}', records, target)
            big = sorted((round(d * 1000) for d in self.dts[3:] if d > 0.03), reverse=True)
            print(f'    đứng hình khi dựng súng: {state["apply_ms"]:.0f} ms; khung chậm > 30 ms (ms): {big[:6]}')


Script()
game.app.run()
