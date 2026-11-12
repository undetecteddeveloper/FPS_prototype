"""G18 flow field: blocked cells, cliffs, the time-sliced Dijkstra gives the same field as a full one, directions lead to the goal."""
import math

from fps.core.flowfield import FlowField, NavGrid
from fps.core.poolmap import build_map, pool_terrain
from fps.core.terrain import Terrain
from fps.weapon_data import MapData


def _room(solids=(), tops_extra=()):
    tops = [(-10.0, 10.0, -10.0, 10.0, 0.0)] + list(tops_extra)
    return Terrain(tops, list(solids), (-9.7, 9.7, -9.7, 9.7))


def test_pillar_blocks_cells_with_clearance():
    t = _room(solids=[((-1.0, 0.0, -1.0), (1.0, 3.0, 1.0))])
    nav = NavGrid(t, (-10, 10, -10, 10), 0.5, 0.35, 0.2)
    assert not nav.open(nav.index(0.0, 0.0))
    assert not nav.open(nav.index(1.2, 0.1))                 # within the body radius of the pillar face
    assert nav.open(nav.index(1.6, 0.1))


def test_cliff_is_not_linked_but_steps_are():
    # a 0.6 m ledge on the east half, with a strip of 0.15 m steps up to it in the middle
    t = _room(tops_extra=[(1.5, 10.0, -10.0, 10.0, 0.6), (1.0, 1.5, -1.0, 1.0, 0.45), (0.5, 1.0, -1.0, 1.0, 0.3), (0.0, 0.5, -1.0, 1.0, 0.15)])
    nav = NavGrid(t, (-10, 10, -10, 10), 0.5, 0.3, 0.2)
    f = FlowField(nav)
    goal = nav.index(-5.0, 5.0)
    f.solve(goal)
    up = nav.index(6.0, 5.0)
    assert f.cost(up) < math.inf                             # reachable, through the steps
    # the path from the ledge goes through the step strip (|z| < 1)
    i, z_on_strip = up, False
    for _ in range(200):
        if i == goal:
            break
        dx, dz = f.direction(i)
        cx, cz = nav.center(i)
        j = nav.index(cx + dx * nav.cell, cz + dz * nav.cell)
        if abs(nav.height[i] - nav.height[j]) > 0.01:
            z_on_strip = z_on_strip or abs(cz) < 1.0
        i = j
    assert i == goal and z_on_strip


def test_time_sliced_equals_full():
    pm = build_map(MapData())
    t = pool_terrain(pm, 0.3)
    x0, x1, z0, z1, wy = pm.water
    nav = NavGrid(t, (-10, 10, -15, 15), 0.5, 0.34, 0.2, water=(x0, x1, z0, z1, wy))
    full, sliced = FlowField(nav), FlowField(nav)
    goal = nav.nearest_open(0.0, -12.0)
    full.solve(goal)
    sliced.request(goal)
    frames = 0
    while not sliced.step(100):
        frames += 1
    assert frames > 3 and sliced.dist == full.dist


def test_deep_water_costs_more():
    pm = build_map(MapData())
    t = pool_terrain(pm, 0.3)
    x0, x1, z0, z1, wy = pm.water
    nav = NavGrid(t, (-10, 10, -15, 15), 0.5, 0.34, 0.2, water=(x0, x1, z0, z1, wy), deep_cost=6.0)
    assert nav.cost[nav.index(0.0, 10.0)] > 5.0              # 2 m deep end
    assert nav.cost[nav.index(0.0, -12.5)] == 1.0             # dry deck


def test_new_goal_restarts_job():
    nav = NavGrid(_room(), (-10, 10, -10, 10), 0.5, 0.3, 0.2)
    f = FlowField(nav)
    a, b = nav.index(-5, -5), nav.index(5, 5)
    f.request(a)
    f.step(10)
    f.request(b)                                              # remembered: the job toward a finishes first, then b
    while f.busy:
        f.step(50)
    assert f.goal == b and f.dist[b] == 0.0 and f.completed == 2
    f.request(b)
    assert not f.busy                                         # same goal: no new job
