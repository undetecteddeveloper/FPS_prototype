"""Measures FPS per play situation, with the same script for every version (vsync off).

Each situation: places the player and sets the view direction, skips a few frames for stability, then measures. Prints the average (frames / total time), the median and
the slowest 1% of frames, plus a TOTAL line as a weighted average. Exits with code 1 if the total is below the threshold or any situation is below its threshold.

Run (through the lock, so several games at once do not skew the measurements):
  .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\measure\\perf_scenarios.py [--size 1366x768] [--seconds 6]
"""
import argparse
import statistics
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--size', default='1366x768')
ap.add_argument('--seconds', type=float, default=6.0, help='giây đo cho mỗi tình huống')
ap.add_argument('--min-avg', type=float, default=60.0, help='ngưỡng trung bình toàn kịch bản')
ap.add_argument('--min-scene', type=float, default=55.0, help='ngưỡng trung bình của từng tình huống')
ap.add_argument('--sound', action='store_true', help='bật tiếng như game thật')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))

game = create_game(vsync=False, size=(W, H), sound=args.sound, draw=False)
mouse.locked = False
game.combat.require_locked_mouse = False
player = game.player
game.params.gun.reserve = 9999
game.combat.weapon.reserve = 9999

# (name, position, yaw, pitch, held keys, action each frame)
SCENES = [
    ('dứng yên, nhìn dọc làn', (0, 0, 0), 0, 0, {}, None),
    ('đứng dưới đèn, nhìn chéo tường', (-4, 0, 30), 35, 5, {}, None),
    ('nhìn thẳng vào tường gần', (9.5, 0, 25), 90, 0, {}, None),
    ('ngước nhìn đèn', (0, 0, 20), 0, -35, {}, None),
    ('đi bộ dọc làn', (-3, 0, 5), 0, 0, {'w': 1}, None),
    ('chạy nước rút dọc làn', (3, 0, 5), 0, 0, {'w': 1, 'shift': 1}, None),
    ('ngắm, đứng yên', (0, 0, 0), 0, 0, {'right mouse': 1}, None),
    ('bắn liên thanh từ hông', (0, 0, 0), 0, 0, {'left mouse': 1}, 'refill'),
    ('bắn liên thanh khi ngắm', (0, 0, 0), 0, 0, {'left mouse': 1, 'right mouse': 1}, 'refill'),
    ('nạp đạn', (0, 0, 0), 0, 0, {}, 'reload'),
    ('giữa phòng (100 m), nhìn dọc làn', (0, 0, 100), 0, 0, {}, None),
]
results = []


def release():
    for key in ('w', 'shift', 'right mouse', 'left mouse'):
        held_keys[key] = 0


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.sink = None

    def update(self):
        now = pytime.perf_counter()
        if self.last is not None and self.sink is not None:
            self.sink.append(now - self.last)
        self.last = now
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(report())

    def run(self):
        for _ in range(60):
            yield
        for name, pos, yaw, pitch, keys, action in SCENES:
            release()
            self.sink = None
            player.position = pos
            player.yaw, player.pitch = yaw, pitch
            player.vx = player.vz = 0.0
            player._apply_view()
            for key, value in keys.items():
                held_keys[key] = value
            for _ in range(30):
                yield
            samples = []
            self.sink = samples
            start = pytime.perf_counter()
            while pytime.perf_counter() - start < args.seconds:
                if action == 'refill' and game.combat.weapon.mag < 3:
                    game.combat.weapon.mag = game.params.gun.magazine
                if action == 'reload' and not game.combat.handling.busy:
                    game.combat.weapon.mag = max(0, game.combat.weapon.mag - 5)
                    game.combat.request_reload()
                if player.z > 190:          # back to the start when reaching the end of the lane
                    player.z = pos[2]
                yield
            self.sink = None
            results.append((name, samples))
        release()


def report() -> int:
    total_frames = sum(len(s) for _, s in results)
    total_time = sum(sum(s) for _, s in results)
    print(f'\n=== FPS theo tình huống ({W}x{H}, vsync tắt) ===')
    worst = 1e9
    for name, s in results:
        d = sorted(s)
        avg = len(d) / sum(d)
        worst = min(worst, avg)
        print(f'{name:36s} trung bình {avg:6.1f}   trung vị {1 / statistics.median(d):6.1f}   1% thấp nhất {1 / d[int(len(d) * 0.99)]:6.1f}')
    average = total_frames / total_time
    print(f'TỔNG: trung bình {average:.1f} FPS, tình huống thấp nhất {worst:.1f} FPS')
    ok = average >= args.min_avg and worst >= args.min_scene
    print('ĐẠT' if ok else f'TRƯỢT (ngưỡng tổng {args.min_avg}, ngưỡng tình huống {args.min_scene})')
    return 0 if ok else 1


Script()
game.app.run()
