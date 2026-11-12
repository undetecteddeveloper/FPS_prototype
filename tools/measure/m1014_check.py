r"""Benelli M1014 in the REAL game (opens a window): the traits that make it a shotgun, checked end to end. Prints PASS / FAIL per check and exits with the number of failures.

  - 9 pellets per shot inside the pattern cone, denser in the middle; one trigger pull = one shot, B does not switch to auto; the pellets lose speed in flight (drag)
  - the tube is loaded ONE shell at a time (a chain of cycles, rounds counted at each shell, the reserve falling with them); an empty gun with a full reserve plays the long clip (7 shells + the bolt);
    a short reserve loads what there is; a click while shells go in stops the reload and fires with the rounds already in; sprinting cancels
  - the reload sound plays once per shell (the user's first beat), the head glance stays down across the chain, the hand-held shell shows only during a reload
  - the last round leaves the bolt locked open; pulling the trigger on the empty gun starts the reload; the procedural draw lifts the gun from out of the frame

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\m1014_check.py
"""
import math
import os
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

from fps.core.spread import angle_between  # noqa: E402

game = create_game(vsync=False, size=(800, 450), sound=True, draw=False, gun='m1014')
mouse.locked = False
game.combat.require_locked_mouse = False
combat, player, vm = game.combat, game.player, game.viewmodel
game._update_focus = lambda dt: None          # the checks click and hold keys by code: another window taking the focus must not drop them (G16 focus guard)
failures = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        failures.append(name)


def wait(seconds):
    t_end = pytime.time() + seconds
    while pytime.time() < t_end:
        yield


def wait_ready(limit=15.0):
    t_end = pytime.time() + limit
    while combat.handling.busy and pytime.time() < t_end:
        yield


def click():
    combat.pressed = True


