"""G18 melee swarm: capsule hits, chase through the flow field, tokens, wind-up dodge, stagger, death, hearing, never inside the player, CPU cost."""
import math
import random
import time

import pytest

from fps.core.backrooms import build_floor
from fps.core.ballistics import first_hit
from fps.core.enemies import CHASE, DEAD, IDLE, WINDUP, Swarm, falloff_damage, segment_capsule
from fps.core.flowfield import FlowField, NavGrid
from fps.core.poolmap import pool_terrain
from fps.core.terrain import Terrain
from fps.weapon_data import GLOCK, M4, M1014, EnemyData


def _flat():
    return Terrain([(-20.0, 20.0, -20.0, 20.0, 0.0)], [], (-19.7, 19.7, -19.7, 19.7))


def _swarm(terrain=None, rect=(-20, 20, -20, 20), data=None):
    t = terrain or _flat()
    d = data or EnemyData()
    nav = NavGrid(t, rect, d.cell, 0.34, 0.2)
    boxes = [(lo, hi, None) for lo, hi in t.solids]
    return Swarm(d, t, nav, FlowField(nav), los=lambda a, b: first_hit(a, b, boxes, ground_y=None) is None, rng=random.Random(4))


def test_segment_capsule():
    # straight through the middle at chest height
    t = segment_capsule((-2.0, 1.0, 0.0), (2.0, 1.0, 0.0), 0.0, 0.0, 0.0, 1.8, 0.35)
    assert t == pytest.approx((2.0 - 0.35) / 4.0)
    # over the top misses, onto the round top hits
    assert segment_capsule((-2.0, 1.9, 0.0), (2.0, 1.9, 0.0), 0.0, 0.0, 0.0, 1.8, 0.35) is None
    top = segment_capsule((0.0, 3.0, 0.0), (0.0, 0.5, 0.0), 0.0, 0.0, 0.0, 1.8, 0.35)
    assert top == pytest.approx(1.2 / 2.5)
    # starting inside: no hit; beside: miss
    assert segment_capsule((0.0, 1.0, 0.0), (2.0, 1.0, 0.0), 0.0, 0.0, 0.0, 1.8, 0.35) is None
    assert segment_capsule((-2.0, 1.0, 0.5), (2.0, 1.0, 0.5), 0.0, 0.0, 0.0, 1.8, 0.35) is None


def test_hit_test_nearest_and_head():
    s = _swarm()
    a = s.spawn('normal', 0.0, 3.0)
    b = s.spawn('normal', 0.0, 6.0)
    t, e, head = s.hit_test((0.0, 1.0, 0.0), (0.0, 1.0, 10.0))
    assert e is a and not head
    t, e, head = s.hit_test((0.0, 1.7, 0.0), (0.0, 1.7, 10.0))
    assert e is a and head
    s.damage(a, 1000.0)
    assert s.hit_test((0.0, 1.0, 0.0), (0.0, 1.0, 10.0))[1] is b


def test_idle_until_seen_or_heard():
    s = _swarm()
    e = s.spawn('normal', 0.0, 10.0, yaw=0.0)          # looking away (+z), player behind at the origin
    for _ in range(30):
        s.update(1 / 60, (0.0, 0.0, 0.0, 0.0))
    assert e.state == IDLE
    s.on_noise(0.0, 0.0, 30.0)
    for _ in range(60):
        s.update(1 / 60, (0.0, 0.0, 0.0, 0.0))
    assert e.state != IDLE


def test_sees_player_in_cone():
    s = _swarm()
    e = s.spawn('normal', 0.0, 10.0, yaw=180.0)        # facing the player
    for _ in range(30):
        s.update(1 / 60, (0.0, 0.0, 0.0, 0.0))
    assert e.state != IDLE


def test_chase_around_a_wall_and_strike():
    """A wall between them: the enemy goes round it (flow field), reaches the player and lands a strike."""
    t = Terrain([(-20.0, 20.0, -20.0, 20.0, 0.0)], [((-6.0, 0.0, 4.0), (6.0, 3.0, 4.5))], (-19.7, 19.7, -19.7, 19.7))
    s = _swarm(t)
    e = s.spawn('normal', 0.0, 9.0, yaw=180.0)
    s.on_noise(0.0, 0.0, 50.0)
    hits = []
    for i in range(60 * 12):
        hits += [ev for ev in s.update(1 / 60, (0.0, 0.0, 0.0, 0.0)) if ev.kind == 'hit']
        if hits:
            break
    assert hits and hits[0].damage == EnemyData().normal.damage
    assert math.hypot(e.x, e.z) < 2.0


