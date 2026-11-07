import math

import pytest

from fps.core.poolmap import build_map, pool_terrain
from fps.core.terrain import push_out_of_box, resolve_move
from fps.weapon_data import MapData

D = MapData()
R, STEP, H = 0.3, 0.2, 1.7
WADE_Y = D.water_y - D.wade_depth                  # the lowest the feet go in the pool (chest-deep water)


def ramp(z):
    z0, z1 = D.slope_z
    return D.pool_floor + (D.pool_deep - D.pool_floor) * (z - z0) / (z1 - z0)


@pytest.fixture(scope='module')
def terrain():
    return pool_terrain(build_map(D), R)


def walk(t, x, z, y, vx, vz, seconds=1.0, dt=1 / 60):
    for _ in range(round(seconds / dt)):
        x, z, vx, vz = resolve_move(t, x, z, y, vx, vz, dt, R, STEP, H)
    return x, z


def test_deck_pool_and_step_heights(terrain):
    pz = D.pool_z / 2
    rise = -D.pool_floor / (D.steps + 1)
    assert terrain.floor_at(0, -13.5, 0.2) == 0.0                                   # the spawn bank
    assert terrain.floor_at(0, -8, 0.2) == pytest.approx(D.pool_floor)              # the shallow end
    assert terrain.floor_at(0, 0, 0.2) == pytest.approx(ramp(0.0))                  # on the slope toward the deep end
    assert terrain.floor_at(0, -pz + 0.1, 0.2) == pytest.approx(-rise)             # first step down
    assert terrain.floor_at(0, -pz + 0.1 + D.step_depth, 0.2) == pytest.approx(-2 * rise)
    assert terrain.floor_at(D.stair_x[0] + 1, D.pool_z / 2 + 0.2, 0.2) == 0.0       # in front of the stairs
    assert terrain.floor_at(D.stair_x[0] + 1, D.pool_z / 2 + 0.4 + D.stair_tread * 1.5, D.stair_rise + 0.2) == pytest.approx(2 * D.stair_rise)


def test_floor_below_the_feet_is_found_even_far_down(terrain):
    assert terrain.floor_at(0, -8, 5.0) == pytest.approx(D.pool_floor)
    assert terrain.floor_at(0, 0, 5.0) == pytest.approx(ramp(0.0))


def test_the_pool_is_two_metres_deep_at_the_north_end():
    assert D.water_y - D.pool_deep == pytest.approx(2.0)
    assert D.water_y - D.pool_floor == pytest.approx(0.5)
    assert not any(b.name.startswith('step_n') for b in build_map(D).boxes)          # no steps into 2 m of water: the handrails are a ladder


def test_walking_toward_the_deep_end_stops_where_the_water_is_chest_deep(terrain):
    x, z = walk(terrain, 0.0, -8.0, D.pool_floor, 0.0, 4.5, seconds=4.0)          # wading north along the slope (the feet follow the floor; y is not used for the depth test)
    z_line = D.slope_z[0] + (D.slope_z[1] - D.slope_z[0]) * (D.pool_floor - WADE_Y) / (D.pool_floor - D.pool_deep)
    assert z_line - 0.1 < z <= z_line + 1e-6
    assert D.water_y - ramp(z) <= D.wade_depth + 1e-6


def test_dropping_into_the_deep_end_stands_at_chest_depth_and_can_wade_back(terrain):
    assert terrain.floor_at(0, 10, 0.2) == pytest.approx(WADE_Y)                    # not 2 m down: standing (treading) at chest depth
    x, z = walk(terrain, 0.0, 10.0, WADE_Y, 0.0, -4.5, seconds=3.0)               # someone who jumped in may walk back to the shallows
    assert z < 0.0


