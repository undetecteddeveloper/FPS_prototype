r"""Low-memory mode check (7/11/2026, fps/core/memplan.py): the reduced game really is reduced, still plays, and never overwrites what the user saved.

With saved graphics asking for 4x MSAA and the game built in low-memory mode:
  1. the lens buffer has NO MSAA, while `game.gfx` still says 4 (what F2 shows and saves);
  2. only the gun in hand is built; the second gun is built on the first switch and its draw clip then plays;
  3. the user choosing an anti-aliasing level in the F2 panel lifts the cap (his choice wins).
Uses temp copies of the settings files: the real user_graphics.json / user_params.json are never read or written.

Run: .venv\Scripts\python.exe -X utf8 tools\measure\lowmem_check.py        (exit code 1 if a check fails)
"""
import sys
import tempfile
import time as pytime
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

import fps.app as app_mod  # noqa: E402
from fps.core.graphics import GraphicsSettings, to_json  # noqa: E402
from main import create_game  # noqa: E402
from ursina import Entity, mouse  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='lowmem_check_'))
(tmp / 'g.json').write_text(to_json(GraphicsSettings(aa=4)), encoding='utf-8')
app_mod.USER_GRAPHICS = tmp / 'g.json'
app_mod.USER_PARAMS = tmp / 'no_such_params.json'

t0 = pytime.time()
game = create_game(vsync=False, size=(800, 450), sound=False, draw=True, gun='m4', map_name='pool', user_params=True, low_memory=True)
print(f'dựng game giảm tải: {pytime.time() - t0:.1f} s')
mouse.locked = False
game.combat.require_locked_mouse = False
failures = []


def check(title, ok, detail=''):
    print(f'{"ĐẠT " if ok else "TRƯỢT"} {title}  {detail}')
    if not ok:
        failures.append(title)


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
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
        yield from self.wait(2.0)
        check('saved settings keep 4x (what F2 shows and saves)', game.gfx.aa == 4, f'gfx.aa={game.gfx.aa}')
        check('the lens buffer has no MSAA in low-memory mode', game.lens.samples == 0, f'samples={game.lens.samples}')
        check('only the gun in hand is built at start-up', list(game._kits) == ['m4'], str(list(game._kits)))
        t0 = pytime.perf_counter()
        game.request_gun('glock')
        yield from self.wait(4.0)
        check('the second gun is built on the first switch and comes into hand', game.gun_name == 'glock' and 'glock' in game._kits, f'gun={game.gun_name} kits={list(game._kits)}')
        check('...and its draw clip has finished (the gun is ready)', game.combat.handling.phase.name == 'READY', f'phase={game.combat.handling.phase}')
        check('the cap still holds after the switch', game.lens.samples == 0, f'samples={game.lens.samples}')
        game.apply_graphics(replace(game.gfx, aa=2))
        check('choosing an anti-aliasing level in F2 lifts the cap', game.lens.samples == 2, f'samples={game.lens.samples}')
        game.apply_graphics(replace(game.gfx, aa=0))
        check('...and 0 works again', game.lens.samples == 0, f'samples={game.lens.samples}')
        print(f'(đổi súng + chờ: {pytime.perf_counter() - t0:.1f} s)')


Script()
game.app.run()
