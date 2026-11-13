"""G18 / G19 the run in the game: stage 0 = the pool hall (no enemies), stages 1-5 = the Backrooms floors, one at a time as a PoolHall (core/backrooms.py has the
geometry, core/level.py the phases, core/enemies.py the swarm).

Game owns the wiring that every map shares (player terrain, bullets, water, underwater, reflections); this module tells it WHEN to swap stages (`Game._enter_floor`) and
runs everything that only exists here. Per frame (Game.update, after the player moved, before Combat):
  where is the player (corridors / cabins / floor) -> LevelState phases -> doors slide (solid while not fully open) -> the swarm moves / strikes -> health, lift ride,
  sounds, notices.
The next stage is built the moment the current one is cleared (a short hitch while no enemy is left) and swapped in on the stairs (pool hall) or during the lift ride.
"""
import json
import math
import random
import time
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.core import backrooms as br
from fps.core.ballistics import first_hit
from fps.core.enemies import Swarm, falloff_damage
from fps.core.flowfield import FlowField, NavGrid
from fps.core.level import CLEAR, DEAD, FINAL, RIDE, WON, Health, LevelState, Where
from fps.weapon_data import BACKROOMS

ASSET_ROOT = 'assets/maps/backrooms'
SOUND_DIR = 'assets/sounds/enemy'
DOOR_SPEED = {'corridor': 0.9, 'lift': 1.2}       # openings per second (a corridor door ~1.1 s, the lift leaves ~0.8 s)
RIDE_TIME = 4.2                                    # s the cabin hums between floors
SPAWN_CLEAR = 9.0                                  # m: no enemy starts closer than this to where the player comes in
NOTICE_GLYPHS = ('Tầng / 5 · Sảnh đầu Rừng cột Sảnh cao Mê cung Hồ lớn đã sạch, thang máy mở. Còn 0123456789 Thoát khỏi Poolrooms Thời gian: '
                 'Bạn gục. Chơi lại từ 1 Nhấn Enter để chơi lại E: đi thang máy')


def stage_dir(stage: int) -> str:
    """Where a stage's bake lives: the pool hall keeps its old folder."""
    return 'assets/maps/pool' if stage == 0 else f'{ASSET_ROOT}/floor{stage}'


floor_dir = stage_dir                                  # (G18 name, kept for the tools)


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds + 0.5), 60)
    return f'{m}:{s:02d}'


class _Sounds:
    """A few voices per sound (assets/sounds/enemy, tools/build/make_enemy_sounds.py); volume falls with distance from the camera. Missing files are silent."""
    VOLUME = {'alert': 0.55, 'windup': 0.6, 'strike': 0.9, 'hurt': 0.55, 'die': 0.7, 'player_hurt': 0.9,
              'lift_hum': 0.55, 'lift_ding': 0.6, 'door_slide': 0.45}

    def __init__(self, root: Path, enabled: bool):
        self.banks = {}
        self.rng = random.Random(3)
        if not enabled:
            return
        loader = application.base.loader
        for name in self.VOLUME:
            path = root / SOUND_DIR / f'{name}.wav'
            if path.exists():
                self.banks[name] = [[loader.load_sfx(Filename.from_os_specific(str(path))) for _ in range(4)], 0]

    def play(self, name: str, pos=None, listener=None, rate: float = None):
        bank = self.banks.get(name)
        if bank is None:
            return
        voices, i = bank
        s = voices[i]
        bank[1] = (i + 1) % len(voices)
        k = 1.0
        if pos is not None and listener is not None:
            d = math.dist(pos, listener)
            k = 1.0 / (1.0 + max(d - 2.0, 0.0) / 5.0)
        s.set_volume(self.VOLUME[name] * k)
        s.set_play_rate(rate if rate is not None else self.rng.uniform(0.92, 1.08))
        s.play()


