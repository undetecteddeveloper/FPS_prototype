"""Phòng tập kín: chụp ảnh các góc nhìn bằng game thật vào shots\\room_*.png để xem tường, đèn, bóng, sàn gạch.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\measure\\room_shots.py [true|fake|off]   (chế độ bóng, mặc định theo LookData)
Ảnh: lane (nhìn dọc làn từ vạch bắn), side (tường bên), back (phía sau), pillar (sát cột), target (sát bia 10 m),
     z10 / z100 (đứng ở 10 m / 100 m nhìn xuôi), up (ngẩng nhìn trần), down (nhìn sàn gạch dưới chân), wallhit (lỗ đạn trên tường).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

MODES = {'true': True, 'fake': 'fake', 'off': False}
mode = MODES.get(sys.argv[1].lower()) if len(sys.argv) > 1 else None
suffix = '' if mode is None else f'_{sys.argv[1].lower()}'

game = create_game(vsync=False, sound=False, draw=False)
if mode is not None and game.look:
    game.look.set_shadow_mode(mode)
player = game.player
mouse.locked = False

VIEWS = [  # tên, vị trí người chơi, yaw, pitch
    ('lane', (0, 0, 0), 0, 0),
    ('side', (0, 0, 3), 90, 0),
    ('back', (2, 0, 5), 180, 0),
    ('pillar', (8.5, 0, 6), 60, 18),
    ('target', (-1.2, 0, 4.5), -15, 8),
    ('target25', (0.5, 0, 19.5), 22, 16),
    ('shadow50', (1.0, 0, 41.0), -22, 14),
    ('z10', (0, 0, 10), 0, 0),
    ('z100', (0, 0, 100), 0, 0),
    ('up', (0, 0, 2), 0, -55),
    ('down', (0, 0, 0), 20, 50),
]


def shot(name):
    out = ROOT / 'shots' / f'room_{name}{suffix}.png'
    out.parent.mkdir(exist_ok=True)
    application.base.win.saveScreenshot(Filename.from_os_specific(str(out)))
    print('ĐÃ CHỤP', out.name)


def place(pos, yaw, pitch):
    player.position = pos
    player.vx = player.vz = 0.0
    player.yaw, player.pitch = yaw, pitch
    player._apply_view()


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            if game.look and game.look.shadows:
                print('số lượt vẽ bản đồ bóng:', game.look.shadows.render_count)
            sys.exit(0)

    def run(self):
        for _ in range(20):
            yield
        for name, pos, yaw, pitch in VIEWS:
            place(pos, yaw, pitch)
            for _ in range(6):
                yield
            shot(name)
        # bắn vào tường phải (giữa hai cột) để thấy lỗ đạn trên tường
        place((6, 0, 5), 90, 0)
        for _ in range(4):
            yield
        shot('prefire')
        game.combat.require_locked_mouse = False
        game.combat.weapon.mag = 30
        held_keys['left mouse'] = 1
        for _ in range(12):
            yield
        held_keys['left mouse'] = 0
        for _ in range(10):
            yield
        imp = game.combat.last_impact
        print('lỗ đạn cuối:', None if imp is None else (tuple(round(c, 2) for c in imp.point), imp.normal, type(imp.owner).__name__))
        place((7, 0, 5), 90, 0)
        for _ in range(6):
            yield
        shot('wallhit')


Script()
game.app.run()
