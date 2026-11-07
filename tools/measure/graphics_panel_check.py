r"""G10: the F2 graphics panel in the real game: opens and frees the mouse, anti-aliasing 2x / 4x rebuilds the lens with REAL multisample buffers (the gun moves to the new buffer),
every row changes and cycles back, the preset row keeps the anti-aliasing, Esc closes and saves (to a temp file, not the user's). Screenshots shots\g10_panel.png, g10_aa_off/4x.png.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\graphics_panel_check.py      (exit code = number of failures)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
import fps.app as app_mod  # noqa: E402
import tempfile  # noqa: E402
app_mod.USER_GRAPHICS = Path(tempfile.gettempdir()) / 'fps_graphics_panel_check.json'       # never overwrite the player's own settings
from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, time  # noqa: E402

from fps.core.graphics import OPTIONS  # noqa: E402

game = create_game(vsync=False, size=(1280, 720), sound=False, draw=False, map_name='pool')
SHOTS = ROOT / 'shots'
fails = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        fails.append(name)


def snap(name):
    application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'g10_{name}.png')))


class S(Entity):
    def __init__(self):
        super().__init__()
        self.g = self.run()
        self.dts = []

    def update(self):
        self.dts.append(time.dt)
        try:
            next(self.g)
        except StopIteration:
            sys.exit(len(fails))

    def frames(self, n):
        for _ in range(n):
            yield

    def run(self):
        yield from self.frames(30)
        p = game.player
        p.x, p.y, p.z, p.yaw, p.pitch = 3.0, -1.37, 5.0, 75.0, 0.0
        p._apply_view()
        yield from self.frames(20)
        snap('aa_off')
        game.input('f2')
        yield from self.frames(10)
        panel = game.gfx_panel
        check('F2 opens the panel and frees the mouse', panel.is_open and p.ui_open and not __import__('ursina').mouse.locked)
        snap('panel')
        # anti-aliasing: Off -> 2x -> 4x, with real multisample buffers
        for want in (2, 4):
            t0 = pytime.perf_counter()
            panel.change(1, row=1)
            ms = (pytime.perf_counter() - t0) * 1000
            self.dts.clear()
            yield from self.frames(15)
            buf = game.lens.scene_buffer
            got = buf.get_fb_properties().get_multisamples()
            check(f'anti-aliasing {want}x: the scene buffer has {want} samples, switch is quick', got >= want and game.gfx.aa == want and ms < 300,
                  f'mẫu {got}, đổi {ms:.0f} ms, khung chậm nhất sau đó {max(self.dts) * 1000:.0f} ms')
            vm = game.viewmodel
            check(f'... the gun draws into the new buffer ({want}x)', vm.output == buf and vm.region.is_active())
        game.input('f2')
        yield from self.frames(20)
        snap('aa_4x')
        game.input('f2')
        yield from self.frames(5)
        # every other row changes and comes back
        for i, (field, label, choices) in enumerate(OPTIONS):
            if field in ('aa', 'preset'):
                continue
            before = getattr(game.gfx, field)
            panel.change(1, row=i)
            yield from self.frames(3)
            after = getattr(game.gfx, field)
            for _ in range(len(choices) - 1):
                panel.change(1, row=i)
            yield from self.frames(3)
            check(f'row "{label}" changes and cycles back', after != before and getattr(game.gfx, field) == before)
        panel.change(1, row=0)                                    # preset: Cao -> Thấp
        yield from self.frames(5)
        check('row "Mức chung" applies a preset (keeps anti-aliasing)', game.graphics_level == 0 and game.gfx.aa == 4, f'level {game.graphics_level}, aa {game.gfx.aa}')
        panel.change(1, row=0)
        panel.change(1, row=0)
        game.input('escape')
        yield from self.frames(5)
        check('Esc closes, locks the mouse, saves the file', not panel.is_open and not p.ui_open and app_mod.USER_GRAPHICS.exists())
        print('saved:', app_mod.USER_GRAPHICS.read_text(encoding='utf-8').replace('\n', ' '))
        # back to off for a fair look
        game.apply_graphics(type(game.gfx)(**{**game.gfx.__dict__, 'aa': 0}))
        yield from self.frames(10)
        check('anti-aliasing off again: plain buffer', game.lens.scene_buffer.get_fb_properties().get_multisamples() == 0)


S()
game.app.run()
