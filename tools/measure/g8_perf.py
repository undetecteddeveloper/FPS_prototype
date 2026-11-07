r"""G8: FPS of a gun in the real game (vsync off, 1366x768): standing, aimed, firing, reloading. Prints average / worst FPS of each scene (threshold 55).

Run: .venv\Scripts\python.exe -X utf8 tools\measure\g8_perf.py [--gun glock|m4]
"""
import argparse
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse, time  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='glock')
ap.add_argument('--map', default='pool', choices=('pool', 'flat'), help='pool = phòng hồ bơi (G9); flat = nền phẳng cũ để so')
ap.add_argument('--level', type=int, default=-1, help='mức đồ hoạ 0 Thấp / 1 Vừa / 2 Cao (mặc định: như game)')
ap.add_argument('--trace', action='store_true', help='in thời gian từng khung của giây đầu (tìm chỗ giật lúc mở game)')
ap.add_argument('--size', default='1366x768')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
game = create_game(vsync=False, size=(W, H), sound=False, draw=False, gun=args.gun, map_name=args.map)
if args.level >= 0:
    game.set_graphics(args.level, announce=False)
print(f'mức đồ hoạ: {game.graphics_level}, cửa sổ {W}x{H}')
mouse.locked = False
game.combat.require_locked_mouse = False
c = game.combat
dts = []


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        dts.append(time.dt)
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(0)

    def scene(self, name, seconds, setup=None):
        if setup:
            setup()
        dts.clear()
        t0 = pytime.time()
        while pytime.time() - t0 < seconds:
            yield
        if args.trace and name == 'khởi động':
            print('   từng khung (ms):', [round(x * 1000) for x in dts])
        d = sorted(dts[5:])
        avg = len(d) / max(sum(d), 1e-9)
        worst = 1.0 / max(d) if d else 0
        low1 = 1.0 / d[int(len(d) * 0.99)] if d else 0
        print(f'{name:14s} trung bình {avg:6.1f} FPS | 1% thấp {low1:6.1f} | tệ nhất {worst:6.1f}  {"ĐẠT" if avg >= 55 else "TRƯỢT"}')

    def run(self):
        yield from self.scene('khởi động', 1.0)
        yield from self.scene('đứng yên', 3.0)
        yield from self.scene('ngắm', 3.0, lambda: held_keys.__setitem__('right mouse', 1))
        held_keys['right mouse'] = 0

        def fire():
            c.weapon.auto = True
            c.weapon.mag = c.weapon.mag_size
            held_keys['left mouse'] = 1
        yield from self.scene('bắn liên tục', 3.0, fire)
        held_keys['left mouse'] = 0
        yield from self.scene('nạp đạn', 2.6, lambda: (setattr(c.weapon, 'mag', 3), c.request_reload()))
        yield from self.scene('chạy nước rút', 3.0, lambda: (held_keys.__setitem__('w', 1), held_keys.__setitem__('shift', 1)))


Script()
game.app.run()
