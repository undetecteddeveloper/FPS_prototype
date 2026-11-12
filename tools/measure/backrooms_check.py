r"""G18: the Backrooms level in the REAL game (opens a window): the arrival door, enemies chasing and striking, a bullet kill, the floor clear, the exit door,
the floor swap halfway up the stairs (the player keeps his spot in the corridor), all 5 floors, the win, death and the restart at floor 1, FPS while 8-15 enemies chase.
Screenshots of every floor go to shots\g18_floorN_*.png (for viewing). Prints PASS / FAIL per check; exit code = number of failures.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\backrooms_check.py [--fps-seconds 4] [--size 1280x720]
"""
import argparse
import math
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename  # noqa: E402
from ursina import Entity, application, held_keys, mouse  # noqa: E402

from fps.core import backrooms as br  # noqa: E402
from fps.core.enemies import DEAD as E_DEAD  # noqa: E402
from fps.core.level import ARRIVE, CLEAR, CLIMB, DEAD, FIGHT, WON  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--fps-seconds', type=float, default=4.0)
ap.add_argument('--size', default='1280x720')
ap.add_argument('--vsync', action='store_true', help='như game thật (FPS bị chặn 60): kiểm mục tiêu >= 60')
args = ap.parse_args()
W, H = (int(v) for v in args.size.split('x'))
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)

game = create_game(hidden=False if args.vsync else None, vsync=args.vsync, size=(W, H), sound=False, draw=False, map_name='backrooms')    # --vsync measures true FPS: real window
mouse.locked = False
game.combat.require_locked_mouse = False
level, player, combat = game.level, game.player, game.combat
failures = []
fps_rows = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)
    if not ok:
        failures.append(name)


def place(x, z, yaw=0.0, pitch=0.0):
    t = player.terrain
    y = t.floor_at(x, z, player.y + 3.0)
    player.x, player.z = x, z
    player.y = 0.0 if y is None else y
    player.vx = player.vz = player.vy = 0.0
    player.on_ground = True
    player.yaw, player.pitch = yaw, pitch
    player.step_offset = 0.0
    player._apply_view()


def shot(name):
    application.base.graphicsEngine.render_frame()
    application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'g18_floor{level.current.k + 1}_{name}.png')))


