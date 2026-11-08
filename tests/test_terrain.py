import math

import pytest

from fps.core.poolmap import build_map, pool_terrain
from fps.core.terrain import push_out_of_box, resolve_move
from fps.weapon_data import MapData

D = MapData()
R, STEP, H = 0.3, 0.2, 1.7


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


def test_walking_down_the_slope_reaches_the_two_metre_bottom(terrain):
    """G12: no rope line at chest depth any more: he walks the whole slope and stands on the deep floor, head under the water."""
    x, z = walk(terrain, 0.0, -8.0, D.pool_floor, 0.0, 4.5, seconds=6.0)          # wading north along the slope (the feet follow the floor; y is not used for the depth test)
    assert z > D.slope_z[1] + 1.0
    assert terrain.floor_at(x, z, D.pool_floor) == pytest.approx(D.pool_deep)
    assert D.water_y - D.pool_deep == pytest.approx(2.0)
    eye = D.pool_deep + 1.68
    assert eye < D.water_y - 0.3                                                   # standing there, the eye is well under the surface


def test_dropping_into_the_deep_end_lands_on_the_bottom_and_can_walk_back(terrain):
    assert terrain.floor_at(0, 10, 0.2) == pytest.approx(D.pool_deep)               # jumping in from the deck: down to the 2 m floor
    x, z, y = 0.0, 10.0, D.pool_deep
    for _ in range(80):                                                            # walking back up the slope to the shallows, the feet following the floor
        x, z = walk(terrain, x, z, y, 0.0, -4.5, seconds=0.05)
        y = terrain.floor_at(x, z, y + STEP)
    assert z < 0.0 and y > D.pool_deep + 0.5


def test_a_ledge_higher_than_a_step_blocks_from_the_pool_floor_but_not_when_high_enough(terrain):
    pz = D.pool_z / 2
    assert terrain.blocked_by_ledge(0, -pz - 0.1, D.pool_floor, STEP)            # the pool edge seen from the bottom
    assert not terrain.blocked_by_ledge(0, -pz - 0.1, -0.15, STEP)               # mid-jump, high enough to get over
    assert not terrain.blocked_by_ledge(0, -pz + 0.2, 0.0, STEP)                 # walking down into the pool is never blocked


def test_walking_into_the_pool_wall_from_the_bottom_stops_at_the_wall(terrain):
    px = D.pool_x / 2
    x, z = walk(terrain, -4.0, -8.0, D.pool_floor, -4.5, 0.0, seconds=2.0)         # on the shallow floor, walking west into the 0.62 m wall
    assert -px + R - 1e-3 <= x <= -px + R + 0.05                                  # G14: the BODY stops at the wall (radius away), not the centre point
    x, z = walk(terrain, -4.0, -8.0, D.pool_floor, -4.5, 4.5, seconds=1.0)         # diagonally: stopped in x but keeps sliding north along the wall
    assert -px + R - 1e-3 <= x <= -px + R + 0.05 and z > -5.0


@pytest.mark.parametrize('name, start, vel, axis, sign', [
    ('west', (-3.0, 8.0), (-1.7, 0.0), 0, -1), ('east', (3.0, 8.0), (1.7, 0.0), 0, 1), ('north', (0.0, 8.0), (0.0, 1.7), 1, 1),
])
def test_the_body_never_gets_closer_than_its_radius_to_the_deep_walls(terrain, name, start, vel, axis, sign):
    """G14: pressing into the wall of the deep end (the eye sat exactly ON the wall plane and the camera saw through it): he stops one radius away, at every speed."""
    wall = (D.pool_x / 2 if axis == 0 else D.pool_z / 2) * sign
    for speed in (1.0, 2.0, 4.5, 9.0):
        x, z = walk(terrain, start[0], start[1], D.pool_deep, vel[0] * speed / 1.7, vel[1] * speed / 1.7, seconds=6.0)
        c = (x, z)[axis]
        assert abs(wall - c) >= R - 1e-3, (name, speed, c)
        assert abs(wall - c) <= R + 0.05, (name, speed, c)


def test_pressing_into_a_wall_corner_keeps_the_body_inside_the_circle_of_both_walls(terrain):
    x, z = walk(terrain, 3.0, 8.0, D.pool_deep, 3.0, 3.0, seconds=6.0)
    assert D.pool_x / 2 - x >= R - 1e-3 and D.pool_z / 2 - z >= R - 1e-3


def test_a_player_who_landed_overlapping_the_edge_is_pushed_out_not_stuck(terrain):
    """Dropping from the deck near the rim can leave the circle over the ledge: he must be able to walk away (and is eased out), never frozen."""
    x, z = walk(terrain, D.pool_x / 2 - 0.1, 8.0, D.pool_deep, -1.7, 0.0, seconds=1.0)
    assert D.pool_x / 2 - x >= R - 1e-3 and x < D.pool_x / 2 - 0.5                 # walked away from the wall
    x, z = walk(terrain, D.pool_x / 2 - 0.1, 8.0, D.pool_deep, 0.0, 0.0, seconds=0.3)
    assert D.pool_x / 2 - x >= R - 1e-3                                              # standing still: pushed out to one radius


def test_jumping_out_of_the_pool_over_the_edge_still_works(terrain):
    """The ledge only blocks while the feet are below it: at the height of a jump he clears the rim (G12 test in pool_check does the same with the real game)."""
    y = -0.10                                                                        # feet within step height of the deck top (0.0)
    x, z = walk(terrain, D.pool_x / 2 - R - 0.02, 8.0, y, 4.5, 0.0, seconds=0.5)
    assert x > D.pool_x / 2 + 0.2


def test_the_stairs_landing_is_a_wall_for_the_body_when_walked_into_from_the_side(terrain):
    """The landing (0.68 m up) cannot be stepped onto from the deck beside the flight: the circle stays outside it like a column."""
    x0, x1 = D.stair_x
    x, z = walk(terrain, x0 - 2.0, D.room_z / 2 - 0.9, 0.0, 2.0, 0.0, seconds=4.0)
    assert x0 - R - 0.05 <= x <= x0 - R + 1e-3


def test_the_north_stairs_can_still_be_climbed_from_the_front(terrain):
    """G14: the body circle pushes out of ledges higher than a step, never out of the next step of a flight (rise 0.17 <= 0.20)."""
    x, z, y = (D.stair_x[0] + D.stair_x[1]) / 2, D.pool_z / 2 + 0.15, 0.0
    for _ in range(80):
        x, z = walk(terrain, x, z, y, 0.0, 2.0, seconds=0.05)
        y = max(y, terrain.floor_at(x, z, y + STEP) or y)
    assert y == pytest.approx(D.stair_count * D.stair_rise)
