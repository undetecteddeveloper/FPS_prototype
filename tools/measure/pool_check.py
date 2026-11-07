r"""G9: checks of the pool hall in the REAL game (opens a window): bullets on water / wall / window, walking into the pool, climbing out by the steps and by jumping, the light on the gun, the polygon budget.
Prints PASS / FAIL per check and exits with the number of failures.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\pool_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, mouse  # noqa: E402

from fps.core.exposure import sun_vector  # noqa: E402
from fps.game.combat import Bullet  # noqa: E402

game = create_game(vsync=False, size=(800, 450), sound=False, draw=False, map_name='pool')
mouse.locked = False
game.combat.require_locked_mouse = False
pool, combat, player = game.pool, game.combat, game.player
failures = []


def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not ok:
        failures.append(name)


def fire(origin, vel, seconds=0.05):
    """Fly one bullet until it is gone; returns the number of 0.05 s steps it lived."""
    b = Bullet(origin, vel)
    for steps in range(1, 80):
        if not combat._advance(b, seconds, combat._boxes()):
            return steps
    return 80


def walk(frames, forward=0.0, strafe=0.0, jump=False, dt=1 / 60):
    for i in range(frames):
        player.step(dt, forward, strafe, False, False, jump and i < 3)


def place(x, y, z, yaw):
    player.x, player.y, player.z = x, y, z
    player.vx = player.vz = player.vy = 0.0
    player.on_ground = True
    player.yaw, player.pitch = yaw, 0.0
    player.step_offset = 0.0


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            sys.exit(len(failures))

    def run(self):
        for _ in range(5):
            yield
        # --- map facts
        check('budget: <= 6000 triangles', pool.triangles <= 6000, f'{pool.triangles} tam giác')
        check('budget: <= 4 draw calls for the map', pool.draw_calls <= 4, f'{pool.draw_calls} lần vẽ')
        check('reflection image loaded', pool.reflection is not None)

        # --- bullets
        holes = combat.decals.count
        rings = pool.water.ripples.alive(pool.water.clock, game.params.water.impact_life)
        steps = fire((0.0, 1.5, -5.0), (0.0, -200.0, 60.0))
        check('bullet on the water makes exactly one ring', pool.water.ripples.alive(pool.water.clock, game.params.water.impact_life) == rings + 1 and steps < 80)
        check('bullet on the water leaves no hole', combat.decals.count == holes)
        impact = combat.last_impact
        check('the ring is at the hit point on the water level', impact is not None and abs(impact.point[1] - pool.pm.water[4]) < 1e-6, f'{impact.point if impact else None}')

        holes = combat.decals.count
        fire((0.0, 1.5, 0.0), (-300.0, 0.0, 0.0))
        check('bullet on the west wall makes a hole', combat.decals.count == holes + 1)
        check('... at x = west wall', abs(combat.last_impact.point[0] + game.pool.data.room_x / 2) < 1e-3, f'{combat.last_impact.point}')
        last = combat.last_impact
        holes = combat.decals.count
        lived = fire((0.0, 1.5, game.pool.data.window_z[1]), (300.0, 0.0, 0.0))
        check('bullet through a window flies out and expires (no hole, no error)', combat.decals.count == holes and combat.last_impact is last and 58 <= lived <= 62, f'{lived} bước (tuổi thọ 3 s)')
        holes = combat.decals.count
        fire((0.0, 1.2, 0.0), (0.0, 300.0, 0.0))
        check('bullet straight up hits the ceiling', combat.decals.count == holes + 1 and abs(combat.last_impact.point[1] - game.pool.data.ceiling) < 1e-3)
        n_ring = pool.water.ripples.alive(pool.water.clock, game.params.water.impact_life)
        fire((20.0, 1.5, 0.0), (-300.0, 0.0, 0.0))                    # from outside: the east wall is hit first (or through a window if aligned)
        check('a bullet from outside hits the east wall and never rings the water', pool.water.ripples.alive(pool.water.clock, game.params.water.impact_life) == n_ring and combat.last_impact.point[0] > pool.data.room_x / 2)

        # --- walking
        sp = pool.spawn
        place(*sp, 0.0)
        walk(1, 0.0)
        check('spawn: standing on the deck', player.on_ground and abs(player.y) < 1e-9 and abs(player.z - sp[2]) < 1e-6)
        walk(480, forward=1.0)                                            # 8 s at 4.5 m/s: from the south bank (z = -13.5) past the far end of the pool (z = 12)
        pz = pool.data.pool_z / 2
        check('walk north into the pool: down the steps onto the floor', player.on_ground and abs(player.y - pool.data.pool_floor) < 1e-6, f'y={player.y:.3f}')
        check('... and stopped by the north wall of the pool', pz - 0.6 <= player.z <= pz + 1e-6, f'z={player.z:.2f}')
        walk(25, strafe=-1.0)                                             # against the north wall, sliding sideways into the side of the stairs: the top step is 0.47 m up, a wall
        check('the side of the north steps is a wall from the pool floor (no climbing sideways)', player.on_ground and abs(player.y - pool.data.pool_floor) < 1e-6 and player.x > pool.data.north_steps_x[1] - 1e-3, f'x={player.x:.2f}')
        place(-1.8, pool.data.pool_floor, 8.0, 0.0)                       # in front of the steps, facing north
        walk(150, forward=1.0)
        check('walk up the north steps onto the deck (3 steps of 0.155 m)', player.on_ground and abs(player.y) < 1e-6 and player.z > pz, f'y={player.y:.3f} z={player.z:.2f} x={player.x:.2f}')

        place(-5.2, pool.data.pool_floor, 0.0, 270.0)                    # on the pool floor, 0.8 m from the west wall, facing west
        walk(30, forward=1.0)
        check('a wall of the pool stops him on the floor', player.x >= -pool.data.pool_x / 2 - 1e-6 and abs(player.y - pool.data.pool_floor) < 1e-6, f'x={player.x:.2f}')
        place(-5.2, pool.data.pool_floor, 0.0, 270.0)
        walk(70, forward=1.0, jump=True)
        check('jump + run gets him out over the pool edge onto the west bank', player.x < -pool.data.pool_x / 2 - 0.3 and abs(player.y) < 1e-6, f'x={player.x:.2f} y={player.y:.3f}')

        place(0.0, 0.0, -13.5, 0.0)
        walk(1, 0.0)
        player.x, player.y = 0.0, 0.0
        drop = 0
        place(0.0, 0.0, -11.9, 0.0)                                       # right at the pool edge on the south side: steps down, no thump
        before = player.landed
        walk(10, forward=1.0)
        check('stepping down a pool step is not a fall (no landing event)', player.landed == 0.0 and player.on_ground)
        place(3.0, 0.0, -13.9, 0.0)
        walk(60, forward=1.0)
        check('the columns and walls never let him through', abs(player.x) <= pool.data.room_x / 2 and abs(player.z) <= pool.data.room_z / 2)
        place(-8.0 + 0.6 + 2.0, 0.0, 6.0, 270.0)
        walk(120, forward=1.0)
        check('a column stops him', player.x >= -8.0 + 0.6 + player.p.radius - 1e-3, f'x={player.x:.2f}')

        # --- light on the gun
        sun = sun_vector(game.params.look)
        grid = [(x, 1.68, z) for x in range(-9, 10, 2) for z in range(-14, 15, 2)]
        blocked = [pool.sun_blocked(p, sun) for p in grid]
        check('the sun reaches the player in some places and not in others', 0 < sum(blocked) < len(blocked), f'{sum(blocked)}/{len(blocked)} in the shade')

        # --- ripples really animate
        t0 = pool.water.clock
        pool.update(0.5)
        check('water clock advances', abs(pool.water.clock - t0 - 0.5) < 1e-9)
        yield


Script()
game.app.run()
