r"""G9: screenshots of the aimed (ADS) gun with the gun pushed off the screen centre by the mouse (shots\ads_<gun>_<yaw>.png) + a crop of the middle, to check that the rear and front sights stay lined up with the eye.
Checks nothing, only for viewing; the numbers are in tests/test_sights.py.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\ads_shots.py [--gun m4|glock] [--yaws 0,2.5,-2.5]
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
ap.add_argument('--gun', default='m4')
ap.add_argument('--size', default='1280x720')
ap.add_argument('--yaws', default='0,2.5,-2.5', help='độ lệch ngang của súng so với giữa màn hình (độ), dương = sang phải')
ap.add_argument('--pitch', type=float, default=0.0)
ap.add_argument('--relief', type=float, default=0.0, help='đặt thử ads_eye_relief (m); 0 = giữ số của súng')
ap.add_argument('--tag', default='')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
yaws = [float(v) for v in args.yaws.split(',')]

game = create_game(vsync=False, size=(W, H), sound=False, draw=False, gun=args.gun, map_name='pool')
mouse.locked = False
game.combat.require_locked_mouse = False
player = game.player
if args.relief > 0:
    from fps.core.sway import ads_target_for
    game.params.gun.ads_eye_relief = args.relief
    game.sway.ads_target = ads_target_for(game.params.gun)
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)


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

    def sec(self, seconds):
        t = time.time()
        while time.time() - t < seconds:
            yield

    def run(self):
        for _ in range(30):
            yield
        player.x, player.y, player.z = 0.0, 0.0, -13.5
        player.yaw, player.pitch = 0.0, 4.0
        player._apply_view()
        held_keys['right mouse'] = 1
        yield from self.sec(1.0)                                         # fully aimed
        for yaw in yaws:
            fl = player.free_look
            fl.offset = [yaw, args.pitch]
            fl.spring.x = [0.0, 0.0]
            fl.spring.v = [0.0, 0.0]
            for _ in range(25):
                fl.offset = [yaw, args.pitch]                              # hold it there (the head would slowly recentre)
                yield
            name = f'ads_{args.gun}{args.tag}_{yaw:+.1f}'.replace('+', 'p').replace('-', 'm')
            application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'{name}.png')))
            print('đã chụp', name, 'barrel_pose', tuple(round(v, 2) for v in game.viewmodel.barrel_pose))
        held_keys['right mouse'] = 0


Script()
game.app.run()