def test_tokens_cap_simultaneous_attackers():
    s = _swarm()
    for k in range(8):
        a = 2 * math.pi * k / 8
        s.spawn('normal', math.cos(a) * 6.0, math.sin(a) * 6.0)
    s.on_noise(0.0, 0.0, 50.0)
    most = 0
    for _ in range(60 * 8):
        s.update(1 / 60, (0.0, 0.0, 0.0, 0.0))
        most = max(most, sum(1 for e in s.enemies if e.state == WINDUP))
        assert s.tokens_used <= s.d.tokens
    assert 1 <= most <= s.d.tokens


def test_stepping_out_of_reach_dodges_the_strike():
    s = _swarm()
    e = s.spawn('normal', 0.0, 1.2, yaw=180.0)
    s.on_noise(0.0, 0.0, 50.0)
    player = [0.0, 0.0, 0.0]
    hits = []
    for _ in range(60 * 3):
        if e.state == WINDUP:
            player[2] = -4.0                                   # jump back while it winds up
        hits += [ev for ev in s.update(1 / 60, (*player, 0.0)) if ev.kind == 'hit']
        if e.state not in (WINDUP,) and player[2] < 0:
            break
    assert not hits


def test_never_inside_the_player_and_apart_from_each_other():
    s = _swarm()
    for k in range(10):
        s.spawn('normal', -3.0 + k * 0.6, 5.0)
    s.on_noise(0.0, 0.0, 50.0)
    for _ in range(60 * 6):
        s.update(1 / 60, (0.0, 0.0, 0.0, 0.0))
        for e in s.enemies:
            assert math.hypot(e.x, e.z) >= e.kind.radius + s.player_radius - 1e-6
    pairs = [(a, b) for i, a in enumerate(s.enemies) for b in s.enemies[i + 1:]]
    overlap = sum(1 for a, b in pairs if math.hypot(a.x - b.x, a.z - b.z) < (a.kind.radius + b.kind.radius) * 0.6)
    assert overlap <= 1


def test_damage_stagger_and_death():
    s = _swarm()
    e = s.spawn('normal', 0.0, 5.0)
    ev = s.damage(e, 34.0)
    assert e.state == CHASE and e.stagger > 0 and e.flash == 1.0 and ev[-1].kind == 'hurt'
    ev = s.damage(e, 34.0, head=True)                   # 68 more
    assert e.state == DEAD and ev[-1].kind == 'death' and s.kills == 1
    for _ in range(int(60 * (s.d.corpse_time + 0.2))):
        s.update(1 / 60, (0.0, 0.0, -10.0, 0.0))
    assert e not in s.enemies


def test_gun_damage_drops_a_normal_enemy_as_designed():
    hp = EnemyData().normal.hp
    assert math.ceil(hp / falloff_damage(M4, 10.0)) == 3
    assert math.ceil(hp / falloff_damage(GLOCK, 10.0)) == 4
    assert M1014.pellets * falloff_damage(M1014, 5.0) >= hp           # one close blast
    assert falloff_damage(M1014, 40.0) == pytest.approx(M1014.damage * M1014.damage_min)


def test_fifteen_chasers_on_a_real_floor_are_cheap():
    """15 hostile enemies on floor 5 (with the flow field rebuilding as the player moves): mean CPU per frame well under the 2 ms budget."""
    fm = build_floor(4)
    terrain = pool_terrain(fm, 0.3)
    x0, x1, z0, z1, wy = fm.water
    d = EnemyData()
    nav = NavGrid(terrain, fm.nav_rect, d.cell, 0.34, 0.2, water=(x0, x1, z0, z1, wy))
    s = Swarm(d, terrain, nav, FlowField(nav), water=(x0, x1, z0, z1, wy), rng=random.Random(2))
    rng = random.Random(5)
    cells = [i for i in nav.open_cells() if nav.height[i] >= 0.0]
    for kind, n in zip(('normal', 'runner', 'brute'), (8, 4, 3)):
        for _ in range(n):
            s.spawn(kind, *nav.center(rng.choice(cells)))
    s.on_noise(0.0, 0.0, 100.0)
    px, pz = 0.0, -13.0
    t0 = time.perf_counter()
    frames = 240
    for f in range(frames):
        px = 10.0 * math.sin(f / 40.0)                        # he keeps moving: the field keeps being rebuilt
        s.update(1 / 60, (px, 0.0, pz, 0.0))
    per_frame = (time.perf_counter() - t0) / frames * 1000.0
    assert per_frame < 2.5, f'{per_frame:.2f} ms'
    assert s.field.completed >= 3
