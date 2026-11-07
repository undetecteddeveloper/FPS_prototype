r"""G9: checks of the pool hall in the REAL game (opens a window): bullets on water / wall / window, walking into the pool, climbing out by the steps and by jumping, the light on the gun, the polygon budget.
Prints PASS / FAIL per check and exits with the number of failures.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\pool_check.py
"""
import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Point3  # noqa: E402
from ursina import Entity, held_keys, mouse  # noqa: E402

from fps.core.exposure import sun_vector  # noqa: E402
from fps.core.sway import ads_target_for  # noqa: E402
from fps.game.combat import Bullet  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='m4')
args = ap.parse_args()
game = create_game(vsync=False, size=(800, 450), sound=False, draw=False, map_name='pool', gun=args.gun)
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


def sight_gap_degrees() -> float:
    """Angle (degrees) between the rear and the front sight as seen from the eye, read from the REAL scene graph: two probe nodes at the sight points under the gun's `sway` node, so they go
    through exactly the transforms the gun model goes through (the aim node above it included)."""
    vm, gun = game.viewmodel, game.params.gun
    pts = []
    for sight in gun.ads_sights:
        node = vm.sway.attach_new_node('sight_probe')
        node.set_pos(*(c + h for c, h in zip(sight, gun.hip_offset)))
        pts.append(vm.root.get_relative_point(node, Point3(0, 0, 0)))
        node.remove_node()
    a, b = pts
    cross = (a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
    return math.degrees(math.atan2(math.sqrt(sum(c * c for c in cross)), a.x * b.x + a.y * b.y + a.z * b.z))      # atan2, not acos: acos of a float32 'almost 1' is off by ~0.02 degrees


def read_sim(sim) -> list:
    """The simulated heights (metres) read back from the GPU ([row][col])."""
    import struct
    from ursina import application
    tex = sim.drawn_texture
    base = application.base
    base.graphicsEngine.extract_texture_data(tex, base.win.get_gsg())
    raw = bytes(tex.get_ram_image_as('RG'))
    vals = struct.unpack(f'<{2 * sim.cols * sim.rows}f', raw[:8 * sim.cols * sim.rows])
    return [[vals[2 * (j * sim.cols + i)] for i in range(sim.cols)] for j in range(sim.rows)]


def centre_contrast() -> float:
    """Standard deviation of the brightness in the middle 30 % of the window (the picture after the lens: noise included)."""
    from panda3d.core import PNMImage
    from ursina import application
    img = PNMImage()
    application.base.win.get_screenshot(img)
    w, h = img.get_x_size(), img.get_y_size()
    vals = []
    for y in range(int(h * 0.35), int(h * 0.65), 2):
        for x in range(int(w * 0.35), int(w * 0.65), 2):
            vals.append(img.get_bright(x, y))
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


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
        walk(480, forward=1.0)                                            # 8 s at 4.5 m/s: from the south bank down the steps, along the shallow end, down the slope
        d = pool.data
        wade_y = d.water_y - d.wade_depth
        z_line = d.slope_z[0] + (d.slope_z[1] - d.slope_z[0]) * (d.pool_floor - wade_y) / (d.pool_floor - d.pool_deep)
        check('walk north into the pool: down the steps and the slope, stopped where the water is chest-deep', player.on_ground and abs(player.y - wade_y) < 0.05 and abs(player.z - z_line) < 0.15,
              f'y={player.y:.3f} (giới hạn {wade_y:.2f}) z={player.z:.2f} (vạch {z_line:.2f})')
        check('... his eyes stay above the water', player.y + player.eye_height > d.water_y + 0.2, f'mắt {player.y + player.eye_height:.2f}')
        place(0.0, 0.0, 13.5, 180.0)                                      # on the north deck, facing the deep end
        walk(60, forward=1.0, jump=True)
        walk(30)
        check('the deep end cannot be entered from the deck either (no swimming yet): he stays on the deck edge', player.on_ground and abs(player.y) < 1e-6 and player.z >= d.pool_z / 2 - 1e-6,
              f'y={player.y:.3f} z={player.z:.2f}')
        place(0.0, wade_y, 9.0, 180.0)                                    # safety net: if he ever ends up in the deep end he stands at chest depth...
        walk(300, forward=1.0)
        check('... and wades back to the shallows', player.z < 0.0 and player.on_ground, f'z={player.z:.2f} y={player.y:.3f}')

        place(-5.2, pool.data.pool_floor, -8.0, 270.0)                   # on the shallow floor, 0.8 m from the west wall, facing west
        walk(30, forward=1.0)
        check('a wall of the pool stops him on the floor', player.x >= -pool.data.pool_x / 2 - 1e-6 and abs(player.y - pool.data.pool_floor) < 1e-6, f'x={player.x:.2f}')
        place(-5.2, pool.data.pool_floor, -8.0, 270.0)
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

        # --- aimed sights stay lined up with the eye when the gun is pushed off the screen centre (user report 7/11/2026)
        # (a) exact: set the poses straight on the real scene-graph nodes (ADS pose + an aim rotation far outside the free zone), no sway noise
        vm, gun = game.viewmodel, game.params.gun
        vm.ads = 1.0
        ads = ads_target_for(gun)
        exact = []
        for yaw, pitch, roll in ((0.0, 0.0, 0.0), (3.0, 1.8, 0.7), (-6.0, -3.6, -1.3), (10.0, 6.0, 2.2), (-15.0, 9.0, -3.3), (15.0, -9.0, 3.3)):
            vm.update(ads, aim=((0.0, 0.0, 0.0, pitch, yaw, roll),))
            exact.append(sight_gap_degrees())
        check(f'{args.gun}: sights on one line through the eye at any aim offset (real nodes, exact poses)', max(exact) < 0.01, f'{[round(g, 4) for g in exact]} deg')
        # (b) live: aimed for real, gun pushed to offsets inside the aimed free zone; breathing and mouse lag still move the gun a few mm, which M4 (eye relief 0.18 m) shows as ~0.2 degrees
        place(*pool.spawn, 0.0)
        held_keys['right mouse'] = 1
        for _ in range(90):                                              # ~1.5 s: fully aimed
            yield
        gaps = []
        for yaw, pitch in ((0.0, 0.0), (1.5, 0.9), (-2.0, -1.0), (2.8, -0.5)):
            for _ in range(20):
                player.free_look.offset = [yaw, pitch]
                yield
            gaps.append(sight_gap_degrees())
        held_keys['right mouse'] = 0
        check(f'{args.gun}: aimed live, sights stay within 0.5 degrees at in-zone offsets', max(gaps) < 0.5 and player.ads_amount > 0.99, f'{[round(g, 3) for g in gaps]} deg, ads {player.ads_amount:.2f}')
        player.free_look.reset()

        # --- the gun is lit by the baked local ambient: dark in the dark corner, brighter by the windows
        place(-9.5, 0.0, -14.5, 0.0)
        for _ in range(10):
            yield
        corner = tuple(game.light.ambient_up[0])                            # a copy: the PTA element is a live reference
        place(8.5, 0.0, 0.0, 0.0)
        for _ in range(10):
            yield
        window = tuple(game.light.ambient_up[0])
        corner_luma, window_luma = sum(corner) / 3, sum(window) / 3
        check('gun ambient light follows the room: dark corner < under the windows, and well below the old fixed 0.27', corner_luma < 0.6 * window_luma and corner_luma < 0.2, f'corner {corner_luma:.3f}, windows {window_luma:.3f}')

        # --- ripples really animate
        t0 = pool.water.clock
        pool.update(0.5)
        check('water clock advances', abs(pool.water.clock - t0 - 0.5) < 1e-9)
        yield

        # --- G10: wave simulation, clear water, F2
        water = pool.water
        game.set_graphics(2, announce=False)
        for _ in range(5):
            yield
        check('graphics High builds the wave simulation', water.sim is not None and water.sim.enabled, f'{water.sim.cols}x{water.sim.rows}' if water.sim else 'none')
        if water.sim is not None:
            for _ in range(10):
                yield
            water.splash((1.0, water.y, 2.0), 10.0)
            for _ in range(4):
                yield
            h = read_sim(water.sim)
            check('a bullet on the water pushes the simulated surface down', min(min(r) for r in h) < -0.001, f'deepest {min(min(r) for r in h) * 1000:.2f} mm')
            for _ in range(30):                                     # the readback stalls the GPU: let it pass before anything is timed
                yield
        # straight down at the water from inside the pool: Low (dark mirror) vs High (tiles of the bottom seen through the water)
        vm_root = game.viewmodel.root
        vm_root.hide()
        contrast = {}
        for lvl in (0, 2):
            game.set_graphics(lvl, announce=False)
            place(2.0, -0.62, -2.0, 0.0)
            player.pitch = 80.0
            player._apply_view()
            for _ in range(20):
                yield
            contrast[lvl] = centre_contrast()
        vm_root.show()
        check('High: the pool bottom shows through the water (tile contrast well above the dark mirror of Low)', contrast[2] > 2.0 * contrast[0] and contrast[2] > 0.02,
              f'contrast Low {contrast[0]:.4f}, High {contrast[2]:.4f}')
        # F2 switching costs no hitch
        import time as pytime
        worst = 0.0
        for lvl in (0, 1, 2, 1, 2):
            game.set_graphics(lvl, announce=True)
            last = pytime.perf_counter()
            for _ in range(6):
                yield
                now = pytime.perf_counter()
                worst = max(worst, now - last)
                last = now
        check('F2: switching graphics levels never makes a frame slower than 50 ms', worst < 0.05, f'worst frame {worst * 1000:.1f} ms')
        game.set_graphics(game.params.graphics.level, announce=False)
        yield


Script()
game.app.run()
