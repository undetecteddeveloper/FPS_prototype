r"""G10: water sound wiring in the real game with SOUND ON, using short dummy WAVs in a temp folder (nothing is copied into assets/): ambience loop, water banks,
wading steps instead of tile steps, landing in the water, a bullet on the water (after the sound travels), climbing out (drips, then tile steps again). Counts plays via Foley.counts.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\water_audio_check.py      (exit code = number of failures)
"""
import math
import shutil
import struct
import sys
import tempfile
import time as pytime
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

tmp = Path(tempfile.mkdtemp(prefix='fps_water_audio_'))
src = ROOT / 'assets' / 'sounds' / 'foley'
for f in src.glob('*.wav'):                       # the real groups, so the required banks load
    shutil.copy(f, tmp / f.name)
for group in ('wade', 'wade_run', 'wade_deep', 'water_land', 'water_hit', 'drip'):
    for i in range(2):
        with wave.open(str(tmp / f'{group}_{i}.wav'), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b''.join(struct.pack('<h', int(3000 * math.sin(k * 0.05))) for k in range(4410)))
amb = tmp / 'amb.wav'
shutil.copy(tmp / 'drip_0.wav', amb)

import fps.app as app_mod  # noqa: E402
from fps.weapon_data import GameParams  # noqa: E402


def params_with_temp_audio(**kw):
    gp = GameParams(**kw)
    gp.audio.folder, gp.audio.ambience_file = str(tmp), str(amb)
    return gp


app_mod.GameParams = params_with_temp_audio          # create_game builds its GameParams through this name
from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

game = create_game(vsync=False, size=(800, 450), sound=True, draw=False, map_name='pool')
mouse.locked = False
game.combat.require_locked_mouse = False
fails = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        fails.append(name)


class S(Entity):
    def __init__(self):
        super().__init__()
        self.g = self.run()

    def update(self):
        try:
            next(self.g)
        except StopIteration:
            shutil.rmtree(tmp, ignore_errors=True)
            sys.exit(len(fails))

    def sec(self, s):
        t = pytime.time()
        while pytime.time() - t < s:
            yield

    def run(self):
        yield from self.sec(0.5)
        f, p = game.foley, game.player
        check('ambience loop playing', game.ambience is not None and game.ambience.status() == game.ambience.PLAYING)
        check('water banks loaded', all(n in f.banks for n in ('wade', 'wade_run', 'wade_deep', 'water_land', 'water_hit', 'drip')))
        p.x, p.y, p.z, p.yaw = 0.0, game.pool.data.pool_floor, -8.0, 90.0
        p._apply_view()
        game._feet = (p.x, p.z)
        held_keys['w'] = 1
        yield from self.sec(2.0)
        held_keys['w'] = 0
        check('wading plays water steps, no tile steps', f.counts['wade'] + f.counts['wade_run'] >= 2 and f.counts['step_walk'] + f.counts['step_run'] == 0,
              f"wade {f.counts['wade']}, run {f.counts['wade_run']}, gạch {f.counts['step_walk'] + f.counts['step_run']}")
        p.x, p.y, p.z = -3.0, game.pool.data.pool_floor + 1.2, -8.0
        p.vy = 0.0
        p.on_ground = False
        yield from self.sec(1.0)
        check('landing in the water plays the splash', f.counts['water_land'] >= 1, f"{f.counts['water_land']}")
        game.pool.water.splash((1.0, game.pool.water.y, -6.0), 12.0)
        yield from self.sec(0.4)
        check('a bullet on the water plays the water hit (after the sound travelled 12 m)', f.counts['water_hit'] == 1, f"{f.counts['water_hit']}")
        p.x, p.y, p.z, p.yaw = 0.0, game.pool.data.pool_floor, -10.0, 180.0      # walk south up the steps onto the deck
        p.on_ground = True
        p._apply_view()
        game._feet = (p.x, p.z)
        held_keys['w'] = 1
        yield from self.sec(2.5)
        held_keys['w'] = 0
        check('climbing out drips, then the deck has tile steps again', f.counts['drip'] >= 1 and f.counts['step_walk'] + f.counts['step_run'] >= 1,
              f"drip {f.counts['drip']}, gạch {f.counts['step_walk'] + f.counts['step_run']}, y={p.y:.2f}")


S()
game.app.run()