def look_at(x, y, z):
    eye = player.aim_ray()[0]
    dx, dy, dz = x - eye[0], y - eye[1], z - eye[2]
    player.yaw = math.degrees(math.atan2(dx, dz))
    player.pitch = -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
    player._apply_view()


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.dt_log = None

    def update(self):
        if self.dt_log is not None:
            from ursina import time
            self.dt_log.append(time.dt)
        try:
            next(self.gen)
        except StopIteration:
            application.quit()

    def wait(self, seconds):
        t0 = pytime.time()
        while pytime.time() - t0 < seconds:
            yield

    def measure_fps(self, label):
        """Let the swarm chase the player (standing still, invulnerable) for a few seconds and record the frame times."""
        hp = level.health.hp
        self.dt_log = []
        t0 = pytime.time()
        while pytime.time() - t0 < args.fps_seconds:
            level.health.hp = level.health.d.max_hp        # invulnerable while measuring
            yield
        log, self.dt_log = self.dt_log[5:], None
        level.health.hp = hp
        if log:
            avg = len(log) / sum(log)
            worst = sorted(log)[-max(1, len(log) // 100)]
            hostile = sum(1 for e in level.current.swarm.enemies if e.hostile)
            dropped = sum(1 for t in log if t > 1.5 / 60.0)          # with vsync: a frame that missed its 16.7 ms slot
            fps_rows.append((label, avg, 1.0 / worst, hostile))
            print(f'   FPS {label}: trung bình {avg:.0f}, 1% thấp {1.0 / worst:.0f}, khung rớt {dropped}/{len(log)}, địch đang đuổi {hostile}', flush=True)
            if args.vsync:
                # this laptop drops ~5-7 % of windowed vsync frames on the old pool hall too (Windows / DWM, measured 12/11/2026): the level must not do worse
                check(f'{label}: ~60 FPS with vsync', avg >= 57.0 and dropped <= len(log) * 0.08, f'{avg:.1f} FPS, rớt {dropped}')

    def run(self):
        yield from self.wait(0.5)
        cur = level.current
        fm = cur.fm
        check('floor 1 built with its enemies', cur.k == 0 and cur.swarm.alive_count == sum(fm.spec.enemies), f'{cur.swarm.alive_count}')
        check('the player starts in the arrival corridor', br.in_corridor(fm.arrive_origin, (player.x, 0, player.z)) is not None and level.state.phase == ARRIVE)
        shot('corridor')
        yield from self.wait(1.6)
        arrive = next(n for n, d in cur.doors.items() if d.kind == 'arrive')
        check('the arrival door opens in front of him', cur.door_open[arrive] > 0.95, f'{cur.door_open[arrive]:.2f}')
        for floor in range(5):
            yield from self.play_floor(floor)
        # Enter after the win: back to floor 1; then death and the restart
        game.input('enter')
        yield
        yield
        check('after the win, Enter restarts at floor 1', level.current.k == 0 and level.state.phase == ARRIVE and level.state.clock < 0.5,
              f'tầng {level.current.k + 1}, {level.state.phase}, {level.state.clock:.2f} s')
        yield from self.wait(0.5)
        yield from self.death()
        print('\nFPS:', ', '.join(f'{lab} {a:.0f}/{lo:.0f}' for lab, a, lo, _ in fps_rows))
        print(f'KẾT QUẢ: {"QUA" if not failures else f"{len(failures)} mục TRƯỢT"}')

    def play_floor(self, k):
        cur = level.current
        fm, sw = cur.fm, cur.swarm
        d = fm.data
        hz = d.room_z / 2
        check(f'floor {k + 1}: current floor index', cur.k == k and level.state.floor == k)
        # into the hall
        place(fm.spec.arrive_x, -hz + 3.0, 0.0)
        yield from self.wait(0.3)
        check(f'floor {k + 1}: stepping into the hall starts the fight and shuts the door behind', level.state.phase == FIGHT)
        shot('hall')
        place(0.0, -hz + 1.6, 0.0, -8.0)
        yield
        shot('view')
        # a shot wakes them up; they come and strike
        combat.shots_fired += 1
        hp0 = level.health.hp
        t0 = pytime.time()
        closest = 1e9
        while pytime.time() - t0 < 14.0 and level.health.hp >= hp0:
            closest = min([closest] + [math.hypot(e.x - player.x, e.z - player.z) for e in sw.enemies if e.alive])
            yield
        took = pytime.time() - t0
        check(f'floor {k + 1}: the swarm reaches him and a strike lands', level.health.hp < hp0, f'{took:.1f} s, nearest {closest:.2f} m, hp {level.health.hp:.0f}')
        hostile = sum(1 for e in sw.enemies if e.hostile)
        check(f'floor {k + 1}: the gunshot turned the floor hostile', hostile >= sw.alive_count * 0.6, f'{hostile}/{sw.alive_count}')
        shot('swarm')
        yield from self.measure_fps(f'tầng {k + 1} ({sw.alive_count} địch)')
        windups = max(sum(1 for e in sw.enemies if e.state == 'windup'), 0)
        check(f'floor {k + 1}: at most {game.params.enemy.tokens} attack at once', sw.tokens_used <= game.params.enemy.tokens and windups <= game.params.enemy.tokens)
        # a real bullet kill: aim at the nearest enemy and fire until it drops (M4: 3 body hits)
        level.health.hp = level.health.d.max_hp
        alive = [e for e in sw.enemies if e.alive]
        target = min(alive, key=lambda e: math.hypot(e.x - player.x, e.z - player.z))
        hits_before = sw.kills
        for _ in range(240):
            if not target.alive:
                break
            level.health.hp = level.health.d.max_hp
            look_at(target.x, target.y + target.kind.height * 0.55, target.z)
            held_keys['left mouse'] = 1
            combat.pressed = True
            yield
        held_keys['left mouse'] = 0
        check(f'floor {k + 1}: bullets kill an enemy', target.state == E_DEAD and sw.kills > hits_before, f'{target.kind_name} hp {target.hp:.0f}')
        # the rest drop (direct damage) -> the floor is clear
        for e in list(sw.enemies):
            if e.alive:
                sw.damage(e, 1e6)
        yield from self.wait(0.3)
        check(f'floor {k + 1}: no enemy left -> clear, exit door opening', level.state.phase == CLEAR)
        if k < 4:
            check(f'floor {k + 1}: the next floor is built at the clear', level.next is not None and level.next.k == k + 1)
        yield from self.wait(1.5)
        exit_name = next(n for n, dd in cur.doors.items() if dd.kind == 'exit')
        check(f'floor {k + 1}: exit door open', cur.door_open[exit_name] > 0.95)
        # up the stairs: walk in, the door shuts, halfway up the floor swaps
        eo = fm.exit_origin
        place(eo[0], eo[2] - 1.0, 0.0)
        for s in (0.5, 1.5, 2.5, 3.4):
            place(eo[0], eo[2] + s, 0.0)
            yield
        check(f'floor {k + 1}: the door shuts behind him on the stairs', level.state.phase == CLIMB)
        shot('stairs')
        yield from self.wait(1.6)
        check(f'floor {k + 1}: exit door shut', cur.door_open[exit_name] <= 0.0)
        if k == 4:
            place(eo[0], eo[2] + br.LENGTH - 1.0, 0.0)
            yield
            yield
            check('floor 5: the top of the last stairs wins', level.state.phase == WON, level.state.phase)
            shot('won')
            return
        place(eo[0], eo[2] + br.SWAP_S + 0.2, 0.0)
        rel = (player.x - eo[0], player.y - eo[1], player.z - eo[2])
        yield
        yield
        new = level.current
        ao = new.fm.arrive_origin
        rel2 = (player.x - ao[0], player.y - ao[1], player.z - ao[2])
        err = max(abs(a - b) for a, b in zip(rel, rel2))
        check(f'floor {k + 1} -> {k + 2}: swapped halfway up, same spot in the corridor', new.k == k + 1 and err < 1e-3, f'lệch {err * 1000:.2f} mm')
        check(f'floor {k + 2}: ammo refilled', combat.weapon.mag == game.params.gun.magazine)
        # walk to the top of the arrival corridor: its door opens
        place(ao[0], ao[2] + br.LENGTH - 1.0, 0.0)
        yield from self.wait(1.6)
        arrive = next(n for n, dd in new.doors.items() if dd.kind == 'arrive')
        check(f'floor {k + 2}: arrival door opens', new.door_open[arrive] > 0.95)

    def death(self):
        level.health.hit(1e6)
        yield
        yield
        check('death: the level shows the death', level.state.phase == DEAD and player.frozen)
        yield from self.wait(game.params.health.death_time + 0.5)
        check('death: restarted at floor 1 with full health', level.current.k == 0 and level.state.phase == ARRIVE and level.health.hp == level.health.d.max_hp
              and not player.frozen and br.in_corridor(level.current.fm.arrive_origin, (player.x, 0, player.z)) is not None)


Script()
game.app.run()
sys.exit(len(failures))
