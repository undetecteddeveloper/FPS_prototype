"""G18 / G19 the stages of the run: geometry sanity, identical cabins / corridors on both sides of a swap, reachability, heights, light density."""
import math

import pytest

from fps.core import backrooms as br
from fps.core.flowfield import NavGrid
from fps.core.poolmap import build_map, is_air, pool_terrain
from fps.weapon_data import BACKROOMS, BACKROOMS_DENSITY, LookData, MapData, PlayerParams

STAGES = [br.build_stage(k) for k in range(br.stage_count())]
FLOORS = STAGES[1:]


def _same_air(a, oa, b, ob, lo, hi, step=0.2):
    """Sample is_air on a grid around the frame origins (relative box lo..hi): the two maps must agree everywhere. Returns the mismatches."""
    bad = []
    n = [max(1, round((hi[i] - lo[i]) / step)) for i in range(3)]
    for i in range(n[0] + 1):
        for j in range(n[1] + 1):
            for k in range(n[2] + 1):
                r = (lo[0] + (hi[0] - lo[0]) * (i + 0.37) / (n[0] + 1), lo[1] + (hi[1] - lo[1]) * (j + 0.41) / (n[1] + 1), lo[2] + (hi[2] - lo[2]) * (k + 0.43) / (n[2] + 1))
                pa = tuple(oa[q] + r[q] for q in range(3))
                pb = tuple(ob[q] + r[q] for q in range(3))
                if is_air(a, pa) != is_air(b, pb):
                    bad.append(r)
    return bad


@pytest.mark.parametrize('k', range(1, len(BACKROOMS)))
def test_lift_cabins_are_identical_on_both_sides(k):
    a, b = STAGES[k], STAGES[k + 1]
    ea, ab = a.spec.exit, b.spec.arrive
    for c in (ea, ab):
        for v in (c.x, c.y, c.z):
            assert abs(v / 1.2 - round(v / 1.2)) < 1e-9, f'cabin frame {c} is not on the 1.2 m tile grid'
    w = a.data.wall
    lo, hi = (-br.CAB_W / 2 - 0.3, 0.05, 0.02), (br.CAB_W / 2 + 0.3, br.CAB_H + 0.3, w + br.CAB_D + 0.3)      # the cabin, its walls, the door hole (not the room)
    assert not _same_air(a, br.cabin_frame(ea), b, br.cabin_frame(ab), lo, hi)
    t = br.transfer(k)
    assert all(abs(br.cabin_frame(ea)[i] + t[i] - br.cabin_frame(ab)[i]) < 1e-9 for i in range(3))