def test_a_ledge_higher_than_a_step_blocks_from_the_pool_floor_but_not_when_high_enough(terrain):
    pz = D.pool_z / 2
    assert terrain.blocked_by_ledge(0, -pz - 0.1, D.pool_floor, STEP)            # the pool edge seen from the bottom
    assert not terrain.blocked_by_ledge(0, -pz - 0.1, -0.15, STEP)               # mid-jump, high enough to get over
    assert not terrain.blocked_by_ledge(0, -pz + 0.2, 0.0, STEP)                 # walking down into the pool is never blocked


def test_walking_into_the_pool_wall_from_the_bottom_stops_at_the_wall(terrain):
    px = D.pool_x / 2
    x, z = walk(terrain, -4.0, -8.0, D.pool_floor, -4.5, 0.0, seconds=2.0)         # on the shallow floor, walking west into the 0.62 m wall
    assert -px <= x <= -px + 0.1
    x, z = walk(terrain, -4.0, -8.0, D.pool_floor, -4.5, 4.5, seconds=1.0)         # diagonally: stopped in x but keeps sliding north along the wall
    assert -px <= x <= -px + 0.1 and z > -5.0


def test_climbing_the_south_steps_is_possible(terrain):
    pz = D.pool_z / 2
    # from the pool floor at the steps, walking south, each step is a rise of 0.155 <= 0.2
    y = D.pool_floor
    x, z = 0.0, -pz + D.step_depth * D.steps + 0.2
    for _ in range(40):
        x, z = walk(terrain, x, z, y, 0, -4.5, seconds=0.05)
        g = terrain.floor_at(x, z, y + STEP)
        y = max(y, g)
    assert y == 0.0 and z < -pz + 0.05


def test_a_column_pushes_the_player_out_and_he_slides_along_it(terrain):
    cx, cz, s = D.column_x, D.column_z[0], D.column_size / 2
    x, z = walk(terrain, cx + s + 2.0, cz, 0.0, -4.5, 0.0, seconds=1.0)
    assert x == pytest.approx(cx + s + R, abs=1e-3)
    x, z = walk(terrain, cx + s + 2.0, cz - 0.3, 0.0, -3.0, 3.0, seconds=0.6)       # diagonal into the column: slides north along its east face (and around the corner)
    gap = math.hypot(x - min(max(x, cx - s), cx + s), z - min(max(z, cz - s), cz + s))
    assert gap >= R - 1e-3 and z > cz - 0.3                                          # never inside the column, and it did move along


def test_walls_hold_the_player_in_even_at_full_sprint(terrain):
    hx, hz = D.room_x / 2, D.room_z / 2
    x, z = walk(terrain, 5, 0, 0.0, 9.0, 0.0, seconds=3.0)
    assert x <= hx - R + 1e-6
    x, z = walk(terrain, -9.5, 13, 0.0, -9.0, 9.0, seconds=2.0)
    assert x >= -hx + R - 1e-6 and z <= hz - R + 1e-6


def test_window_barrier_stops_a_player_who_jumped_into_the_opening(terrain):
    hx = D.room_x / 2
    x, z = walk(terrain, hx - 1.0, D.window_z[1], 1.0, 9.0, 0.0, seconds=1.0)         # standing at 1 m height, i.e. inside the window's height band
    assert x <= hx - R + 1e-6


def test_push_out_of_box_cases():
    lo, hi = (0, 0, 0), (2, 2, 2)
    assert push_out_of_box(5, 1, 0.3, lo, hi)[2:] == (0.0, 0.0)                    # far away: untouched
    x, z, nx, nz = push_out_of_box(2.1, 1, 0.3, lo, hi)                             # touching the east face
    assert (x, z) == pytest.approx((2.3, 1.0)) and (nx, nz) == pytest.approx((1.0, 0.0))
    x, z, nx, nz = push_out_of_box(2.1, 2.1, 0.3, lo, hi)                           # the corner: pushed along the diagonal
    assert math.hypot(x - 2, z - 2) == pytest.approx(0.3)
    x, z, nx, nz = push_out_of_box(1.8, 1, 0.3, lo, hi)                             # centre inside the footprint: leaves through the nearest side
    assert x == pytest.approx(2.3) and (nx, nz) == (1.0, 0.0)
