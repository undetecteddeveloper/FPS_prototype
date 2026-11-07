r"""G10: the water sounds in the REAL game with sound on and the real files (assets/sounds/foley/wade_0.wav, water_land_0.wav, assets/sounds/pool_ambience.wav):
  - the room tone loops; wading plays the ONE wading recording instead of tile steps; jumping in plays the water landing; back on the deck the tile steps return;
  - the calibration: the same recording is played higher and lighter in the shallows, lower and fuller at chest depth, and quicker / louder when running;
  - the groups the user removed (water_hit, drip, wade_run, wade_deep) no longer exist.
Reads the playback rate and volume of each sound that Foley plays (Foley.last_sound). No file is written.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\water_audio_check.py      (exit code = number of failures)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

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
            sys.exit(len(fails))

    def sec(self, s):
        t = pytime.time()
        while pytime.time() - t < s:
            yield

    def run(self):
        yield from self.sec(0.5)
        f, p, a, d = game.foley, game.player, game.params.audio, game.pool.data
        check('room tone loops', game.ambience is not None and game.ambience.status() == game.ambience.PLAYING and game.ambience.get_loop())
        check('wading and landing banks loaded, removed groups gone', 'wade' in f.banks and 'water_land' in f.banks and not any(n in f.banks for n in ('water_hit', 'drip', 'wade_run', 'wade_deep')))
        results = {}
        for tag, y, z, run in (('shallow walk', d.pool_floor, -8.0, False), ('chest walk', d.water_y - d.wade_depth + 0.02, 0.9, False), ('shallow run', d.pool_floor, -8.0, True)):
            n0 = f.counts['wade']
            tiles0 = f.counts['step_walk'] + f.counts['step_run']
            play_rates, volumes = [], []
            original_play = f.play

            def spy(name, volume, pitch=1.0, pan=0.0, fit_hz=0.0, _orig=original_play, _r=play_rates, _v=volumes):
                if name == 'wade':
                    _r.append(pitch)
                    _v.append(volume)
                _orig(name, volume, pitch, pan, fit_hz)
            f.play = spy
            p.x, p.y, p.z, p.yaw = -4.0, y, z, 90.0
            p.vx = p.vz = 0.0
            p._apply_view()
            game._feet = (p.x, p.z)
            held_keys['w'] = 1
            held_keys['shift'] = 1 if run else 0
            yield from self.sec(1.8)
            held_keys['w'] = 0
            held_keys['shift'] = 0
            f.play = original_play
            tiles = f.counts['step_walk'] + f.counts['step_run'] - tiles0
            results[tag] = (len(play_rates), sum(play_rates) / max(len(play_rates), 1), sum(volumes) / max(len(volumes), 1), tiles)
            yield from self.sec(0.3)
        for tag, (n, rate, vol, tiles) in results.items():
            print(f'   {tag:13s}: {n} wading sounds, mean playback rate {rate:.2f}, mean volume {vol:.3f}, tile steps {tiles}')
        check('wading plays the one recording and no tile steps', all(r[0] >= 2 and r[3] == 0 for r in results.values()), str({k: (v[0], v[3]) for k, v in results.items()}))
        sh, ch, run = results['shallow walk'], results['chest walk'], results['shallow run']
        check('calibration: higher and lighter in the shallows than at chest depth', sh[1] > ch[1] + 0.12 and sh[2] < ch[2] * 0.85, f'rate {sh[1]:.2f} vs {ch[1]:.2f}, volume {sh[2]:.3f} vs {ch[2]:.3f}')
        check('calibration: running is quicker and louder than walking at the same depth', run[1] > sh[1] * 1.15 and run[2] > sh[2], f'rate {run[1]:.2f} vs {sh[1]:.2f}, volume {run[2]:.3f} vs {sh[2]:.3f}')
        # jump into the water
        land0 = f.counts['water_land']
        p.x, p.y, p.z, p.yaw = -3.0, d.pool_floor + 1.2, -8.0, 0.0
        p.vy = 0.0
        p.on_ground = False
        p._apply_view()
        yield from self.sec(1.0)
        check('landing in the water plays the water landing', f.counts['water_land'] == land0 + 1, f"{f.counts['water_land'] - land0}")
        # out of the water: tile steps again
        p.x, p.y, p.z, p.yaw = 0.0, d.pool_floor, -10.0, 180.0
        p.on_ground = True
        p._apply_view()
        game._feet = (p.x, p.z)
        tiles0 = f.counts['step_walk'] + f.counts['step_run']
        held_keys['w'] = 1
        yield from self.sec(2.5)
        held_keys['w'] = 0
        check('back on the deck the tile steps return', f.counts['step_walk'] + f.counts['step_run'] > tiles0 and p.y == 0.0, f'y={p.y:.2f}')


S()
game.app.run()
