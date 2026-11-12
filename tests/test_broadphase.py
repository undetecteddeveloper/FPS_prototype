"""G18 broadphase: the grid queries give exactly what a full scan of the boxes gives (terrain, bullets, the High Ready probe)."""
import random

from fps.core.ballistics import first_hit
from fps.core.broadphase import BoxIndex, Grid2D
from fps.core.poolmap import build_map, colliders
from fps.core.terrain import Terrain, resolve_move
from fps.core.weaponcol import probe_distance
from fps.weapon_data import MapData


def _random_boxes(rnd, n):
    out = []
    for i in range(n):
        x, z, y = rnd.uniform(-20, 20), rnd.uniform(-20, 20), rnd.uniform(-1, 2)
        sx, sz, sy = rnd.uniform(0.1, 6), rnd.uniform(0.1, 6), rnd.uniform(0.1, 3)
        out.append(((x, y, z), (x + sx, y + sy, z + sz), i))
    return out


def test_grid_cells_are_supersets():
    rnd = random.Random(3)
    boxes = _random_boxes(rnd, 80)
    g = Grid2D([(lo[0], hi[0], lo[2], hi[2]) for lo, hi, _ in boxes])
    for _ in range(2000):
        x, z = rnd.uniform(-25, 30), rnd.uniform(-25, 30)
        cand = set(g.at(x, z))
        for i, (lo, hi, _) in enumerate(boxes):
            if lo[0] <= x <= hi[0] and lo[2] <= z <= hi[2]:
                assert i in cand
        assert list(g.at(x, z)) == sorted(g.at(x, z))


def test_bullet_segments_match_full_scan():
    rnd = random.Random(5)
    boxes = _random_boxes(rnd, 120)
    index = BoxIndex(boxes)
    for _ in range(3000):
        p0 = (rnd.uniform(-25, 25), rnd.uniform(-1, 3), rnd.uniform(-25, 25))
        length = rnd.choice((0.3, 3.0, 8.0, 60.0))
        d = (rnd.uniform(-1, 1), rnd.uniform(-0.3, 0.3), rnd.uniform(-1, 1))
        p1 = tuple(p0[i] + d[i] * length for i in range(3))
        full = first_hit(p0, p1, boxes, ground_y=None)
        fast = first_hit(p0, p1, index.segment(p0, p1), ground_y=None)
        assert (full is None) == (fast is None)
        if full:
            assert full.owner == fast.owner and abs(full.t - fast.t) < 1e-12


def test_pool_terrain_moves_match_full_scan():
    """resolve_move / floor_at with the grid against a Terrain whose grid holds every box in one cell (= the old full scan)."""
    from fps.core.poolmap import pool_terrain
    pm = build_map(MapData())
    fast = pool_terrain(pm, 0.3)
    slow = Terrain(fast.tops, fast.solids, fast.bounds, fast.ramps)
    slow._top_grid = Grid2D([t[:4] for t in fast.tops], cell=1e4)
    slow._solid_grid = Grid2D([(lo[0], hi[0], lo[2], hi[2]) for lo, hi in fast.solids], cell=1e4)
    rnd = random.Random(9)
    for _ in range(3000):
        x, z = rnd.uniform(-10, 10), rnd.uniform(-15, 15)
        q = rnd.choice((0.0, -0.12, -0.62, -2.12, 0.34))
        assert fast.floor_at(x, z, q + 0.35) == slow.floor_at(x, z, q + 0.35)
        y = slow.highest_top(x, z)                       # a legal start: standing on the surface there (not buried metres inside a slab)
        if y is None:
            continue
        vx, vz = rnd.uniform(-6, 6), rnd.uniform(-6, 6)
        a = resolve_move(fast, x, z, y, vx, vz, 1 / 60, 0.3, 0.35, 1.75)
        b = resolve_move(slow, x, z, y, vx, vz, 1 / 60, 0.3, 0.35, 1.75)
        assert a == b


def test_wall_probe_with_index_matches_list():
    boxes = colliders(build_map(MapData()))
    index = BoxIndex(boxes)
    rnd = random.Random(11)
    for _ in range(500):
        o = (rnd.uniform(-9.5, 9.5), rnd.uniform(0.5, 1.8), rnd.uniform(-14.5, 14.5))
        yaw, pitch = rnd.uniform(0, 360), rnd.uniform(-60, 60)
        assert probe_distance(o, yaw, pitch, index, 1.2) == probe_distance(o, yaw, pitch, boxes, 1.2)
