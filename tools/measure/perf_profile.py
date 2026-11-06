"""Finds what costs frame time: runs one situation, then prints the most expensive Python functions (cProfile) and the rendering part (`render_frame`).

Run: .venv\\Scripts\\python.exe -X utf8 tools\\measure\\perf_profile.py idle|fire|ads_fire|reload [--seconds 6]
"""
import argparse
import cProfile
import io
import pstats
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('scene')
ap.add_argument('--seconds', type=float, default=6.0)
ap.add_argument('--top', type=int, default=28)
args = ap.parse_args()

game = create_game(vsync=False, size=(1366, 768), sound=False, draw=False)
mouse.locked = False
game.combat.require_locked_mouse = False
game.combat.weapon.reserve = 99999
profiler = cProfile.Profile()


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            profiler.disable()
            s = io.StringIO()
            pstats.Stats(profiler, stream=s).strip_dirs().sort_stats('tottime').print_stats(args.top)
            print(f'\n=== {args.scene}: {self.frames} khung trong {self.elapsed:.2f} s = {self.frames / self.elapsed:.1f} FPS, '
                  f'{1000 * self.elapsed / self.frames:.2f} ms/khung ===')
            print(s.getvalue())
            sys.exit(0)

    def run(self):
        for _ in range(60):
            yield
        if args.scene in ('fire', 'ads_fire'):
            held_keys['left mouse'] = 1
        if args.scene == 'ads_fire':
            held_keys['right mouse'] = 1
        for _ in range(30):
            yield
        self.frames = 0
        start = pytime.perf_counter()
        profiler.enable()
        while pytime.perf_counter() - start < args.seconds:
            if args.scene in ('fire', 'ads_fire') and game.combat.weapon.mag < 3:
                game.combat.weapon.mag = game.params.gun.magazine
            if args.scene == 'reload' and not game.combat.handling.busy:
                game.combat.weapon.mag = 20
                game.combat.request_reload()
            self.frames += 1
            yield
        self.elapsed = pytime.perf_counter() - start


Script()
game.app.run()