class Floor:
    """Everything built for one stage: the PoolHall (room, water, bake), the swarm, the nav grid, the doors."""

    def __init__(self, game, stage: int):
        from fps.game.enemies import DoorView, SwarmView
        from fps.game.pool import PoolHall
        p = game.params
        self.k = stage
        self.fm = br.build_stage(stage)
        key = br.floor_key(self.fm, p.look)
        label = 'phòng hồ bơi' if stage == 0 else f'tầng {stage} của Backrooms'
        self.hall = PoolHall(p, game.root, pm=self.fm, asset_dir=stage_dir(stage), key=key, label=label, spawn=self.fm.start[:3])
        x0, x1, z0, z1, wy = self.fm.water
        self.water = (x0, x1, z0, z1, wy)
        self.terrain = self.hall.terrain(p.player.radius)
        d = p.enemy
        if stage > 0:
            self.nav = NavGrid(self.terrain, self.fm.nav_rect, d.cell, d.normal.radius, p.player.step_up, water=self.water, deep_cost=d.deep_cost)
            self.field = FlowField(self.nav)
        else:
            self.nav = self.field = None                      # the pool hall: nobody to guide
        index = self.hall._sun_index                          # the room's boxes without the water: what blocks a line of sight

        def los(a, b):
            return first_hit(a, b, index.segment(a, b), ground_y=None) is None
        seed = self.fm.spec.seed if self.fm.spec else 1
        self.swarm = Swarm(d, self.terrain, self.nav, self.field, los=los, water=self.water, step_up=p.player.step_up, rng=random.Random(seed))
        self.swarm.player_radius = p.player.radius
        if stage > 0:
            self._spawn()
        self.view = SwarmView(d)
        self.doors = {dr.name: dr for dr in self.fm.doors}
        self.door_open = {name: 0.0 for name in self.doors}
        self.door_view = DoorView(self.fm.doors, self.hall.local_ambient)
        self.hall.node.hide()                                  # shown when it becomes the current stage
        self.hall.water.node.hide()
        self.door_view_hide(True)

    def _spawn(self):
        fm, nav = self.fm, self.nav
        rng = random.Random(fm.spec.seed)
        ax, az = fm.arrive_point
        cells = [i for i in nav.open_cells() if nav.height[i] >= -0.01 and math.dist(nav.center(i), (ax, az)) > SPAWN_CLEAR]
        rng.shuffle(cells)
        taken = []
        for kind, n in zip(('normal', 'runner', 'brute'), fm.spec.enemies):
            for _ in range(n):
                for idx, c in enumerate(cells):
                    x, z = nav.center(c)
                    if all(math.hypot(x - tx, z - tz) > 2.2 for tx, tz in taken):
                        taken.append((x, z))
                        self.swarm.spawn(kind, x, z, yaw=rng.uniform(0, 360))
                        cells.pop(idx)
                        break

    def door_view_hide(self, hidden: bool):
        for b in self.door_view.bodies:
            if hidden:
                b.node.hide()
            else:
                b.node.show()

    def show(self):
        self.hall.node.show()
        self.hall.water.node.show()
        self.door_view_hide(False)

    def destroy(self):
        self.view.clear()
        self.door_view.destroy()
        self.hall.destroy()


