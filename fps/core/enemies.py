"""The melee swarm of the Backrooms level (G18, pure, tests/test_enemies.py; skill `enemy-swarm-ai`).

Each enemy is a vertical capsule that walks the same terrain as the player (`resolve_move`: walls, pillars, the pool edge and steps cannot be cheated).
Per frame (`Swarm.update`):
- the shared flow field toward the player is advanced by a time slice (core/flowfield.py);
- perception, staggered at ~5 Hz per enemy: an idle enemy notices the player inside its view cone and range with a clear line of sight; a gunshot alerts everyone
  within `hearing`, and an enemy that turns hostile alerts its neighbours within `shout`;
- steering: with a clear line to a close player it runs straight at him, bent sideways by its own flank angle so the group surrounds him; otherwise it follows the
  flow field; neighbours push each other apart (separation); without an attack token it circles at `hold_ring` instead of crowding in;
- attack: an enemy in reach takes one of the shared tokens (Doom 2016: at most `tokens` attack at once), winds up (telegraph, a step out of reach dodges it), strikes
  if the player is still in reach and in front, recovers, gives the token back;
- a bullet hit staggers it (and cancels a wind-up); at 0 HP it dies, falls and is removed after `corpse_time`.
"""
import math
import random
from dataclasses import dataclass

from fps.core.terrain import resolve_move

IDLE, ALERT, CHASE, WINDUP, RECOVER, DEAD = 'idle', 'alert', 'chase', 'windup', 'recover', 'dead'
SENSE_PERIOD = 0.2          # s between two perception checks of one enemy (staggered over the swarm)
GRAVITY = 18.0
HASH_CELL = 2.0


def segment_capsule(p0, p1, cx: float, cz: float, y0: float, y1: float, r: float):
    """First t in [0, 1] where the segment p0 -> p1 enters the vertical capsule (axis x = cx, z = cz, from y0 to y1 including the round ends, radius r), or None.
    The capsule = a cylinder between the end-sphere centres (y0 + r .. y1 - r) plus two spheres; the earliest entry into that union is the entry into the capsule.
    A segment that starts inside counts as no hit (like `segment_vs_aabb`)."""
    ya, yb = y0 + r, max(y1 - r, y0 + r)
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    ox, oz = p0[0] - cx, p0[2] - cz
    # inside?
    yc = min(max(p0[1], ya), yb)
    if ox * ox + (p0[1] - yc) ** 2 + oz * oz < r * r:
        return None
    best = None
    a = dx * dx + dz * dz
    if a > 1e-12:
        b = 2.0 * (ox * dx + oz * dz)
        c = ox * ox + oz * oz - r * r
        disc = b * b - 4.0 * a * c
        if disc >= 0.0:
            t = (-b - math.sqrt(disc)) / (2.0 * a)
            if 0.0 <= t <= 1.0 and ya <= p0[1] + dy * t <= yb:
                best = t
    for sy in (ya, yb):
        oy = p0[1] - sy
        a2 = dx * dx + dy * dy + dz * dz
        if a2 < 1e-12:
            continue
        b2 = 2.0 * (ox * dx + oy * dy + oz * dz)
        c2 = ox * ox + oy * oy + oz * oz - r * r
        disc = b2 * b2 - 4.0 * a2 * c2
        if disc < 0.0:
            continue
        t = (-b2 - math.sqrt(disc)) / (2.0 * a2)
        if 0.0 <= t <= 1.0 and (best is None or t < best):
            best = t
    return best


def angle_diff(a: float, b: float) -> float:
    """b - a in degrees, wrapped to (-180, 180]."""
    d = (b - a) % 360.0
    return d - 360.0 if d > 180.0 else d


def yaw_of(dx: float, dz: float) -> float:
    """Ursina yaw (degrees, 0 = +z, 90 = +x) of a direction on the floor."""
    return math.degrees(math.atan2(dx, dz))


