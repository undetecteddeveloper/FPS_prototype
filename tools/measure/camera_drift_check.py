r"""9/11/2026: the camera must not drift toward the crosshair by itself. Checks in the REAL game (opens a window, runs the real Game.update): with the gun pushed off the screen centre in
eight directions the camera stays still (standing and walking), the gun stays where it was pushed, the mouse still turns the camera once it goes past the free zone, and aiming turns
the camera ONCE (the zone shrinks) and then stops. Prints PASS / FAIL per check and exits with the number of failures.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\camera_drift_check.py [--gun m4|glock|m1014]
"""
import argparse
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='m4')
args = ap.parse_args()
game = create_game(vsync=False, size=(800, 450), sound=False, draw=False, map_name='flat', gun=args.gun)     # the flat map: nothing to walk into
mouse.locked = False
game.combat.require_locked_mouse = False
player = game.player
game._update_focus = lambda dt: None          # the checks click and hold keys by code: another window taking the focus must not drop them (G16 focus guard)
failures = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        failures.append(name)


def wait(seconds):
    t_end = pytime.time() + seconds
    while pytime.time() < t_end:
        yield


def view():
    return player.yaw, player.pitch


def delta(a, b):
    dy = (b[0] - a[0] + 180.0) % 360.0 - 180.0
    return math.hypot(dy, b[1] - a[1])


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(len(failures))

    def run(self):
        for _ in range(5):
            yield
        fa = game.params.gun.free_aim
        check('the head-chases-the-gun rates are 0 by default', fa.recenter_idle == 0.0 and fa.recenter_move == 0.0, f'{fa.recenter_idle} / {fa.recenter_move}')
        # the gun's own start-up draw clip may still be running: wait it out (a reload / draw narrows the zone and would turn the camera once, on purpose)
        yield from wait(2.5)
        zy, zp = fa.zone_yaw * fa.zone_soft, fa.zone_pitch * fa.zone_soft
        directions = {'phải': (0.8 * zy, 0.0), 'trái': (-0.8 * zy, 0.0), 'lên': (0.0, 0.8 * zp), 'xuống': (0.0, -0.8 * zp),
                      'phải-lên': (0.6 * zy, 0.6 * zp), 'trái-lên': (-0.6 * zy, 0.6 * zp), 'phải-xuống': (0.6 * zy, -0.6 * zp), 'trái-xuống': (-0.6 * zy, -0.6 * zp)}
        for walking in (False, True):
            for name, (yaw, pitch) in directions.items():
                player.free_look.reset()
                player.yaw, player.pitch = 30.0, 0.0
                player._apply_view()
                player.free_look.offset = [yaw, pitch]
                player.x, player.z = 0.0, -8.0
                held_keys['w'] = 1 if walking else 0
                yield from wait(0.15)                                     # the hand spring settles on the offset; only then compare
                start = view()
                offset0 = list(player.free_look.offset)
                yield from wait(3.0)
                moved = delta(start, view())
                kept = math.hypot(player.free_look.offset[0] - offset0[0], player.free_look.offset[1] - offset0[1])
                check(f'{"walking" if walking else "standing"}, crosshair {name}: the camera stays still for 3 s and the gun stays put', moved < 0.02 and kept < 0.02,
                      f'camera {moved:.4f} deg, gun {kept:.4f} deg')
        held_keys['w'] = 0

        # the mouse still turns the camera once the gun is past the free zone (mouse units = window heights: 0.2 = 9 deg at the default sensitivity)
        player.free_look.reset()
        player.yaw, player.pitch = 0.0, 0.0
        player._apply_view()
        yield from wait(0.2)
        start = view()
        sens = game.params.player.mouse_sensitivity
        for _ in range(10):
            player.look(0.2, 0.0)                                        # 0.2 x 45 = 9 deg per frame, ten frames: a flick of 90 deg in total
            yield
        turned = (player.yaw - start[0] + 180.0) % 360.0 - 180.0
        want = 10 * 0.2 * sens
        check('past the zone the mouse still turns the camera (the mouse turn minus the room the gun had left)', want - fa.zone_yaw - 0.5 <= turned <= want + 0.01, f'camera {turned:.1f} deg of {want:.1f} deg, zone {fa.zone_yaw:.0f}')

        # aiming shrinks the zone: the camera turns ONCE toward where the gun points, then stays
        player.free_look.reset()
        player.yaw, player.pitch = 0.0, 0.0
        player._apply_view()
        player.free_look.offset = [0.9 * zy, 0.0]
        held_keys['right mouse'] = 1
        trace = []
        for _ in range(14):
            yield from wait(0.2)
            trace.append(round(player.yaw, 3))
        print('  yaw every 0.2 s while aiming:', trace, 'ads', round(player.ads_amount, 3), 'zone scale', round(player.free_look.scale, 4), 'offset', [round(v, 3) for v in player.free_look.offset])
        a = view()                                                       # 2.8 s after the aim button went down: the quick turn (about 0.5 s, see the trace) is long over
        yield from wait(2.0)
        b = view()
        check('aiming: the camera turns once, then stays (no slow drift afterwards)', delta(a, b) < 0.02 and a[0] > 0.0, f'after 2.8 s {a[0]:.2f} deg, 2 s later {delta(a, b):.4f} deg more')
        held_keys['right mouse'] = 0
        yield


Script()
game.app.run()
