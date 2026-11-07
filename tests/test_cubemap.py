import math
import random

import pytest

from fps.core.cubemap import (COLS, FACE_AXES, ROWS, TAN_HALF, atlas_uv, basis, box_project, direction_of, face_uv, pick_face, region)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_bases_are_orthonormal_and_right_handed_in_ursinas_world():
    for f in range(6):
        r, u, fw = basis(f)
        assert dot(r, u) == 0 and dot(r, fw) == 0 and dot(u, fw) == 0
        assert dot(r, r) == dot(u, u) == dot(fw, fw) == 1
    r, u, fw = basis(4)                                                                # looking +z: right = +x, up = +y (the default Ursina camera)
    assert r == (1, 0, 0) and u == (0, 1, 0) and fw == (0, 0, 1)
    r, u, fw = basis(0)                                                                # looking +x: right = -z (a quarter turn to the right)
    assert r == (0, 0, -1)


def test_the_six_forwards_are_the_six_axes():
    assert sorted(f for f, _ in FACE_AXES) == sorted([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)])


def test_face_centres_map_to_the_middle_of_their_cell():
    for f in range(6):
        forward = FACE_AXES[f][0]
        face, u, v = face_uv(forward)
        assert face == f and u == pytest.approx(0.5) and v == pytest.approx(0.5)
        U, V = atlas_uv(forward)
        assert U == pytest.approx(((f % COLS) + 0.5) / COLS) and V == pytest.approx(((f // COLS) + 0.5) / ROWS)


@pytest.mark.parametrize('seed', range(5))
def test_direction_round_trip_over_random_directions(seed):
    rng = random.Random(seed)
    for _ in range(200):
        d = [rng.gauss(0, 1) for _ in range(3)]
        n = math.sqrt(dot(d, d))
        d = tuple(c / n for c in d)
        f, u, v = face_uv(d)
        assert f == pick_face(d) and 0.0 < u < 1.0 and 0.0 < v < 1.0
        back = direction_of(f, u, v)
        assert dot(back, d) == pytest.approx(1.0, abs=1e-9)


def test_lookups_stay_inside_the_face_with_a_guard_band():
    """The face is rendered wider than 90 degrees, so even a direction on the seam lands >= 1.5% away from the edge of its cell (no bleeding into the neighbour)."""
    seam = (1.0, 1.0, 0.2)
    n = math.sqrt(dot(seam, seam))
    f, u, v = face_uv(tuple(c / n for c in seam))
    assert 0.015 < min(u, 1 - u, v, 1 - v) and TAN_HALF > 1.0


def test_a_sunlit_window_direction_lands_in_the_east_face():
    f, u, v = face_uv((0.95, 0.2, -0.2))
    assert f == 0                                                                      # the +x face: toward the windows
    assert u > 0.5                                                                     # the east-looking camera has -z on its right, and the sun direction leans toward -z
    assert v > 0.5                                                                     # above the horizon


def test_regions_tile_the_atlas_without_gaps():
    cells = [region(f) for f in range(6)]
    assert sorted(set(c[0] for c in cells)) == pytest.approx([0, 1 / 3, 2 / 3])
    assert sorted(set(c[2] for c in cells)) == pytest.approx([0, 0.5])
    assert sum((c[1] - c[0]) * (c[3] - c[2]) for c in cells) == pytest.approx(1.0)


def test_box_projection_finds_the_wall_and_corrects_the_parallax():
    lo, hi = (-10, -1, -15), (10, 4, 15)
    probe = (0.0, 1.3, 0.0)
    # a point right under the east wall looking horizontally east hits that wall straight ahead: the lookup direction is from the probe to the wall point, not along the ray
    d = box_project((9.0, 0.0, 6.0), (1.0, 0.0, 0.0), lo, hi, probe)
    assert d == pytest.approx((10.0, -1.3, 6.0))
    # the same ray from the probe's own position gives the plain direction (no parallax to correct)
    d0 = box_project(probe, (0.0, 0.0, 1.0), lo, hi, probe)
    assert d0 == pytest.approx((0.0, 0.0, 15.0))
    # a ray going straight up from anywhere hits the ceiling at the same x, z
    d1 = box_project((4.0, 0.0, -3.0), (0.0, 1.0, 0.0), lo, hi, probe)
    assert d1 == pytest.approx((4.0, 4.0 - 1.3, -3.0))