@dataclass
class Enemy:
    kind_name: str
    kind: object                  # weapon_data.EnemyKind
    x: float
    y: float
    z: float
    yaw: float = 0.0
    hp: float = 100.0
    vx: float = 0.0
    vz: float = 0.0
    vy: float = 0.0
    state: str = IDLE
    timer: float = 0.0            # time left in ALERT / WINDUP / RECOVER
    token: bool = False
    flank: float = 1.0            # +1 / -1: which side of the player it goes round
    sense_t: float = 0.0          # time to the next perception check
    sees: bool = False            # clear line to the player at the last check
    stagger: float = 0.0
    flash: float = 0.0            # 1 right after a bullet hit, fades (drawn white)
    lean: float = 0.0             # 0..1 wind-up lean (drawn), back to 0 after the strike
    dead_t: float = 0.0
    fall: float = 0.0             # 0 standing .. 1 lying (drawn)
    on_ground: bool = True
    wander: tuple = None          # idle wander target
    wander_t: float = 0.0
    id: int = 0

    @property
    def alive(self) -> bool:
        return self.state != DEAD

    @property
    def hostile(self) -> bool:
        return self.state in (CHASE, WINDUP, RECOVER)


@dataclass
class Event:
    kind: str                     # 'hit' (the player is struck), 'death', 'alert', 'windup', 'hurt'
    enemy: Enemy
    damage: float = 0.0
    push: tuple = (0.0, 0.0)      # knockback velocity on the player
    head: bool = False


