r"""After a reload the gun must act again when it is back in place (Clip.settle), not when the clip ends 0.5-0.75 s later (user report 7/11/2026: "I cannot shoot / swap / aim for ~1.5 s
after the reload animation"). In the REAL game with real input, for both guns and both reload kinds:
  - Handling lets go at settle (within 0.12 s), well before the clip end;
  - holding fire / aim at that moment: the first shot and the aim start within 0.1 s;
  - the clip's tail (hands settling) is still playing then, ends by itself, and leaves the gun in the ready pose (Glock: only the right magazine node shown);
  - a swap request right then is accepted and the other gun is drawn; a shot during the tail works.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\reload_check.py [--gun m4|glock]      (exit code = number of failures)
"""
import argparse
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='m4')
args = ap.parse_args()
game = create_game(vsync=False, size=(800, 450), sound=False, draw=False, gun=args.gun, map_name='pool')
mouse.locked = True
c, p = game.combat, game.player
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
        yield from self.sec(2.0)
        gun = game.params.gun
        for kind, mag in (('reload', 5), ('reload_empty', 0)):
            clip = gun.clips[kind]
            speed = gun.reload.speed
            want_ready = clip.settle_time / speed
            end = clip.duration / speed
            c.weapon.mag, c.weapon.reserve = mag, 90
            p.ads_amount = 0.0
            t0 = pytime.perf_counter()
            c.request_reload()
            t_ready = None
            while t_ready is None and pytime.perf_counter() - t0 < end + 1.0:
                yield
                if pytime.perf_counter() - t0 > 0.1 and not c.handling.busy:
                    t_ready = pytime.perf_counter() - t0
            check(f'{gun.name} {kind}: the gun is free at settle, {end - (t_ready or 0):.2f} s before the clip ends', t_ready is not None and abs(t_ready - want_ready) < 0.12 and end - t_ready > 0.4,
                  f'ready {t_ready if t_ready is None else round(t_ready, 2)} s, expected {want_ready:.2f} s, clip end {end:.2f} s')
            vm = game.viewmodel
            check(f'{gun.name} {kind}: the tail of the clip is still playing', vm._tail_left is not None and vm._tail_left > 0.2 and vm.clip_key == kind,
                  f'tail left {vm._tail_left}, clip {vm.clip_key}')
            shots0 = c.shots_fired
            held_keys['right mouse'] = 1
            held_keys['left mouse'] = 1
            c.pressed = True
            t1 = pytime.perf_counter()
            first_shot = first_ads = None
            while (first_shot is None or first_ads is None) and pytime.perf_counter() - t1 < 1.0:
                yield
                c.pressed = True
                if first_shot is None and c.shots_fired > shots0:
                    first_shot = pytime.perf_counter() - t1
                if first_ads is None and p.ads_amount > 0.05:
                    first_ads = pytime.perf_counter() - t1
            held_keys['right mouse'] = 0
            held_keys['left mouse'] = 0
            check(f'{gun.name} {kind}: fire and aim work at once', first_shot is not None and first_shot < 0.1 and first_ads is not None and first_ads < 0.1,
                  f'shot after {first_shot}, aim after {first_ads}')
            yield from self.sec(end - want_ready + 0.6)                       # the tail (and the fire clip, Glock) play out
            check(f'{gun.name} {kind}: afterwards the gun rests in the ready pose', vm._tail_left is None and vm.clip_key is None and vm._fade is None,
                  f'tail {vm._tail_left}, clip {vm.clip_key}')
            if vm.mag_groups:
                check(f'{gun.name} {kind}: only the seated magazine is shown', vm._mags_state in ('rest', 'locked'), f'state {vm._mags_state}')
            # swap right at the moment the gun is free
            c.weapon.mag, c.weapon.reserve = mag, 90
            c.request_reload()
            while c.handling.busy or p.ads_amount > 0.0:
                yield
            other = 'glock' if game.gun_name == 'm4' else 'm4'
            was = game.gun_name
            game.request_gun(other)
            accepted = game._pending_gun == other
            yield from self.sec(3.0)
            check(f'{gun.name} {kind}: a swap request right when the gun is free is accepted and the other gun is drawn', accepted and game.gun_name == other and not c.handling.busy,
                  f'pending {game._pending_gun}, gun {game.gun_name}')
            game.request_gun(was)
            yield from self.sec(3.0)
            gun = game.params.gun


S()
game.app.run()
