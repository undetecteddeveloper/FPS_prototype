"""Muzzle flash on the viewmodel: stands in the darkest spot of the pool hall, holds the trigger and saves a picture before the shot and during the flash
(shots\\flash_<gun>_<tag>_off.png / _on.png). Prints the mean brightness of the lower-right quarter of the screen (where the gun is) for both pictures.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\measure\\flash_shots.py [--gun-name m4|glock] [--tag x] [--spot dark|beam]
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, PNMImage  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1280x720')
ap.add_argument('--gun-name', default='m4')
ap.add_argument('--tag', default='')
ap.add_argument('--spot', default='dark', choices=['dark', 'beam'])
ap.add_argument('--set', action='append', default=[], help='đổi một số trước khi chụp, vd --set gun.flash.light_power=3')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))

game = create_game(vsync=False, size=(W, H), sound=False, draw=False, gun=args.gun_name, map_name='pool')
mouse.locked = False
game.combat.require_locked_mouse = False
for item in args.set:
    from fps.core.params import resolve
    path, value = item.split('=')
    obj_path, attr = path.rsplit('.', 1)
    obj = resolve(game.params, obj_path)
    old = getattr(obj, attr)
    setattr(obj, attr, type(old)(float(value)))
    print(f'{path}: {old} -> {getattr(obj, attr)}')
if args.set:
    game.viewmodel.apply_light()
    game.light.apply_params()

SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)
SPOTS = {'dark': (-9.5, 0.0, -14.5, 200.0, 12.0), 'beam': (-4.0, 0.0, 0.0, 95.0, 8.0)}


def snap(name):
    tag = f'_{args.tag}' if args.tag else ''
    path = SHOTS / f'flash_{args.gun_name}{tag}_{name}.png'
    application.base.win.save_screenshot(Filename.from_os_specific(str(path)))
    img = PNMImage()
    img.read(Filename.from_os_specific(str(path)))
    w, h = img.get_x_size(), img.get_y_size()
    total, n = 0.0, 0
    for y in range(h // 2, h, 4):
        for x in range(w // 2, w, 4):
            total += img.get_gray(x, y)
            n += 1
    print(f'{name}: độ sáng trung bình góc dưới-phải = {total / n:.4f}')


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(0)

    def wait(self, n):
        for _ in range(n):
            yield

    def run(self):
        yield from self.wait(30)
        x, y, z, yaw, pitch = SPOTS[args.spot]
        p = game.player
        p.x, p.y, p.z = x, y, z
        p.vx = p.vz = 0.0
        p.yaw, p.pitch = yaw, pitch
        p._apply_view()
        yield from self.wait(60)                       # exposure settles
        snap('off')
        held_keys['left mouse'] = 1
        for _ in range(40):
            game.combat.pressed = True                 # semi-auto guns (Glock) fire on the press event, not on the held button
            yield
            if game.light.flash_on:
                yield                                  # the picture on screen is always the previous frame: wait one so it shows the flash
                snap('on')
                break
        else:
            print('KHÔNG thấy tia lửa bật trong 40 khung')
        held_keys['left mouse'] = 0


Script()
game.app.run()
