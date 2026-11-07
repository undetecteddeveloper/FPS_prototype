"""G9: screenshots of the pool hall from fixed spots (shots\\g9_<name>.png), to compare with the reference photo and to tune light / water. Checks nothing, only for viewing.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\measure\\pool_shots.py [--size 1280x720] [--only spawn,east] [--gun] [--ring]
Views: spawn (looking along the pool like the photo), down (water at the feet), east (toward the windows), west, stairs (north end: stairs + handrails), pool (standing in the water),
ceiling, corner (SW corner in the shade), water (close look at the surface). --gun keeps the gun in the picture; --ring drops bullet rings on the water first.
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
from ursina import Entity, application, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1280x720')
ap.add_argument('--only', default='')
ap.add_argument('--gun', action='store_true')
ap.add_argument('--ring', action='store_true')
ap.add_argument('--holes', action='store_true', help='bắn một chùm đạn vào tường phía trước trước khi chụp (xem lỗ đạn)')
ap.add_argument('--gun-name', default='m4')
ap.add_argument('--tag', default='')
ap.add_argument('--exposure', type=float, default=0.0, help='nhân thêm vào phơi sáng (xem vùng tối); 0 = giữ mặc định')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
only = set(filter(None, args.only.split(',')))

t0 = time.time()
game = create_game(vsync=False, size=(W, H), sound=False, draw=False, gun=args.gun_name, map_name='pool')
print(f'dựng game: {time.time() - t0:.1f} s')
mouse.locked = False
game.combat.require_locked_mouse = False
player = game.player
if args.exposure > 0:
    game.params.look.exposure = args.exposure
if not args.gun:
    game.viewmodel.root.hide()
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)

# name: (x, y, z, yaw, pitch)   yaw 0 looks +z (north), 90 looks +x (east, the windows); positive pitch looks DOWN
VIEWS = {
    'spawn': (0.0, 0.0, -13.5, 0.0, 0.0),
    'down': (0.0, 0.0, -13.5, 0.0, 28.0),
    'east': (-5.0, 0.0, -2.0, 80.0, -4.0),
    'west': (6.5, 0.0, 0.0, 262.0, -2.0),
    'stairs': (0.0, 0.0, 4.0, 0.0, -2.0),
    'pool': (0.0, -0.62, -6.0, 0.0, 6.0),
    'ceiling': (-4.0, 0.0, -9.0, 20.0, -62.0),
    'corner': (8.0, 0.0, 12.0, 215.0, 0.0),
    'water': (-6.8, 0.0, -2.0, 70.0, 38.0),
    'dark_corner': (-9.5, 0.0, -14.5, 200.0, -50.0),      # the darkest spot of the room (SW corner, no beam reaches it), looking up at the tiles: the gun must not glow there
    'window_close': (9.35, 0.0, -3.5, 84.0, 3.0),         # at the east wall in front of a window, as close as the player can get (0.3 m body radius)
    'window_side': (9.35, 0.0, -0.4, 40.0, 4.0),          # beside a window, looking along the wall at the reveal (the wall thickness)
    'win_a': (7.0, 0.0, -8.0, 100.0, 4.0),                # a window frame seen from inside at normal distance, slightly from the side
    'win_b': (8.6, 0.0, -6.8, 128.0, 0.0),                # close, looking along the wall toward the next pier: the reveal of the window beyond
    'win_c': (9.3, 0.0, -9.0, 150.0, 24.0),               # looking down at the sill
    'win_d': (9.3, 0.0, -6.5, 20.0, -28.0),               # looking up at the lintel from beside the window
}


def snap(name):
    tag = f'_{args.tag}' if args.tag else ''
    application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'g9_{name}{tag}.png')))
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
        t = time.time()
        while time.time() - t < seconds:
            yield

    def run(self):
        yield from self.wait(30)
        for name, (x, y, z, yaw, pitch) in VIEWS.items():
            if only and name not in only:
                continue
            player.x, player.y, player.z = x, y, z
            player.vx = player.vz = 0.0
            player.yaw, player.pitch = yaw, pitch
            player._apply_view()
            if args.holes:
                from fps.game.combat import Bullet
                for k in range(-4, 5):                                     # a fan of bullets at the north wall: some land in the sun patch, some in the shade
                    b = Bullet((x, y + 1.5, z), (k * 9.0, 4.0 - abs(k) * 0.4, 300.0))
                    for _ in range(20):
                        if not game.combat._advance(b, 0.05, game.combat._boxes()):
                            break
            if args.ring and game.pool:
                for k in range(3):
                    game.pool.water.splash((x + 1.5 * k - 1.5, game.pool.pm.water[4], z + 4.0 + 1.2 * k), 10.0)
                yield from self.sec(0.7)
            yield from self.wait(25)
            snap(name)
            yield from self.wait(3)


Script()
game.app.run()
