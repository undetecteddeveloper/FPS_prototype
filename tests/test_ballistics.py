import math

import pytest

from fps.core.ballistics import (GROUND, advance, drop_at_distance, first_hit, hole_size, segment_vs_aabb,
                        segment_vs_ground)

V, G = 500.0, 9.81


def fly_to(distance, fps):
    """Flies to z = distance and returns the drop, stepping frame by frame as the game does."""
    pos, vel, dt = (0.0, 0.0, 0.0), (0.0, 0.0, V), 1.0 / fps
    while True:
        new_pos, new_vel = advance(pos, vel, G, dt)
        if new_pos[2] >= distance:
            f = (distance - pos[2]) / (new_pos[2] - pos[2])
            return -(pos[1] + (new_pos[1] - pos[1]) * f)
        pos, vel = new_pos, new_vel


def test_drop_matches_the_spec_numbers():
    assert drop_at_distance(75, V, G) == pytest.approx(0.11, abs=0.005)     # spec: ~0.1 m at 75 m
    assert drop_at_distance(150, V, G) == pytest.approx(0.4415, abs=0.001)  # spec: ~0.45 m at 150 m


@pytest.mark.parametrize('fps', [20, 30, 60, 144, 240])
@pytest.mark.parametrize('distance', [10, 50, 100, 150, 200])
def test_stepped_flight_equals_closed_form_at_any_fps(distance, fps):
    # Each frame the bullet follows an arc, but we measure on the chord (the straight segment joining two points): maximum error g*dt^2/8
    # = 3 mm at 20 FPS, 0.3 mm at 60 FPS. Apart from that error, the drop does not depend on FPS.
    chord_error = G * (1.0 / fps) ** 2 / 8
    assert fly_to(distance, fps) == pytest.approx(drop_at_distance(distance, V, G), abs=chord_error + 1e-9)


def test_advance_keeps_horizontal_speed_and_accelerates_down():
    pos, vel = advance((0, 0, 0), (0, 0, 500), 9.81, 0.1)
    assert vel == (0, pytest.approx(-0.981), 500)
    assert pos[2] == pytest.approx(50)


BOX = ((-1, 0, 99.96), (1, 2, 100.04))   # target plate 8 cm thick


def test_segment_hits_the_front_face_with_outward_normal():
    t, normal = segment_vs_aabb((0, 1, 0), (0, 1, 200), *BOX)
    assert t * 200 == pytest.approx(99.96)
    assert normal == (0.0, 0.0, -1.0)


def test_fast_step_does_not_tunnel_through_a_thin_target():
    # 8 m per frame (500 m/s, 60 FPS), 25 m (20 FPS) and 100 m must all hit the 8 cm plate
    for step in (8.3, 25.0, 100.0):
        z = 100.0 - step / 2
        assert segment_vs_aabb((0, 1, z), (0, 1, z + step), *BOX) is not None


def test_miss_cases():
    assert segment_vs_aabb((5, 1, 0), (5, 1, 200), *BOX) is None        # off to the side
    assert segment_vs_aabb((0, 5, 0), (0, 5, 200), *BOX) is None        # flies over the top
    assert segment_vs_aabb((0, 1, 0), (0, 1, 50), *BOX) is None         # not reached yet
    assert segment_vs_aabb((0, 1, 120), (0, 1, 200), *BOX) is None      # already passed
    assert segment_vs_aabb((0, 1, 200), (0, 1, 0), *BOX) is not None    # from behind, it hits the back face


def test_start_inside_box_is_not_a_new_hit():
    assert segment_vs_aabb((0, 1, 100), (0, 1, 150), *BOX) is None


def test_side_and_top_normals():
    box = ((10, 0, 0), (13, 1.2, 100))
    assert segment_vs_aabb((0, 0.5, 50), (20, 0.5, 50), *box)[1] == (-1.0, 0.0, 0.0)
    assert segment_vs_aabb((11, 5, 50), (11, -5, 50), *box)[1] == (0.0, 1.0, 0.0)


def test_ground_hit():
    assert segment_vs_ground((0, 1, 0), (0, -1, 10)) == pytest.approx(0.5)
    assert segment_vs_ground((0, 1, 0), (0, 0.5, 10)) is None
    assert segment_vs_ground((0, -1, 0), (0, -2, 10)) is None          # already below the ground


def test_first_hit_picks_the_nearest_and_reports_owner():
    near = ((-1, 0, 49.9), (1, 2, 50.1), 'gần')
    far = ((-1, 0, 99.9), (1, 2, 100.1), 'xa')
    h = first_hit((0, 1, 0), (0, 1, 200), [far, near])
    assert h.owner == 'gần' and h.point[2] == pytest.approx(49.9)


def test_first_hit_ground_before_target():
    box = ((-1, 0, 14.9), (1, 2, 15.1), 'bia')
    h = first_hit((0, 1, 0), (0, -1, 20), [box])        # hits the ground at z = 10, before reaching the target at z = 15
    assert h.owner is GROUND
    assert h.point[1] == pytest.approx(0.0) and h.point[2] == pytest.approx(10.0)
    assert h.normal == (0.0, 1.0, 0.0)


def test_first_hit_none_when_clear():
    assert first_hit((0, 5, 0), (0, 5, 200), [((-1, 0, 99), (1, 2, 101), 'bia')]) is None


def test_hole_grows_with_distance():
    assert hole_size(0, 0.05, 0.002) == pytest.approx(0.05)
    assert hole_size(150, 0.05, 0.002) == pytest.approx(0.35)
    assert math.isfinite(hole_size(1000, 0.05, 0.002))


def test_decal_rotation_covers_all_axis_normals():
    from fps.core.ballistics import decal_rotation
    assert decal_rotation((0, 0, -1)) == (0, 0, 0)          # target face turned toward the shooter
    assert decal_rotation((0, 0, 1)) == (0, 180, 0)
    assert decal_rotation((-1, 0, 0)) == (0, 90, 0)
    assert decal_rotation((1, 0, 0)) == (0, -90, 0)
    assert decal_rotation((0, 1, 0)) == (90, 0, 0)          # ground
    assert decal_rotation((0, -1, 0)) == (-90, 0, 0)