class Swarm:
    def __init__(self, data, terrain, nav, field, los=None, water: tuple = None, step_up: float = 0.2, rng: random.Random = None):
        """data = weapon_data.EnemyData; terrain = core.terrain.Terrain; nav / field = core.flowfield NavGrid / FlowField; los(p0, p1) -> True when nothing blocks the
        segment (None = always clear); water = (x0, x1, z0, z1, surface y) or None."""
        self.d = data
        self.terrain, self.nav, self.field = terrain, nav, field
        self.los = los or (lambda a, b: True)
        self.water = water
        self.step_up = step_up
        self.rng = rng or random.Random(1)
        self.enemies = []
        self.tokens_used = 0
        self.kills = 0
        self._next_id = 0
        self.player_radius = 0.30

    # --- population ---
    def spawn(self, kind_name: str, x: float, z: float, yaw: float = None) -> Enemy:
        kind = getattr(self.d, kind_name)
        y = self.terrain.floor_at(x, z, 50.0)
        e = Enemy(kind_name, kind, x, 0.0 if y is None else y, z, yaw=self.rng.uniform(0, 360) if yaw is None else yaw, hp=kind.hp,
                  flank=self.rng.choice((-1.0, 1.0)), sense_t=self.rng.uniform(0, SENSE_PERIOD), id=self._next_id)
        self._next_id += 1
        self.enemies.append(e)
        return e

    @property
    def alive_count(self) -> int:
        return sum(1 for e in self.enemies if e.alive)

    # --- outside events ---
    def alert(self, e: Enemy, events: list, delay: float = None):
        if e.state != IDLE:
            return
        e.state, e.timer = ALERT, self.d.alert_delay if delay is None else delay
        events.append(Event('alert', e))
        for o in self.enemies:                                  # shout: the neighbours turn too (a little later)
            if o is not e and o.state == IDLE and (o.x - e.x) ** 2 + (o.z - e.z) ** 2 < self.d.shout ** 2:
                o.state, o.timer = ALERT, self.d.alert_delay + 0.25
                events.append(Event('alert', o))

    def on_noise(self, x: float, z: float, radius: float) -> list:
        """A gunshot at (x, z): every idle enemy within `radius` turns hostile."""
        events = []
        for e in self.enemies:
            if e.state == IDLE and (e.x - x) ** 2 + (e.z - z) ** 2 < radius * radius:
                self.alert(e, events, self.d.alert_delay * self.rng.uniform(0.6, 1.4))
        return events

    def hit_test(self, p0, p1):
        """Nearest enemy the segment p0 -> p1 enters: (t, enemy, head) or None."""
        best = None
        lo_x, hi_x = min(p0[0], p1[0]), max(p0[0], p1[0])
        lo_z, hi_z = min(p0[2], p1[2]), max(p0[2], p1[2])
        for e in self.enemies:
            if not e.alive:
                continue
            r = e.kind.radius
            if e.x + r < lo_x or e.x - r > hi_x or e.z + r < lo_z or e.z - r > hi_z:
                continue
            t = segment_capsule(p0, p1, e.x, e.z, e.y, e.y + e.kind.height, r)
            if t is not None and (best is None or t < best[0]):
                hy = p0[1] + (p1[1] - p0[1]) * t
                best = (t, e, hy >= e.y + e.kind.height * (1.0 - e.kind.head_share))
        return best

    def damage(self, e: Enemy, amount: float, head: bool = False, push: tuple = (0.0, 0.0)) -> list:
        """A bullet hit. Returns events ('hurt', and 'death' at 0 HP)."""
        events = []
        if not e.alive:
            return events
        amount *= self.d.headshot if head else 1.0
        e.hp -= amount
        e.flash = 1.0
        e.stagger = max(e.stagger, e.kind.stagger)
        e.vx += push[0]
        e.vz += push[1]
        if e.state == WINDUP:                                  # a hit cancels the wind-up (the token goes back)
            self._release(e)
            e.state, e.lean = CHASE, 0.0
        if e.state in (IDLE, ALERT):
            if e.state == IDLE:
                self.alert(e, events, 0.0)
            e.state, e.timer = CHASE, 0.0
        events.append(Event('hurt', e, amount, head=head))
        if e.hp <= 0.0:
            self._release(e)
            e.state, e.dead_t, e.hp = DEAD, 0.0, 0.0
            self.kills += 1
            events.append(Event('death', e, head=head))
        return events

    def _release(self, e: Enemy):
        if e.token:
            e.token = False
            self.tokens_used -= 1

    # --- per frame ---
    def update(self, dt: float, player: tuple, player_alive: bool = True) -> list:
        """player = (x, y, z, yaw). Returns the events of this frame."""
        d = self.d
        events = []
        px, py, pz = player[0], player[1], player[2]
        if self.field is not None and self.nav is not None and player_alive:
            goal = self.nav.index(px, pz)
            if not self.nav.open(goal):
                goal = self.nav.nearest_open(px, pz)
            self.field.request(goal)
            self.field.step(d.field_budget)
        # spatial hash for separation
        grid = {}
        for e in self.enemies:
            if e.alive:
                grid.setdefault((int(e.x // HASH_CELL), int(e.z // HASH_CELL)), []).append(e)
        keep = []
        for e in self.enemies:
            if e.alive:
                self._update_one(e, dt, px, py, pz, player_alive, grid, events)
                keep.append(e)
            else:
                e.dead_t += dt
                e.fall = min(1.0, e.fall + dt / 0.45)
                e.flash = max(0.0, e.flash - dt * 4.0)
                if e.dead_t < d.corpse_time:
                    keep.append(e)
        self.enemies = keep
        return events

    def _update_one(self, e: Enemy, dt: float, px, py, pz, player_alive, grid, events):
        d, k = self.d, e.kind
        e.flash = max(0.0, e.flash - dt * 5.0)
        e.stagger = max(0.0, e.stagger - dt)
        tx, tz = px - e.x, pz - e.z
        dist = math.hypot(tx, tz)
        reach_d = dist - self.player_radius                   # from the capsule centre line to the player's body
        # perception (staggered)
        e.sense_t -= dt
        if e.sense_t <= 0.0:
            e.sense_t += SENSE_PERIOD
            eye = (e.x, e.y + k.height * 0.85, e.z)
            target = (px, py + 1.4, pz)
            in_range = dist < d.view_range
            if e.state == IDLE:
                cone = abs(angle_diff(e.yaw, yaw_of(tx, tz))) <= d.view_cone / 2.0
                e.sees = player_alive and in_range and cone and self.los(eye, target)
                if e.sees:
                    self.alert(e, events)
            else:
                e.sees = player_alive and dist < d.seek_range and self.los(eye, target)
        # state machine
        want_x = want_z = 0.0
        speed = k.speed
        face = None
        if not player_alive and e.state != IDLE:
            self._release(e)
            e.state, e.lean = IDLE, 0.0
        if e.state == IDLE:
            speed = k.patrol_speed
            want_x, want_z = self._wander(e, dt)
        elif e.state == ALERT:
            e.timer -= dt
            face = yaw_of(tx, tz)
            if e.timer <= 0.0:
                e.state = CHASE
        elif e.state == WINDUP:
            e.timer -= dt
            e.lean = min(1.0, e.lean + dt / max(k.windup, 1e-3))
            face = yaw_of(tx, tz)
            if dist > 0.05:                                     # a small lunge
                want_x, want_z = tx / dist * 0.35, tz / dist * 0.35
            if e.timer <= 0.0:
                facing = abs(angle_diff(e.yaw, yaw_of(tx, tz))) <= 70.0
                if reach_d <= k.reach + 0.15 and facing and player_alive:
                    push = (tx / dist * k.knockback, tz / dist * k.knockback) if dist > 1e-6 else (0.0, 0.0)
                    events.append(Event('hit', e, k.damage, push))
                e.state, e.timer = RECOVER, k.recover
        elif e.state == RECOVER:
            e.timer -= dt
            e.lean = max(0.0, e.lean - dt / 0.25)
            speed = k.speed * 0.35
            want_x, want_z = self._chase_dir(e, tx, tz, dist)
            if e.timer <= 0.0:
                self._release(e)
                e.state = CHASE
        if e.state == CHASE:
            e.lean = max(0.0, e.lean - dt / 0.25)
            if reach_d <= k.reach and e.stagger <= 0.0 and (e.token or self.tokens_used < d.tokens):
                if not e.token:
                    e.token = True
                    self.tokens_used += 1
                e.state, e.timer = WINDUP, k.windup
                events.append(Event('windup', e))
                face = yaw_of(tx, tz)
            elif not e.token and dist < d.hold_ring + 0.4 and self.tokens_used >= d.tokens:
                want_x, want_z = self._hold(e, tx, tz, dist)  # no token: circle at the ring instead of crowding in
                face = yaw_of(tx, tz)
            else:
                want_x, want_z = self._chase_dir(e, tx, tz, dist)
        # separation
        sx = sz = 0.0
        gx, gz = int(e.x // HASH_CELL), int(e.z // HASH_CELL)
        for cx in (gx - 1, gx, gx + 1):
            for cz in (gz - 1, gz, gz + 1):
                for o in grid.get((cx, cz), ()):
                    if o is e:
                        continue
                    ox, oz = e.x - o.x, e.z - o.z
                    reach = k.radius + o.kind.radius + 0.5
                    dd = ox * ox + oz * oz
                    if dd < reach * reach and dd > 1e-10:
                        dl = math.sqrt(dd)
                        w = (1.0 - dl / reach)
                        sx += ox / dl * w
                        sz += oz / dl * w
        want_x += sx * d.separation
        want_z += sz * d.separation
        wl = math.hypot(want_x, want_z)
        if wl > 1.0:
            want_x, want_z = want_x / wl, want_z / wl
        # water slows the legs (like the player's wading); stagger stops them
        slow = self._water_factor(e)
        if e.stagger > 0.0:
            slow *= 0.15
        target_vx, target_vz = want_x * speed * slow, want_z * speed * slow
        step = k.accel * dt
        dvx, dvz = target_vx - e.vx, target_vz - e.vz
        dl = math.hypot(dvx, dvz)
        if dl > step:
            dvx, dvz = dvx / dl * step, dvz / dl * step
        e.vx += dvx
        e.vz += dvz
        # move on the terrain (same physics as the player)
        x, z, e.vx, e.vz = resolve_move(self.terrain, e.x, e.z, e.y, e.vx, e.vz, dt, k.radius, self.step_up, k.height)
        # never inside the player
        ox, oz = x - px, z - pz
        min_d = k.radius + self.player_radius
        dd = ox * ox + oz * oz
        if dd < min_d * min_d and abs(e.y - py) < 1.5:
            dl = math.sqrt(dd) or 1e-6
            x, z = px + ox / dl * min_d, pz + oz / dl * min_d
        e.x, e.z = x, z
        ground = self.terrain.floor_at(x, z, e.y + self.step_up)
        ground = e.y if ground is None else ground
        if e.on_ground and ground < e.y - self.step_up:
            e.on_ground = False
        if e.on_ground:
            e.y = ground
        else:
            e.vy -= GRAVITY * dt
            e.y += e.vy * dt
            if e.y <= ground:
                e.y, e.vy, e.on_ground = ground, 0.0, True
        # facing
        if face is None and math.hypot(e.vx, e.vz) > 0.3:
            face = yaw_of(e.vx, e.vz)
        if face is not None:
            diff = angle_diff(e.yaw, face)
            turn = k.turn_rate * dt
            e.yaw = (e.yaw + max(-turn, min(turn, diff))) % 360.0

    def _chase_dir(self, e: Enemy, tx: float, tz: float, dist: float) -> tuple:
        """Straight at the player (bent by the flank angle) when he is seen and close, else the flow field."""
        d = self.d
        if dist < 1e-6:
            return 0.0, 0.0
        if e.sees and dist < d.seek_range:
            ux, uz = tx / dist, tz / dist
            k = min(max((dist - 1.6) / max(d.flank_range - 1.6, 0.1), 0.0), 1.0) if dist < d.flank_range else 1.0
            a = math.radians(d.flank_angle * e.flank * k) if dist < d.flank_range else 0.0
            ca, sa = math.cos(a), math.sin(a)
            return ux * ca + uz * sa, -ux * sa + uz * ca
        cell = self.nav.index(e.x, e.z) if self.nav else None
        if cell is not None and not self.nav.open(cell):
            cell = self.nav.nearest_open(e.x, e.z, 2)
            if cell is not None:                                # pushed into a blocked cell (against a pillar): back to the nearest open one
                cx, cz = self.nav.center(cell)
                ddx, ddz = cx - e.x, cz - e.z
                dl = math.hypot(ddx, ddz)
                if dl > 0.05:
                    return ddx / dl, ddz / dl
        dirn = self.field.direction(cell) if self.field is not None else None
        if dirn is None:
            return tx / dist, tz / dist
        return dirn

    def _hold(self, e: Enemy, tx: float, tz: float, dist: float) -> tuple:
        """Circle around the player at `hold_ring` (tangent + a radial pull toward the ring)."""
        ux, uz = tx / dist, tz / dist
        radial = (dist - self.d.hold_ring) * 1.2
        tang = 0.6 * e.flank
        return ux * radial + (-uz) * tang, uz * radial + ux * tang

    def _wander(self, e: Enemy, dt: float) -> tuple:
        e.wander_t -= dt
        if e.wander is None or e.wander_t <= 0.0:
            e.wander_t = self.rng.uniform(2.5, 6.0)
            if self.rng.random() < 0.45:
                e.wander = None                                  # stand still a while
            else:
                a = self.rng.uniform(0, 2 * math.pi)
                r = self.rng.uniform(1.5, 4.0)
                e.wander = (e.x + math.cos(a) * r, e.z + math.sin(a) * r)
        if e.wander is None:
            return 0.0, 0.0
        dx, dz = e.wander[0] - e.x, e.wander[1] - e.z
        dl = math.hypot(dx, dz)
        if dl < 0.3:
            e.wander = None
            return 0.0, 0.0
        if self.nav is not None and not self.nav.open(self.nav.index(e.x + dx / dl * 0.6, e.z + dz / dl * 0.6)):
            e.wander = None                                      # wall / pool edge ahead
            return 0.0, 0.0
        return dx / dl, dz / dl

    def _water_factor(self, e: Enemy) -> float:
        w = self.water
        if w is None or not (w[0] <= e.x <= w[1] and w[2] <= e.z <= w[3]):
            return 1.0
        depth = w[4] - e.y
        if depth <= 0.0:
            return 1.0
        return max(0.35, 1.0 - 0.45 * depth)


def falloff_damage(gun, distance: float) -> float:
    """Damage of one bullet / pellet of `gun` (GunData) after `distance` m: full up to damage_near, then linear down to damage_min x at damage_far."""
    near, far = gun.damage_near, max(gun.damage_far, gun.damage_near + 1e-3)
    t = min(max((distance - near) / (far - near), 0.0), 1.0)
    return gun.damage * (1.0 + (gun.damage_min - 1.0) * t)


def capsule_mesh(radius: float, height: float, sides: int = 18, cap_rings: int = 5) -> tuple:
    """(vertices, normals, triangles) of a vertical capsule standing on y = 0 (feet) up to y = height, front toward +z. Smooth normals."""
    rings = []                                                     # (y of the ring centre, ring radius, normal y, normal radial scale)
    yb, yt = radius, max(height - radius, radius)
    for k in range(cap_rings + 1):                                 # bottom cap, from the pole up to the equator
        a = -math.pi / 2 + (math.pi / 2) * k / cap_rings
        rings.append((yb + radius * math.sin(a), radius * math.cos(a), math.sin(a), math.cos(a)))
    for k in range(cap_rings + 1):                                 # top cap, from the equator to the pole
        a = (math.pi / 2) * k / cap_rings
        rings.append((yt + radius * math.sin(a), radius * math.cos(a), math.sin(a), math.cos(a)))
    verts, norms, tris = [], [], []
    for y, r, ny, nr in rings:
        for s in range(sides):
            t = 2.0 * math.pi * s / sides
            cx, cz = math.sin(t), math.cos(t)
            verts.append((cx * r, y, cz * r))
            norms.append((cx * nr, ny, cz * nr))
    for i in range(len(rings) - 1):
        for s in range(sides):
            a0, a1 = i * sides + s, i * sides + (s + 1) % sides
            b0, b1 = a0 + sides, a1 + sides
            tris += [(a0, a1, b0), (a1, b1, b0)]
    return verts, norms, tris