def reset_ammo(mag, reserve):
    combat.weapon.mag, combat.weapon.reserve = mag, reserve
    combat.weapon.cooldown = 0.0


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            print('xong')
            sys.stdout.flush()
            os._exit(len(failures))

    def run(self):
        for _ in range(10):
            yield
        g = game.params.gun
        w = combat.weapon
        yield from wait_ready()
        yield from wait(0.5)
        check('the M1014 is the gun in hand with 8 rounds (7 in the tube + 1 chambered) and 32 in reserve', game.gun_name == 'm1014' and w.mag == 8 and w.reserve == 32, f'{game.gun_name} {w.mag}+{w.reserve}')

        # --- the shot: 9 pellets, one pull one shot, B does nothing ---
        before_bullets, before_shots = len(combat.bullets), combat.shots_fired
        click()
        yield
        yield
        check('one click fires one shot of 9 pellets', combat.shots_fired == before_shots + 1 and w.mag == 7 and len(combat.bullets) >= before_bullets + 9 - 1,
              f'shots +{combat.shots_fired - before_shots}, mag {w.mag}, bullets +{len(combat.bullets) - before_bullets}')
        game.input('b')
        check('B does not turn the semi-auto shotgun into a full-auto one', w.auto is False)
        held_keys['left mouse'] = 1
        for _ in range(30):
            yield
        held_keys['left mouse'] = 0
        yield from wait(0.3)
        check('holding the trigger fires ONE shot only (semi-auto)', w.mag == 7 or w.mag == 6, f'mag {w.mag} (7 expected: the held trigger found the gun off cooldown once)')

        # --- the pattern: directions straight from Combat._fire ---
        combat.bullets.clear()
        origin, aim = (0.0, 1.6, 0.0), (0.0, 0.0, 1.0)
        radii, shots = [], 400
        for _ in range(shots):
            combat.bullets.clear()
            combat._fire(origin, aim, 0.0)
            for b in combat.bullets:
                speed = math.sqrt(sum(c * c for c in b.vel))
                radii.append(angle_between(tuple(c / speed for c in b.vel), aim))
        check('every pellet stays inside the pellet cone (+ the 0.01 degree the aim vector may differ)', max(radii) <= g.pellet_spread + 0.011, f'{len(radii)} pellets, widest {max(radii):.3f} deg of {g.pellet_spread}')
        uniform_mean = g.pellet_spread * 2.0 / 3.0                      # mean radius of a uniform disc
        mean = sum(radii) / len(radii)
        check('the pattern is denser in the middle than a uniform disc (centre bias)', mean < 0.93 * uniform_mean, f'mean radius {mean:.3f} deg, uniform disc {uniform_mean:.3f}')
        check('9 pellets per shot', len(radii) == 9 * shots, f'{len(radii)} / {9 * shots}')

        # --- drag: speed after 0.15 s of flight (a quarter of the speed is lost in ~0.16 s at 1.8 /s) ---
        combat.bullets.clear()
        combat._fire((0.0, 30.0, 0.0), aim, 0.0)                         # high above the floor: nothing to hit
        b = combat.bullets[0]
        v0 = math.sqrt(sum(c * c for c in b.vel))
        for _ in range(9):
            combat._advance(b, 1 / 60, [])
        v1 = math.sqrt(sum(c * c for c in b.vel))
        check('a pellet loses speed in flight (drag)', 0.70 < v1 / v0 < 0.80, f'{v1:.0f} / {v0:.0f} m/s after 0.15 s')
        combat.bullets.clear()

        # --- one shot fired (7 left): ONE shell with ReloadOne_type2 (the user's rule) ---
        reset_ammo(7, 20)
        foley = game.foley
        shell_before = foley.counts['m1014_shell']
        combat.request_reload()
        yield
        check('7 rounds left: the one-shell clip (ReloadOne_type2)', combat.handling.key == 'reload' and vm.gun.clips['reload'].anim.endswith('ReloadOne_type2'), str(combat.handling.key))
        shown = [n for n in vm.reload_props if not n.is_hidden()]
        check('the hand-held shell is drawn during a reload', len(shown) == len(vm.reload_props) > 0, f'{len(shown)} / {len(vm.reload_props)}')
        yield from wait_ready(10)
        yield from wait(0.5)
        check('one shell: 7 -> 8, the reserve 20 -> 19, one shell sound', w.mag == 8 and w.reserve == 19 and foley.counts['m1014_shell'] - shell_before == 1, f'{w.mag}+{w.reserve}, {foley.counts["m1014_shell"] - shell_before} sounds')
        check('the hand-held shell is hidden again afterwards', all(n.is_hidden() for n in vm.reload_props))

        # --- fired more (3 left): the long clip ReloadFull_type1, 5 shells, then it jumps to the closing of the bolt ---
        reset_ammo(3, 20)
        foley = game.foley
        shell_before = foley.counts['m1014_shell']
        slider_before = foley.counts['m1014_slider']
        glance = []
        combat.request_reload()
        t0 = pytime.time()
        yield
        check('3 rounds left: the long clip (ReloadFull_type1)', combat.handling.key == 'reload_empty' and vm.gun.clips['reload_empty'].anim.endswith('ReloadFull_type1'), str(combat.handling.key))
        while combat.handling.busy and pytime.time() - t0 < 20:
            if 0.9 < pytime.time() - t0:
                glance.append(game.head.glance)
            yield
        took = pytime.time() - t0
        yield from wait(0.5)
        check('five shells loaded: 3 -> 8 rounds, the reserve 20 -> 15', w.mag == 8 and w.reserve == 15, f'{w.mag}+{w.reserve}')
        check('the long clip is cut short when the gun is full (about 3.3 s, not the 4.2 s of the empty reload)', 2.0 < took < 3.9, f'{took:.1f} s')
        check('the reload sound plays once per shell (5) and the slider sound once', foley.counts['m1014_shell'] - shell_before == 5 and foley.counts['m1014_slider'] - slider_before == 1, f'{foley.counts["m1014_shell"] - shell_before} shells, {foley.counts["m1014_slider"] - slider_before} slider')
        mid = glance[int(len(glance) * 0.15):int(len(glance) * 0.6)]
        check('the head stays down through the clip (glance does not dip)', len(mid) > 20 and min(mid) > 0.6, f'min over the middle {min(mid) if mid else 0:.2f} of {len(glance)} samples')

        # --- interrupt by a click: keeps what is in, fires ---
        reset_ammo(3, 20)
        combat.request_reload()
        yield from wait(1.35)
        in_tube = w.mag
        click()
        yield
        yield
        check('a click while shells go in stops the reload and fires', not combat.handling.busy and w.mag == in_tube - 1 and in_tube >= 4, f'tube had {in_tube}, now {w.mag}, busy {combat.handling.busy}')
        yield from wait(0.6)

        # --- sprinting cancels ---
        reset_ammo(3, 20)
        combat.request_reload()
        yield from wait(0.3)
        held_keys['w'] = 1
        held_keys['shift'] = 1
        yield from wait(0.6)
        held_keys['w'] = 0
        held_keys['shift'] = 0
        check('sprinting cancels the reload', not combat.handling.busy and w.mag <= 4, f'mag {w.mag}')
        yield from wait(1.0)

        # --- empty gun: the long clip loads the whole tube and the bolt closes ---
        reset_ammo(0, 32)
        yield from wait(0.5)
        combat.request_reload()
        yield
        check('an empty gun with a full reserve plays the long empty clip', combat.handling.key == 'reload_empty', str(combat.handling.key))
        t0 = pytime.time()
        shell_before = foley.counts['m1014_shell']
        yield from wait_ready(25)
        took = pytime.time() - t0
        yield from wait(0.5)
        check('the long clip loads 8 rounds (7 shells + the chamber): 0 -> 8, the reserve 32 -> 24', w.mag == 8 and w.reserve == 24, f'{w.mag}+{w.reserve}')
        check('the empty reload took 4-7 s', 3.5 < took < 8.0, f'{took:.1f} s')
        check('7 shell sounds in the long clip', foley.counts['m1014_shell'] - shell_before == 7, f'{foley.counts["m1014_shell"] - shell_before}')

        # --- a short reserve: no phantom shells ---
        reset_ammo(0, 3)
        yield from wait(0.5)
        combat.request_reload()
        yield
        check('with 3 shells in reserve the long clip still runs (it stops after the 3 shells)', combat.handling.key == 'reload_empty', str(combat.handling.key))
        yield from wait_ready(15)
        yield from wait(0.5)
        check('the 3 shells go in, the reserve is 0', w.mag == 3 and w.reserve == 0, f'{w.mag}+{w.reserve}')

        # --- the last round: bolt locked open, the trigger on the empty gun reloads ---
        reset_ammo(1, 10)
        yield from wait(0.5)
        click()
        yield from wait(0.15)
        check('the last round: the check-the-chamber clip plays', vm.clip_key == 'fire_last' and w.mag == 0, f'{vm.clip_key}, mag {w.mag}')
        yield from wait(1.6)
        check('after it the bolt stays locked open (empty pose)', vm._empty >= 1.0, f'{vm._empty}')
        click()
        yield
        yield
        check('pulling the trigger on the empty gun starts a reload', combat.handling.busy and combat.handling.phase.name == 'RELOAD', str(combat.handling.phase))
        yield from wait_ready(25)
        yield from wait(0.3)

        # --- no aiming: the aim button does nothing ---
        reset_ammo(8, 32)
        held_keys['right mouse'] = 1
        yield from wait(0.6)
        check('the aim button does nothing (a shotgun is fired from the hip)', player.ads_amount == 0.0 and not player.ads, f'ads {player.ads_amount}')
        held_keys['right mouse'] = 0

        # --- the procedural draw: switch away and back, watch the gun lift (no draw / holster sounds) ---
        draw_before = (foley.counts['draw_a'], foley.counts['draw_b'])
        game.request_gun('glock')
        yield from wait(2.5)
        check('switched to the Glock', game.gun_name == 'glock', game.gun_name)
        game.request_gun('m1014')
        t_end = pytime.time() + 5.0
        while game.gun_name != 'm1014' and pytime.time() < t_end:           # the Glock's holster clip runs first
            yield
        for _ in range(3):
            yield
        low = game.viewmodel._swap
        yield from wait(1.5)
        check('switching back: the M1014 is in hand and the draw is over', game.gun_name == 'm1014' and not combat.handling.busy and game.viewmodel._swap == 0.0, f'{game.gun_name}, swap {game.viewmodel._swap:.2f}')
        check('no draw / holster sound is played for the M1014', (game.foley.counts['draw_a'], game.foley.counts['draw_b']) == draw_before, f'{draw_before} -> {(game.foley.counts["draw_a"], game.foley.counts["draw_b"])}')
        check('during the draw the gun starts lowered (procedural pose)', low > 0.3, f'swap amount 3 frames after the draw starts: {low:.2f}')

        # --- the F1 panel: the shotgun numbers sit in the shared tabs (Bắn, Nạp đạn), no tab of its own ---
        game.debug.toggle()
        for _ in range(5):
            yield
        game.debug.select_group('fire')
        for _ in range(3):
            yield
        store = game.params_store
        ids = [sp.id for sp in store.group_by_key['fire'].specs]
        check('F1: no Shotgun tab; the pellet numbers are in the "Bắn" tab and the interrupt switch in "Nạp đạn"', 'shotgun' not in [g.key for g in store.groups] and all(i in ids for i in ('gun.pellets', 'gun.pellet_spread', 'gun.pellet_center_bias', 'gun.pellet_tracers', 'gun.bullet_drag'))
              and store.by_id['gun.reload.interrupt_fire'].group == 'reload', f'{len(game.debug.tabs)} tabs')
        shots = ROOT / 'shots'
        shots.mkdir(exist_ok=True)
        application.base.win.save_screenshot(Filename.from_os_specific(str(shots / 'm1014_f1_fire_tab.png')))
        game.debug.hide()
        yield


Script()
game.app.run()
