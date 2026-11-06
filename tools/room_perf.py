"""Phòng tập kín: đo FPS CÓ SO SÁNH XEN KẼ giữa bóng thật / không bóng / bóng giả trong CÙNG một lần chạy.

vsync tắt, 1366x768. Mỗi vòng: cho từng chế độ, đổi chế độ (shader đọc công tắc ở render), bỏ 15 khung, đo 90 khung.
Ba góc nhìn luân phiên giữa các vòng (dọc làn từ vạch bắn, ở 100 m, nhìn chéo sang tường). Báo trung vị thời gian khung
của từng chế độ (ít nhiễu hơn trung bình khi máy đang bận việc khác), FPS trung bình, 1% thấp nhất, và % chậm hơn "tắt bóng".
Cũng báo thời gian của khung đầu tiên (vẽ atlas bóng một lần).

Chạy (qua ổ khoá):  .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\room_perf.py [vòng]
"""
import statistics
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, mouse  # noqa: E402

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
MODES = (True, False, 'fake')
NAMES = {True: 'bóng thật', False: 'tắt bóng', 'fake': 'bóng giả'}
VIEWS = [((0, 0, 0), 0, 0), ((0, 0, 100), 0, 0), ((-4, 0, 30), 35, 5)]

game = create_game(vsync=False, size=(1366, 768), sound=False, draw=False)
mouse.locked = False
player = game.player
samples = {m: [] for m in MODES}
first_frames = []


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.cur = None

    def update(self):
        now = pytime.perf_counter()
        if self.last is not None:
            if self.cur is not None:
                samples[self.cur].append(now - self.last)
            elif len(first_frames) < 5:
                first_frames.append(now - self.last)
        self.last = now
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0)

    def run(self):
        for _ in range(120):
            yield
        for r in range(ROUNDS):
            pos, yaw, pitch = VIEWS[r % len(VIEWS)]
            player.position = pos
            player.yaw, player.pitch = yaw, pitch
            player._apply_view()
            order = MODES if r % 2 == 0 else MODES[::-1]           # đảo thứ tự mỗi vòng: khử ảnh hưởng của thứ tự
            for m in order:
                self.cur = None
                game.look.set_shadow_mode(m)
                for _ in range(15):
                    yield
                self.cur = m
                for _ in range(90):
                    yield
            self.cur = None


def report():
    print('\n=== FPS phòng tập: so sánh xen kẽ (vsync tắt, 1366x768) ===')
    print('khung đầu (gồm vẽ atlas bóng một lần):', ', '.join(f'{d * 1000:.0f} ms' for d in first_frames))
    base = statistics.median(samples[False])
    for m in MODES:
        d = sorted(samples[m])
        n = len(d)
        med = statistics.median(d)
        print(f'{NAMES[m]:10s} {n:5d} khung  trung vị {med * 1000:6.2f} ms ({1 / med:5.0f} FPS)   trung bình {n / sum(d):5.0f} FPS   '
              f'1% thấp nhất {1 / d[int(n * 0.99)]:5.0f}   chậm hơn tắt bóng {100 * (med / base - 1):+5.1f}%')
    if game.look.shadows:
        w, h = game.look.shadows.atlas_size
        print(f'atlas bóng {w}x{h}, số lượt vẽ: {game.look.shadows.render_count}')


Script()
game.app.run()