class Level:
    def __init__(self, game, sound: bool = True, rebake: bool = False, start: int = 0):
        self.game = game
        p = game.params
        self.p = p
        self.state = LevelState(br.stage_count(), br.LENGTH, br.SWAP_S, p.health.death_time, RIDE_TIME, start=start)
        self.health = Health(p.health)
        self.sounds = _Sounds(game.root, sound)
        self.ensure_baked(force=rebake)
        self.current = Floor(game, start)
        self.current.show()
        self.next = None
        self.press_e = False                           # Game.input sets it on 'e'; used once per frame
        self._prompt_t = 0.0
        self._shake_t = 0.0
        self._door_moving = {}

    # --- light bake of every stage before the run starts (a stale one would otherwise bake in the middle of the game) ---
    def ensure_baked(self, force: bool = False):
        from fps.game.pool import _BakeScreen, bake_map, rail_probes, store_bake
        root = self.game.root
        for k in range(br.stage_count()):
            fm = br.build_stage(k)
            key = br.floor_key(fm, self.p.look)
            folder = root / stage_dir(k)
            try:
                stored = json.loads((folder / 'meta.json').read_text(encoding='utf-8')).get('key')
            except (OSError, ValueError):
                stored = None
            if stored == key and not force:
                continue
            print(f'[backrooms] nướng ánh sáng màn {k}...')
            t0 = time.time()
            screen = _BakeScreen('phòng hồ bơi' if k == 0 else f'tầng {k} / {len(BACKROOMS)} của Backrooms')
            try:
                res = bake_map(fm, self.p.look, rail_probes(fm.data), lambda done, total: screen.show(done / total))
            finally:
                screen.close()
            store_bake(folder, key, res)
            print(f'[backrooms] xong màn {k} sau {time.time() - t0:.1f} s')

    @property
    def hall(self):
        return self.current.hall

    def start_pose(self) -> tuple:
        return self.current.fm.start

    # --- per frame ---
    def where(self, x: float, y: float, z: float) -> Where:
        fm = self.current.fm
        w = fm.data.wall
        p = (x, y, z)
        arrive_s = br.in_corridor(fm.arrive_origin, p) if fm.arrive_kind == 'corridor' else None
        exit_s = br.in_corridor(fm.exit_origin, p) if fm.exit_kind == 'corridor' else None
        spec = fm.spec
        in_arrive = fm.arrive_kind == 'cabin' and br.in_cabin(spec.arrive, w, p)
        in_exit = fm.exit_kind in ('cabin', 'final') and br.in_cabin(spec.exit, w, p)
        depth = 0.0
        if fm.arrive_point is not None and arrive_s is None and not in_arrive:
            az = fm.arrive_point[1]
            depth = (z - az) if fm.arrive_kind == 'corridor' else (az - z)
        return Where(arrive_s=arrive_s, exit_s=exit_s, in_arrive_cabin=in_arrive, in_exit_cabin=in_exit, depth=depth)

    def update(self, dt: float):
        """After the player moved, before Combat. Returns the level events of this frame (Game swaps stages on 'swap', restarts on 'restart')."""
        g = self.game
        pl = g.player
        cur = self.current
        where = self.where(pl.x, pl.y, pl.z)
        exit_doors = [n for n, dr in cur.doors.items() if dr.kind == 'exit']
        exit_shut = all(cur.door_open[n] <= 0.0 for n in exit_doors)
        press, self.press_e = self.press_e, False
        events = self.state.update(dt, where, cur.swarm.alive_count, exit_shut, self.health.dead, press)
        self._slide_doors(dt)
        eye = (pl.x, pl.y + pl.camera_pivot.y, pl.z)
        active = not self.health.dead and self.state.phase not in (WON, FINAL)
        for ev in cur.swarm.update(min(dt, 0.05), (pl.x, pl.y, pl.z, pl.yaw), active):
            self._on_enemy_event(ev, eye)
        cur.view.update(cur.swarm, self.hall.local_ambient)
        self.health.update(dt)
        pl.frozen = self.state.phase == DEAD
        pl.slump = min(1.0, pl.slump + dt * 1.6) if self.state.phase == DEAD else 0.0
        self._ride(dt)
        self._prompt(dt, where)
        for e in events:
            self._on_level_event(e)
        return events

    def _slide_doors(self, dt: float):
        cur = self.current
        targets = {'exit': self.state.door['exit'], 'arrive': self.state.door['arrive'], 'dead': 0.0}
        pl = self.game.player
        for name, dr in cur.doors.items():
            want = targets.get(dr.kind, 0.0)
            v = cur.door_open[name]
            speed = DOOR_SPEED['lift' if dr.slide[1] == 0.0 else 'corridor']
            nv = min(want, v + speed * dt) if want > v else max(want, v - speed * dt)
            moving = nv != v
            if moving and not self._door_moving.get(dr.kind) and dr.kind != 'dead':
                self.sounds.play('door_slide', tuple((dr.lo[i] + dr.hi[i]) / 2 for i in range(3)), (pl.x, pl.y + 1.6, pl.z))
            cur.door_open[name] = nv
        for kind in ('exit', 'arrive'):
            self._door_moving[kind] = any(cur.door_open[n] not in (0.0, 1.0) for n, dr in cur.doors.items() if dr.kind == kind)
        solids, boxes = [], []
        for name, dr in cur.doors.items():
            if cur.door_open[name] < 0.98:
                lo, hi = br.door_box(dr, cur.door_open[name])
                solids.append((lo, hi))
                boxes.append((lo, hi, dr))
        cur.terrain.dynamic = solids
        self.game.combat.dynamic_boxes = boxes
        cur.door_view.update(cur.door_open)

    def _ride(self, dt: float):
        """The lift ride: small jolts while the cabin hums (the frame shakes, the world does not move)."""
        if self.state.phase not in (RIDE, FINAL):
            self._shake_t = 0.0
            return
        self._shake_t -= dt
        if self._shake_t <= 0.0:
            self._shake_t = random.uniform(0.35, 0.7)
            if self.game.shake is not None:
                self.game.shake.on_beat('mag_out')

    def _prompt(self, dt: float, where: Where):
        self._prompt_t -= dt
        if self.state.phase == CLEAR and where.in_exit_cabin and self._prompt_t <= 0.0:
            self.game.notice_low.show('E: đi thang máy', 1.2)
            self._prompt_t = 1.0

    def _on_enemy_event(self, ev, eye):
        pos = (ev.enemy.x, ev.enemy.y + 1.2, ev.enemy.z)
        if ev.kind == 'hit':
            self.health.hit(ev.damage)
            pl = self.game.player
            pl.vx += ev.push[0]
            pl.vz += ev.push[1]
            if self.game.shake is not None:
                self.game.shake.on_beat('seat')
                self.game.shake.on_shot(scale=2.0)
            self.sounds.play('strike', pos, eye)
            self.sounds.play('player_hurt')
        elif ev.kind == 'windup':
            self.sounds.play('windup', pos, eye)
        elif ev.kind == 'alert':
            if ev.enemy.id % 3 == 0:                          # not every one of a group: a wall of groans
                self.sounds.play('alert', pos, eye)
        elif ev.kind == 'hurt':
            self.sounds.play('hurt', pos, eye)
        elif ev.kind == 'death':
            self.sounds.play('die', pos, eye)
            left = self.current.swarm.alive_count
            if left > 0:
                self.game.notice_low.show(f'Còn {left}', 1.4)

    def _on_level_event(self, e: str):
        g = self.game
        k = self.state.stage
        if e == 'clear':
            if k >= 1:
                g.notice.show('Tầng đã sạch, thang máy mở.', 3.0)
            if k + 1 < br.stage_count() and self.next is None:
                self.next = Floor(g, k + 1)                   # built now (no enemy left): swapped in on the stairs / during the ride
        elif e == 'board':
            if self.state.last:
                self.sounds.play('lift_hum', rate=1.0)
        elif e == 'swap':
            if self.state.phase == RIDE:
                self.sounds.play('lift_hum', rate=1.0)
        elif e == 'arrived':
            self.sounds.play('lift_ding', rate=1.0)
        elif e == 'won':
            g.notice.show(f'Thoát khỏi Poolrooms. Thời gian: {fmt_time(self.state.clock)}. Nhấn Enter để chơi lại', 1e9)
        elif e == 'died':
            g.notice.show('Bạn gục. Chơi lại từ tầng 1', self.p.health.death_time)

    def on_bullet(self, hit, bullet, distance: float):
        """Combat: a bullet entered an enemy capsule. hit = (t, enemy, head)."""
        _, e, head = hit
        d = falloff_damage(self.game.combat.gun, distance)
        vx, vz = bullet.vel[0], bullet.vel[2]
        sp = math.hypot(vx, vz) or 1.0
        push = 0.8 / max(e.kind.hp / 100.0, 1.0)
        eye = (self.game.player.x, self.game.player.y + 1.6, self.game.player.z)
        for ev in self.current.swarm.damage(e, d, head, (vx / sp * push, vz / sp * push)):
            self._on_enemy_event(ev, eye)

    def hit_test(self, p0, p1):
        return self.current.swarm.hit_test(p0, p1)

    def on_gunshot(self, x: float, z: float):
        eye = (x, 1.6, z)
        for ev in self.current.swarm.on_noise(x, z, self.p.enemy.hearing):
            self._on_enemy_event(ev, eye)

    def hurt_inputs(self) -> tuple:
        return self.health.hurt_inputs()

    # --- stage changes (Game does the wiring) ---
    def take_next(self) -> tuple:
        """The prepared next stage becomes current: (old stage, offset to add to the player's position). Game destroys the old stage once rewired."""
        old = self.current
        if self.next is None:
            self.next = Floor(self.game, old.k + 1)
        new, self.next = self.next, None
        self.current = new
        new.show()
        old.view.clear()
        return old, br.transfer(old.k)

    def restart(self):
        """Back to floor 1 (after a death, or Enter after the win): returns the old stage to destroy."""
        old = self.current
        if self.next is not None:
            self.next.destroy()
            self.next = None
        self.state.restart(1)
        self.health.reset()
        self.current = Floor(self.game, 1)
        self.current.show()
        old.view.clear()
        return old

    def floor_title(self) -> str:
        k = self.current.k
        if k == 0:
            return ''
        return f'Tầng {k} / {len(BACKROOMS)} · {self.current.fm.spec.name}'