def test_pool_corridor_matches_floor_one_corridor():
    a, b = STAGES[0], STAGES[1]
    w = MapData().wall
    lo, hi = (-br.C_WIDTH / 2 - 0.2, 0.05, 0.3), (br.C_WIDTH / 2 + 0.2, br.CLIMB + br.CLEAR - 0.05, br.LENGTH - 0.3)
    assert not _same_air(a, a.exit_origin, b, b.arrive_origin, lo, hi)
    t = br.transfer(0)
    assert all(abs(a.exit_origin[i] + t[i] - b.arrive_origin[i]) < 1e-9 for i in range(3))
    assert w > 0


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_rooms_do_not_overlap(fm):
    vols = [(n, lo, hi) for n, lo, hi, _ in fm.airs]
    d = fm.data
    outer = ((-d.room_x / 2 - d.wall, -9, -d.room_z / 2 - d.wall), (d.room_x / 2 + d.wall, 99, d.room_z / 2 + d.wall))
    for i, (n1, lo1, hi1) in enumerate(vols):
        for n2, lo2, hi2 in vols[i + 1:]:
            assert not br.overlap(lo1, hi1, lo2, hi2), (n1, n2)
        if n1 != 'hall':
            assert not br.overlap(lo1, hi1, *outer), f'{n1} reaches into the hall walls'


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_floor_is_sane(fm):
    d = fm.data
    hx, hz = d.room_x / 2, d.room_z / 2
    px, pz = d.pool_x / 2, d.pool_z / 2
    assert -pz + d.steps * d.step_depth < d.slope_z[0] < d.slope_z[1] < pz
    for x, z, s in fm.spec.pillars:
        assert not (abs(x) - s / 2 < px and abs(z) - s / 2 < pz), f'pillar {x, z} stands in the pool'
    assert 4 <= len(fm.airs) - (2 if fm.arrive_kind == 'cabin' else 1) + 1 <= 7          # the hall + 3-5 rooms ("4-6 rooms")
    assert any(kind in ('dark', 'red') for _, _, _, kind in fm.airs), 'no dark / red room'
    assert sorted(dr.kind for dr in fm.doors).count('exit') == 2                          # the two lift leaves
    assert br.RISE <= PlayerParams().step_up
    for dr in fm.doors:
        mid = tuple((dr.lo[i] + dr.hi[i]) / 2 for i in range(3))
        assert is_air(fm, mid), dr.name


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_light_density_like_floor_one(fm):
    """Every lit room has about the panel density of the floor-1 reference (no glare); dark rooms far less."""
    lights = br.emitters(fm)
    for name, lo, hi, kind in fm.airs:
        if kind == 'cabin':
            continue
        area = (hi[0] - lo[0]) * (hi[2] - lo[2])
        panels = sum((h[0] - l[0]) * (h[2] - l[2]) for l, h, _ in lights if lo[0] <= (l[0] + h[0]) / 2 <= hi[0] and lo[2] <= (l[2] + h[2]) / 2 <= hi[2]
                     and abs(h[1] - hi[1]) < 1e-6)
        density = panels / area
        target = BACKROOMS_DENSITY[kind]
        assert density <= target * 1.6 + 1e-9 or panels <= 0.72 + 1e-9, (name, kind, density)
        if kind == 'lit' and area > 40:
            assert density >= target * 0.55, (name, density)


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_whole_floor_reachable_and_several_heights(fm):
    """From where he comes in, every open nav cell (minus a few boxed in by pillars) can be reached, including the cell in front of the exit lift; the floor has
    at least two walking heights joined by stairs (galleries / mezzanines); enough far cells to spawn the floor's enemies."""
    terrain = pool_terrain(fm, 0.3)
    x0, x1, z0, z1, wy = fm.water
    nav = NavGrid(terrain, fm.nav_rect, 0.5, 0.34, 0.2, water=(x0, x1, z0, z1, wy))
    ax, az = fm.arrive_point
    start = nav.nearest_open(ax, az - 1.0 if fm.arrive_kind == 'cabin' else az + 1.0)
    seen, stack = {start}, [start]
    while stack:
        i = stack.pop()
        for j, _ in nav.links[i]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    open_cells = nav.open_cells()
    assert len(seen) >= 0.95 * len(open_cells), f'{len(seen)} / {len(open_cells)}'
    ex = fm.spec.exit
    door_cell = nav.nearest_open(ex.x, ex.z - 0.6)
    assert door_cell in seen and abs(nav.height[door_cell] - ex.y) < 0.05
    heights = {round(nav.height[i], 1) for i in seen if nav.height[i] >= -0.01}
    assert len([h for h in heights if h in (0.0, 1.2, 2.4)]) >= 2, heights
    far = [i for i in seen if nav.height[i] >= -0.01 and math.dist(nav.center(i), fm.arrive_point) > 9.0]
    assert len(far) > 6 * sum(fm.spec.enemies)


def test_pool_stage_is_the_pool_hall_with_a_door_up():
    fm = STAGES[0]
    pm = build_map(MapData())
    assert fm.index == 0 and fm.arrive_kind == 'start' and fm.exit_kind == 'corridor'
    names = {b.name for b in fm.boxes}
    assert {b.name for b in pm.boxes if b.name != 'wall_n'} <= names
    t = pool_terrain(fm, 0.3)
    eo = fm.exit_origin
    assert t.floor_at(eo[0], eo[2] + 0.5, eo[1] + 0.2) == pytest.approx(eo[1])              # the corridor floor continues the stair landing
    assert t.floor_at(eo[0], 14.0, 1.0) == pytest.approx(eo[1])                               # the landing of the north-bank stairs


