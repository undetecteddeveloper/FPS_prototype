"""G18 Backrooms - Pool rooms in the game: one floor at a time as a PoolHall, the swarm, the doors, health, progress (core/backrooms.py, core/enemies.py, core/level.py).

Game owns the wiring that every map shares (player terrain, bullets, water, underwater, reflections); this module tells it WHEN to swap floors (`Game._enter_floor`) and runs
everything that only exists here. Per frame (Game.update, after the player moved, before Combat):
  where is the player (corridors / hall) -> LevelState phases -> door leaves slide (solid while not fully open) -> the swarm moves / strikes -> health, sounds, notices.
The floor after the current one is built the moment the current one is cleared (a short hitch while no enemy is left), and swapped in halfway up the stairs.
"""
import math
import random
import time
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.core import backrooms as br
from fps.core.ballistics import first_hit
from fps.core.enemies import falloff_damage
from fps.core.flowfield import FlowField, NavGrid
from fps.core.level import DEAD, WON, Health, LevelState, Where
from fps.core.enemies import Swarm
from fps.weapon_data import BACKROOMS

ASSET_ROOT = 'assets/maps/backrooms'
SOUND_DIR = 'assets/sounds/enemy'
DOOR_SPEED = 0.9               # door openings per second (a full slide ~1.1 s)
SPAWN_CLEAR = 9.0              # m: no enemy starts closer than this to the arrival door
NOTICE_GLYPHS = 'Tầng / 5 · Sảnh đầu Hàng cột Sảnh cao Mê cung Hồ lớn đã sạch, cầu thang mở. Còn 0123456789 Thoát khỏi Poolrooms Thời gian: Bạn gục. Chơi lại từ 1 Nhấn Enter để chơi lại'


def floor_dir(k: int) -> str:
    return f'{ASSET_ROOT}/floor{k + 1}'


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds + 0.5), 60)
    return f'{m}:{s:02d}'


class _Sounds:
    """A few voices per enemy sound (assets/sounds/enemy, tools/build/make_enemy_sounds.py); volume falls with distance from the camera. Missing files are silent."""
    VOLUME = {'alert': 0.55, 'windup': 0.6, 'strike': 0.9, 'hurt': 0.55, 'die': 0.7, 'player_hurt': 0.9}

    def __init__(self, root: Path, enabled: bool):
        self.banks = {}
        if not enabled:
            return
        loader = application.base.loader
        for name in self.VOLUME:
            path = root / SOUND_DIR / f'{name}.wav'
            if path.exists():
                self.banks[name] = [[loader.load_sfx(Filename.from_os_specific(str(path))) for _ in range(4)], 0]
        self.rng = random.Random(3)

    def play(self, name: str, pos=None, listener=None):
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
        s.set_play_rate(self.rng.uniform(0.92, 1.08))
        s.play()


