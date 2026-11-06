"""Chụp ảnh các tư thế / vị trí tiêu biểu vào shots\\bc_*.png để so với ảnh chụp Bodycam. Không kiểm gì, chỉ để nhìn.

Chạy: .venv\\Scripts\\python.exe -X utf8 tools\\measure\\bodycam_shots.py [--size 1366x768]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1366x768')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))

game = create_game(vsync=False, size=(W, H), sound=False, draw=False)
mouse.locked = False
game.combat.require_locked_mouse = False
player = game.player
SHOTS = ROOT / 'shots'


def snap(name):
    application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'bc_{name}.png')))


def place(pos, yaw=0.0, pitch=0.0):
    player.position = pos
    player.yaw, player.pitch = yaw, pitch
    player.vx = player.vz = 0.0
    player._apply_view()


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

    def run(self):
        yield from self.wait(30)
        place((0, 0, 0))
        yield from self.wait(90)
        snap('hip')                                     # đứng dưới vạch bắn, nhìn dọc làn
        place((-5, 0, 15), 30, 0)
        yield from self.wait(90)
        snap('under_lamp')                              # dưới đèn, nhìn chéo
        place((9, 0, 30), -60, 5)
        yield from self.wait(120)
        snap('dark_gap')                                # sát tường, giữa hai đèn
        place((0, 0, 20), 0, -30)
        yield from self.wait(90)
        snap('look_lamp')                               # ngước nhìn đèn
        place((0, 0, 0))
        held_keys['right mouse'] = 1
        yield from self.wait(60)
        snap('ads')
        held_keys['left mouse'] = 1
        yield from self.wait(24)
        snap('ads_fire')
        held_keys['left mouse'] = 0
        held_keys['right mouse'] = 0
        yield from self.wait(40)
        place((3, 0, 8), 10, 0)
        held_keys['left mouse'] = 1
        yield from self.wait(22)
        snap('hip_fire')
        held_keys['left mouse'] = 0
        yield from self.wait(30)
        game.combat.weapon.mag = 10
        game.combat.request_reload()
        yield from self.wait(70)
        snap('reload_mag_out')
        yield from self.wait(60)
        snap('reload_mag_in')
        yield from self.wait(150)
        game.combat.handling.cancel()
        place((0, 0, 40))
        held_keys['w'], held_keys['shift'] = 1, 1
        yield from self.wait(45)
        snap('sprint')
        held_keys['w'], held_keys['shift'] = 0, 0
        place((0, 0, 40))
        for i in range(14):                             # cú xoay nhanh sang phải
            player.look(0.05, 0.0)
            yield
        snap('turn')
        place((-1, 0, 2))
        player.free_look.reset()
        yield from self.wait(20)
        sens = game.params.player.mouse_sensitivity
        for i in range(30):                             # chuột sang trái, chậm: súng sang trái, màn hình đứng yên
            player.look(-11.0 / 30 / sens, 2.0 / 30 / sens)
            yield
        yield from self.wait(20)
        snap('free_left')
        place((-1, 0, 2))
        player.free_look.reset()
        yield from self.wait(5)
        for i in range(30):
            player.look(11.0 / 30 / sens, -3.0 / 30 / sens)
            yield
        yield from self.wait(20)
        snap('free_right')


Script()
game.app.run()
