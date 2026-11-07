import math
import random

import pytest

from fps.core.ballistics import first_hit
from fps.core.graphics import clamp_level, level, next_level, water_flags
from fps.core.poolmap import basin_boxes, build_map, colliders, sun_visible, window_rects
from fps.weapon_data import GRAPHICS_LEVELS, GraphicsData, LookData, MapData


def test_f2_cycles_low_mid_high_and_back():
    seen = [0]
    for _ in range(len(GRAPHICS_LEVELS)):
        seen.append(next_level(seen[-1]))
    assert seen == [0, 1, 2, 0]
    assert clamp_level(9) == 2 and clamp_level(-3) == 0


def test_low_is_the_g9_look_and_high_is_at_least_mid():
    low, mid, high = GRAPHICS_LEVELS
    assert water_flags(low) == (0.0, 0.0, 0.0, 0.0) and low.shaft_steps == 0
    assert all(h >= m for h, m in zip(water_flags(high), water_flags(mid)))
    assert high.sim_cols * high.sim_rows >= mid.sim_cols * mid.sim_rows and high.shaft_steps >= mid.shaft_steps
    assert level(GraphicsData().level).name == 'Cao'


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def test_analytic_sun_test_agrees_with_a_ray_against_every_box():
    """The shader's window test must match a real ray cast against the room's boxes (the bake's truth) at random points in the room and in the pool."""
    d = MapData()
    pm = build_map(d)
    sun = _unit(LookData().sun_dir)
    rects, wall = window_rects(d)
    boxes = [(lo, hi, o) for lo, hi, o in colliders(pm)]                 # window gaps are not bullet boxes: rays leave through the holes
    rng = random.Random(3)
    agree = total = lit = 0
    for _ in range(3000):
        p = (rng.uniform(-9.9, 9.9), rng.uniform(-0.6, 4.1), rng.uniform(-14.9, 14.9))
        if any(all(lo[i] < p[i] < hi[i] for i in range(3)) for lo, hi, _ in boxes):
            continue
        far = tuple(p[i] + sun[i] * 60.0 for i in range(3))
        truth = first_hit(p, far, boxes, ground_y=None) is None
        mine = sun_visible(p, sun, rects, wall) > 0.5
        total += 1
        agree += truth == mine
        lit += truth
    assert lit > 50                                                       # enough points in the beams for the check to mean something
    assert agree / total > 0.995


def test_exact_sunlit_segments_match_a_fine_march():
    """The shader's shafts integrate the sunlit length of each view ray analytically; it must equal marching the ray in 1 cm steps with the point test."""
    from fps.core.poolmap import sunlit_segments
    d = MapData()
    sun = _unit(LookData().sun_dir)
    rects, wall = window_rects(d)
    rng = random.Random(5)
    checked = 0
    for _ in range(60):
        eye = (rng.uniform(-9, 9), rng.uniform(0.3, 3.5), rng.uniform(-14, 14))
        p = (rng.uniform(-9.9, 9.9), rng.uniform(0.0, 4.1), rng.uniform(-14.9, 14.9))
        exact = sum(t1 - t0 for t0, t1 in sunlit_segments(eye, p, sun, rects, wall))
        length = math.dist(eye, p)
        n = int(length / 0.01) + 1
        marched = sum(sun_visible(tuple(eye[i] + (p[i] - eye[i]) * (k + 0.5) / n for i in range(3)), sun, rects, wall) for k in range(n)) * length / n
        assert exact == pytest.approx(marched, abs=0.03)
        checked += exact > 0.1
    assert checked >= 5                                                    # enough rays actually cross a beam


def test_basin_holds_the_steps_under_the_water():
    pm = build_map(MapData())
    (lo, hi), steps = basin_boxes(pm)
    assert hi[1] == pytest.approx(MapData().water_y) and lo[1] == pytest.approx(MapData().pool_deep)
    assert len(steps) == 1 + MapData().steps                                        # the shallow shelf + the south steps (no north steps: 2 m deep there)
    assert all(s_hi[1] < hi[1] for _, s_hi in steps)