class Floor:
    """Everything built for one floor: the PoolHall (room, water, bake), the swarm, the nav grid, the door leaves."""

    def __init__(self, game, k: int):
        from fps.game.enemies import DoorView, SwarmView
        from fps.game.pool import PoolHall
        p = game.params
        self.k = k
        self.fm = br.build_floor(k)
        key = br.floor_key(self.fm, p.look)
        self.hall = PoolHall(p, game.root, pm=self.fm, asset_dir=floor_dir(k), key=key, label=f'tầng {k + 1} của Backrooms', spawn=self.fm.start[:3])
        x0, x1, z0, z1, wy = self.fm.water
        self.water = (x0, x1, z0, z1, wy)
        self.terrain = self.hall.terrain(p.player.radius)
        d = p.enemy
        self.enemy_terrain = self.terrain                     # (the same boxes; enemies use their own radius in resolve_move)
        self.nav = NavGrid(self.terrain, self.fm.nav_rect, d.cell, d.normal.radius, p.player.step_up, water=self.water, deep_cost=d.deep_cost)
        self.field = FlowField(self.nav)
        index = self.hall._sun_index                          # the room's boxes without the water: what blocks a line of sight

        def los(a, b):
            return first_hit(a, b, index.segment(a, b), ground_y=None) is None
        self.swarm = Swarm(d, self.terrain, self.nav, self.field, los=los, water=self.water, step_up=p.player.step_up, rng=random.Random(self.fm.spec.seed))
        self.swarm.player_radius = p.player.radius
        self._spawn()
        self.view = SwarmView(d)
        self.doors = {dr.name: dr for dr in self.fm.doors}
        self.door_open = {name: 0.0 for name in self.doors}
        self.door_view = DoorView(self.fm.doors, self.hall.local_ambient)
        self.hall.node.hide()                                  # shown when it becomes the current floor
        self.hall.water.node.hide()
        self.door_view_hide(True)

    def _spawn(self):
        fm, nav = self.fm, self.nav
        rng = random.Random(fm.spec.seed)
        door = (fm.spec.arrive_x, -fm.data.room_z / 2.0)
        cells = [i for i in nav.open_cells() if abs(nav.height[i]) < 1e-6 and math.dist(nav.center(i), door) > SPAWN_CLEAR]
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
    def __init__(self, game, sound: bool = True, rebake: bool = False):
        self.game = game
        p = game.params
        self.p = p
        self.state = LevelState(len(BACKROOMS), br.LENGTH, br.SWAP_S, p.health.death_time)
        self.health = Health(p.health)
        self.sounds = _Sounds(game.root, sound)
        self.ensure_baked(force=rebake)
        self.current = Floor(game, 0)
        self.current.show()
        self.next = None
        self._won_shown = False
        self.notice_text = ''

    # --- light bake of every floor, before the level starts (a stale floor would otherwise bake in the middle of the game) ---
    def ensure_baked(self, force: bool = False):
        import json
        from fps.game.pool import _BakeScreen, bake_map, rail_probes, store_bake
        root = self.game.root
        for k in range(len(BACKROOMS)):
            fm = br.build_floor(k)
            key = br.floor_key(fm, self.p.look)
            folder = root / floor_dir(k)
            try:
                stored = json.loads((folder / 'meta.json').read_text(encoding='utf-8')).get('key')
            except (OSError, ValueError):
                stored = None
            if stored == key and not force:
                continue
            print(f'[backrooms] nướng ánh sáng tầng {k + 1}...')
            t0 = time.time()
            screen = _BakeScreen(f'tầng {k + 1} / {len(BACKROOMS)} của Backrooms')
            try:
                res = bake_map(fm, self.p.look, rail_probes(fm.data), lambda done, total: screen.show(done / total))
            finally:
                screen.close()
            store_bake(folder, key, res)
            print(f'[backrooms] xong tầng {k + 1} sau {time.time() - t0:.1f} s')

    @property
    def hall(self):
        return self.current.hall

    def start_pose(self) -> tuple:
        return self.current.fm.start

    # --- per frame ---
    def where(self, x: float, z: float) -> Where:
        fm = self.current.fm
        return Where(arrive_s=br.in_corridor(fm.arrive_origin, (x, 0.0, z)), exit_s=br.in_corridor(fm.exit_origin, (x, 0.0, z)),
                     hall_depth=z + fm.data.room_z / 2.0 if abs(x) <= fm.data.room_x / 2.0 and -fm.data.room_z / 2.0 <= z <= fm.data.room_z / 2.0 else 0.0)

    def update(self, dt: float):
        """After the player moved, before Combat. Returns the level events of this frame (Game swaps floors / restarts on 'swap' / 'restart')."""
        g = self.game
        pl = g.player
        cur = self.current
        where = self.where(pl.x, pl.z)
        exit_name = next(n for n, dr in cur.doors.items() if dr.kind == 'exit')
        arrive_name = next(n for n, dr in cur.doors.items() if dr.kind == 'arrive')
        exit_shut = cur.door_open[exit_name] <= 0.0
        events = self.state.update(dt, where, cur.swarm.alive_count, exit_shut, self.health.dead)
        # doors slide toward their targets; a leaf is solid for the player, enemies and bullets unless fully open
        targets = {exit_name: self.state.door['exit'], arrive_name: self.state.door['arrive']}
        for name in cur.door_open:
            want = targets.get(name, 0.0)
            v = cur.door_open[name]
            cur.door_open[name] = min(want, v + DOOR_SPEED * dt) if want > v else max(want, v - DOOR_SPEED * dt)
        self._door_solids()
        cur.door_view.update(cur.door_open)
        # swarm
        eye = (pl.x, pl.y + pl.camera_pivot.y, pl.z)
        for ev in cur.swarm.update(min(dt, 0.05), (pl.x, pl.y, pl.z, pl.yaw), not self.health.dead and self.state.phase != WON):
            self._on_enemy_event(ev, eye)
        cur.view.update(cur.swarm, self.hall.local_ambient)
        self.health.update(dt)
        # the player down on the floor while dead
        pl.frozen = self.state.phase == DEAD
        pl.slump = min(1.0, pl.slump + dt * 1.6) if self.state.phase == DEAD else 0.0
        for e in events:
            self._on_level_event(e)
        return events

    def _door_solids(self):
        cur = self.current
        solids, boxes = [], []
        for name, dr in cur.doors.items():
            if cur.door_open[name] < 0.98:
                lo, hi = br.door_box(dr, cur.door_open[name])
                solids.append((lo, hi))
                boxes.append((lo, hi, dr))
        cur.terrain.dynamic = solids
        self.game.combat.dynamic_boxes = boxes

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
        k = self.state.floor
        if e == 'clear':
            g.notice.show('Tầng đã sạch, cầu thang mở.', 3.0)
            if k + 1 < len(BACKROOMS) and self.next is None:
                self.next = Floor(g, k + 1)                   # built now (no enemy left): swapped in halfway up the stairs
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

    # --- floor changes (Game does the wiring) ---
    def take_next(self) -> tuple:
        """The prepared next floor becomes current: (new floor, offset to add to the player's position). The old floor is destroyed by Game once rewired."""
        old = self.current
        if self.next is None:
            self.next = Floor(self.game, old.k + 1)
        new, self.next = self.next, None
        self.current = new
        new.show()
        old.view.clear()
        return old, br.transfer(old.k)

    def restart(self) -> object:
        """Back to floor 1 (after a death, or Enter after the win): returns the old floor to destroy."""
        old = self.current
        if self.next is not None:
            self.next.destroy()
            self.next = None
        self.state.restart()
        self.health.reset()
        self.current = Floor(self.game, 0)
        self.current.show()
        old.view.clear()
        return old

    def floor_title(self) -> str:
        k = self.current.k
        return f'Tầng {k + 1} / {len(BACKROOMS)} · {self.current.fm.spec.name}'
