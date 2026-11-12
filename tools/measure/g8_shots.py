"""G8: screenshots of the Glock in the real game (shots\\g8_*.png) for tuning hip_offset / rest pose / ADS / sprint and for the review folder.
Checks nothing, only for viewing.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\measure\\g8_shots.py [--size 1366x768] [--gun glock] [--only hip,ads]
Poses: hip, ads, fire (slide back), reload (several moments), empty (slide locked), sprint, draw.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1366x768')
ap.add_argument('--gun', default='glock')
ap.add_argument('--only', default='')
ap.add_argument('--relief', type=float, default=0.0, help='override GunData.ads_eye_relief (m) for the shots: a longer eye relief shows the sight picture smaller and clearer')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
only = set(filter(None, args.only.split(',')))

game = create_game(vsync=False, size=(W, H), sound=False, draw=False, gun=args.gun)
mouse.locked = False
game.combat.require_locked_mouse = False
player, combat, vm = game.player, game.combat, game.viewmodel
if args.relief > 0.0:
    from fps.core.sway import ads_target_for
    game.params.gun.ads_eye_relief = args.relief
    game.sway.ads_target = ads_target_for(game.params.gun)
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)
tag = args.gun + (f'_relief{args.relief:g}' if args.relief > 0.0 else '')


def want(name):
    return not only or name in only


def snap(name):
    application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'g8_{tag}_{name}.png')))
    print('đã chụp', name)


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            print('xong')
            sys.exit(0)

    def wait(self, n):
        for _ in range(n):
            yield

    def sec(self, seconds):
        """Wait in real seconds (the game runs uncapped here, so frame counts mean nothing for clips)."""
        t0 = time.time()
        while time.time() - t0 < seconds:
            yield

    def run(self):
        yield from self.wait(40)
        player.position = (0, 0, 0)
        player.yaw = player.pitch = 0.0
        player._apply_view()
        yield from self.wait(60)
        if want('hip'):
            snap('hip')
        if want('ads'):
            held_keys['right mouse'] = 1
            yield from self.wait(60)
            snap('ads')
            held_keys['left mouse'] = 1
            yield from self.wait(3)
            held_keys['left mouse'] = 0
            yield from self.wait(2)
            snap('ads_fire')
            held_keys['right mouse'] = 0
            yield from self.wait(40)
        if want('fire'):
            held_keys['left mouse'] = 1
            yield from self.wait(2)
            held_keys['left mouse'] = 0
            yield from self.wait(1)
            snap('fire')
            yield from self.wait(40)
        if want('reload'):
            combat.weapon.mag = min(9, combat.weapon.mag_size - 2)          # a full magazine cannot be reloaded
            combat.request_reload()
            for i in range(10):
                yield from self.sec(0.27)
                snap(f'reload{i}')
            yield from self.sec(1.0)
        if want('empty'):
            combat.weapon.mag = 0
            yield from self.wait(30)
            snap('empty')
            combat.request_reload()
            for i in range(10):
                yield from self.sec(0.33)
                snap(f'empty_reload{i}')
            yield from self.sec(1.0)
        if want('sprint'):
            held_keys['w'] = 1
            held_keys['shift'] = 1
            yield from self.wait(70)
            snap('sprint')
            held_keys['w'] = 0
            held_keys['shift'] = 0
            yield from self.wait(40)
        if want('draw'):
            combat.handling.start_draw()
            for i in range(5):
                yield from self.sec(0.2)
                snap(f'draw{i}')


Script()
game.app.run()