def test_cabin_frames_and_tiles():
    for fm in FLOORS:
        for c in (fm.spec.arrive, fm.spec.exit):
            if c is not None:
                assert all(abs(v / 1.2 - round(v / 1.2)) < 1e-9 for v in (c.x, c.y, c.z))


def test_floor_keys_differ():
    look = LookData()
    assert len({br.floor_key(fm, look) for fm in STAGES}) == len(STAGES)


def test_doors_slide():
    lift = [d for d in FLOORS[0].doors if d.kind == 'exit']
    (lo0, hi0), (lo1, hi1) = br.door_box(lift[0], 0.0), br.door_box(lift[0], 1.0)
    assert lo1[0] == pytest.approx(lo0[0] - br.CAB_LEAF_TRAVEL) and lo1[1] == lo0[1]
    up = [d for d in STAGES[0].doors if d.kind == 'exit'][0]
    assert br.door_box(up, 1.0)[0][1] > up.lo[1] + br.DOOR_H - 0.2


def test_box_subtraction():
    pieces = br.subtract_box((0, 0, 0), (4, 4, 4), (1, 1, 1), (2, 2, 2))
    assert len(pieces) == 6
    vol = sum((h[0] - l[0]) * (h[1] - l[1]) * (h[2] - l[2]) for l, h in pieces)
    assert vol == pytest.approx(64 - 1)
    for i, (l1, h1) in enumerate(pieces):
        for l2, h2 in pieces[i + 1:]:
            assert not br.overlap(l1, h1, l2, h2)


def _walk(fm, x, z, y, vz, seconds=6.0, radius=0.3):
    """Walk straight along z with the player's collision (resolve_move + floor_at), doors open; returns (x, z, y)."""
    from fps.core.terrain import resolve_move
    t = pool_terrain(fm, radius)
    vx = 0.0
    for _ in range(int(seconds * 120)):
        x, z, vx, _vz = resolve_move(t, x, z, y, vx, vz, 1 / 120, radius, PlayerParams().step_up, 1.8)
        fy = t.floor_at(x, z, y + PlayerParams().step_up)
        y = y if fy is None else fy
    return x, z, y


def test_floor_one_corridor_can_be_walked_into_the_hall():
    """G19 bug: a 0.4 m slab of the carved solid plugged the top of the arrival corridor: the player stopped 0.3 m short of the open door."""
    fm = STAGES[1]
    ao = fm.arrive_origin
    hz = fm.data.room_z / 2
    x, z, y = _walk(fm, ao[0], ao[2] + 1.0, ao[1] + br.CLIMB, 4.5)
    assert z > -hz + 1.0, f'stopped at z={z:.2f} (the hall starts at {-hz:.2f})'
    assert abs(y) < 0.05


@pytest.mark.parametrize('k', range(2, len(BACKROOMS) + 1))
def test_lift_cabin_can_be_walked_out_into_the_room(k):
    fm = STAGES[k]
    c = fm.spec.arrive
    w = fm.data.wall
    x, z, y = _walk(fm, c.x, c.z + w + 1.2, c.y, -4.5)
    assert z < c.z - 1.0, f'floor {k}: stopped at z={z:.2f} (cabin door at {c.z:.2f})'


def test_pool_hall_stairs_lead_to_the_end_of_the_corridor():
    fm = STAGES[0]
    eo = fm.exit_origin
    z0 = eo[2] - 3.0
    y0 = pool_terrain(fm, 0.3).floor_at(eo[0], z0, 5.0)                  # on the north-bank stairs
    x, z, y = _walk(fm, eo[0], z0, y0, 4.5, seconds=4.0)
    assert z > eo[2] + br.LENGTH - 1.0, f'stopped at z={z:.2f}'
