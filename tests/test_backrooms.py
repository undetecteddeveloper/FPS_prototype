"""G18 Backrooms floors: geometry sanity, the two stair corridors are the same shape, the floor swap offset, doors, lights, the bake key."""
import pytest

from fps.core import backrooms as br
from fps.core.flowfield import NavGrid
from fps.core.poolmap import UV_AXES, build_map, is_air, pool_terrain
from fps.weapon_data import BACKROOMS, LookData, MapData, PlayerParams

FLOORS = [br.build_floor(k) for k in range(len(BACKROOMS))]


def _corridor_boxes(fm, origin, tag):
    """Boxes of a corridor in its own frame, without the end walls (those differ by design: one end is the hall wall)."""
    out = []
    for b in fm.boxes:
        if b.name.startswith(tag + '_') and '_end_' not in b.name:
            out.append((b.name[len(tag) + 1:], tuple(round(b.lo[i] - origin[i], 6) for i in range(3)), tuple(round(b.hi[i] - origin[i], 6) for i in range(3)),
                        b.emit, b.walk, b.solid))
    return sorted(out)


@pytest.mark.parametrize('k', range(len(BACKROOMS) - 1))
def test_exit_and_next_arrival_corridors_match(k):
    """The exit corridor of floor k and the arrival corridor of floor k + 1 are the same boxes in their own frames (except the base / top landing reaching into
    the end wall that the corridor owns), and the swap offset maps one frame onto the other."""
    a, b = FLOORS[k], FLOORS[k + 1]
    ca = {n: (lo, hi) for n, lo, hi, *_ in _corridor_boxes(a, a.exit_origin, 'up')}
    cb = {n: (lo, hi) for n, lo, hi, *_ in _corridor_boxes(b, b.arrive_origin, 'down')}
    assert set(ca) == set(cb)
    for n in ca:
        if n == 'base' or n.startswith('stair'):
            assert ca[n][0][0] == cb[n][0][0] and ca[n][1][:2] == cb[n][1][:2]          # same width and height; length differs by the wall it reaches into
        else:
            assert ca[n] == cb[n], n
    t = br.transfer(k)
    for i in range(3):
        assert a.exit_origin[i] + t[i] == pytest.approx(b.arrive_origin[i])


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_floor_is_sane(fm):
    d = fm.data
    hx, hz = d.room_x / 2, d.room_z / 2
    px, pz = d.pool_x / 2, d.pool_z / 2
    assert hz - pz >= 3.0                                         # a deck in front of both doors
    assert -pz + d.steps * d.step_depth < d.slope_z[0] < d.slope_z[1] < pz
    for x, z, s in fm.spec.pillars:                               # pillars on the deck, inside the hall
        assert abs(x) + s / 2 < hx and abs(z) + s / 2 < hz
        assert abs(x) - s / 2 > px or abs(z) - s / 2 > pz
    for x, z, sx, sz in fm.spec.lights:
        assert abs(x) + sx / 2 < hx and abs(z) + sz / 2 < hz
    for door_x in (fm.spec.exit_x, fm.spec.arrive_x):
        assert abs(door_x) + br.C_WIDTH / 2 + d.wall < hx + d.wall
    assert len(br.emitters(fm)) == len(fm.spec.lights) + 2 * len(br.CORRIDOR_LIGHTS)
    assert sorted(dr.kind for dr in fm.doors) == ['arrive', 'dead', 'dead', 'exit']
    assert br.RISE <= PlayerParams().step_up
    assert abs(br.CLIMB / 1.2 - round(br.CLIMB / 1.2)) < 1e-9     # the climb is whole tile periods (the corridor copies line up)
    # the door holes are air, the leaves fill them
    for dr in fm.doors:
        mid = tuple((dr.lo[i] + dr.hi[i]) / 2 for i in range(3))
        assert is_air(fm, mid)


@pytest.mark.parametrize('fm', FLOORS, ids=[f.spec.name for f in FLOORS])
def test_whole_floor_reachable_from_the_arrival_door(fm):
    """Every open nav cell of the hall can be reached from the arrival door (no sealed pocket where an enemy could never be killed), and enough cells exist far from it to spawn the floor's enemies."""
    terrain = pool_terrain(fm, 0.3)
    x0, x1, z0, z1, wy = fm.water
    nav = NavGrid(terrain, fm.nav_rect, 0.5, 0.34, 0.2, water=(x0, x1, z0, z1, wy))
    start = nav.nearest_open(fm.spec.arrive_x, -fm.data.room_z / 2 + 1.0)
    seen, stack = {start}, [start]
    while stack:
        i = stack.pop()
        for j, _ in nav.links[i]:
            if j not in seen:
                seen.add(j)
                stack.append(j)
    open_cells = nav.open_cells()
    assert len(seen) >= 0.97 * len(open_cells)                  # a few cells boxed in by pillars at most
    far = [i for i in seen if nav.height[i] >= -0.01 and nav.center(i)[1] > -fm.data.room_z / 2 + 8.0]
    assert len(far) > 6 * sum(fm.spec.enemies)


def test_corridor_tiles_use_the_corridor_frame():
    fm = FLOORS[0]
    stairs = [b for b in fm.boxes if b.name.startswith('up_stair')]
    assert stairs and all(b.uv_origin == fm.exit_origin for b in stairs)
    hall = [b for b in fm.boxes if b.name.startswith('pillar')]
    assert all(b.uv_origin == (0.0, 0.0, 0.0) for b in hall)


def test_pool_hall_unchanged():
    """The default pool hall has no lights, no corridors and the same bounds as before G18 (its stored bake stays valid)."""
    pm = build_map(MapData())
    assert pm.bounds is None and not br.emitters(pm)
    t = pool_terrain(pm, 0.3)
    assert t.bounds == (-10 + 0.3, 10 - 0.3, -15 + 0.3, 15 - 0.3)


def test_floor_key_changes_with_the_floor():
    look = LookData()
    keys = {br.floor_key(fm, look) for fm in FLOORS}
    assert len(keys) == len(FLOORS)


def test_door_slides_up():
    dr = FLOORS[0].doors[0]
    lo0, hi0 = br.door_box(dr, 0.0)
    lo1, hi1 = br.door_box(dr, 1.0)
    assert lo0 == dr.lo and lo1[1] > dr.lo[1] + br.DOOR_H - 0.2
    assert UV_AXES  # (import kept: faces use it)
