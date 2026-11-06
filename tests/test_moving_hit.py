"""Bullet hit test against a box (target) moving while the bullet flies: exact for uniform motion, with no error of speed x dt."""
import pytest

from fps.core.ballistics import advance, moving_hit, segment_vs_aabb, segment_vs_moving_aabb

LO, HI = (-0.5, 0.0, 9.97), (0.5, 2.0, 10.03)          # target 1 m wide and thin, at z = 10, step start at x = 0
V = 500.0


def bullet_segment(dt, x_aim=0.0):
    return (x_aim, 1.0, 0.0), (x_aim, 1.0, V * dt)


def test_zero_displacement_is_the_static_test():
    p0, p1 = bullet_segment(0.03)
    assert segment_vs_moving_aabb(p0, p1, LO, HI, (0, 0, 0)) == segment_vs_aabb(p0, p1, LO, HI)


def test_box_moving_into_the_line_of_fire_is_hit_at_the_right_time():
    # target moves right at 4 m/s; step 0.03 s: target shifts 0.12 m. Bullet aims at x = 0.56: outside the edge (0.5) at the start of the step,
    # but when the bullet reaches z = 10 (t = 0.02 s) the target is at x = 0.08, so its right edge is at 0.58 -> HIT
    dt, v = 0.03, 4.0
    p0, p1 = bullet_segment(dt, 0.56)
    assert segment_vs_aabb(p0, p1, LO, HI) is None                       # if the target stood still at the start-of-step position it would miss
    h = moving_hit(p0, p1, LO, HI, (v * dt, 0, 0), 'bia')
    assert h is not None and h.owner == 'bia'
    assert h.t == pytest.approx(9.97 / (V * dt), abs=1e-6)               # target front face at z = 9.97
    assert h.point[2] == pytest.approx(9.97, abs=1e-3)                    # the hit point is where the bullet currently is


def test_box_moving_away_misses():
    dt, v = 0.03, 4.0
    p0, p1 = bullet_segment(dt, 0.45)                                    # standing still it would hit (0.45 < 0.5)
    assert segment_vs_aabb(p0, p1, LO, HI) is not None
    # target moves left: when the bullet arrives, its right edge is at 0.5 - 0.08 = 0.42 < 0.45 -> miss
    assert moving_hit(p0, p1, LO, HI, (-v * dt, 0, 0), 'bia') is None


@pytest.mark.parametrize('dt', [1 / 240, 1 / 120, 1 / 60, 1 / 30, 1 / 20])
def test_edge_decision_is_the_same_at_any_step_length(dt):
    """Target at 4 m/s, bullet flies straight to z = 10 (0.02 s). The target's right edge when the bullet arrives is 0.5 + 4 * 0.02 = 0.58 m:
    aim 0.57 must hit, aim 0.59 must miss, whatever the step (frame) length. (Using the end-of-step position would be off by up to 4 * dt.)"""
    v = 4.0
    t_fly = 10.0 / V
    for aim, expect_hit in ((0.57, True), (0.59, False)):
        pos, t, hit = (aim, 1.0, 0.0), 0.0, None
        while hit is None and t < 0.1:
            new_pos, _ = advance(pos, (0, 0, V), 0.0, dt)
            lo = (LO[0] + v * t, LO[1], LO[2])
            hi = (HI[0] + v * t, HI[1], HI[2])
            hit = moving_hit(pos, new_pos, lo, hi, (v * dt, 0, 0), 'bia')
            pos, t = new_pos, t + dt
        assert (hit is not None) == expect_hit, (aim, dt)
        if hit:
            assert hit.point[2] == pytest.approx(9.97, abs=1e-6)
            assert t - dt + hit.t * dt == pytest.approx(t_fly - 0.03 / V, abs=1e-6)
