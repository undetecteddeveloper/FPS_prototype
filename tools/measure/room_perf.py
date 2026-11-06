"""Closed range: measures FPS with INTERLEAVED COMPARISON between real shadows, no shadows and fake shadows within ONE run.

vsync off, 1366x768. Each round: for each mode, switch the mode (the shader reads the switch on render), skip 15 frames, measure 90 frames.
Three views alternate between rounds (down the lane from the firing line, at 100 m, looking diagonally at a wall). Reports the median frame time
of each mode (less noisy than the mean when the machine is busy with other work), the average FPS, the 1% low, and the % slower than "shadows off".
Also reports the time of the first frame (drawing the shadow atlas once).

Run (through the lock):  .venv\\Scripts\\python.exe -X utf8 tools\\with_game_lock.py .venv\\Scripts\\python.exe -X utf8 tools\\measure\\room_perf.py [rounds]
"""
import statistics
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
            order = MODES if r % 2 == 0 else MODES[::-1]           # reverse the order each round: cancels the effect of order
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
