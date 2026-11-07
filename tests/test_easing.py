"""Cubic-bezier easing (core/easing.py), checked against the CSS definition."""
import pytest

from fps.core.easing import CubicBezier, bezier


def test_endpoints_and_clamping():
    c = CubicBezier(0.42, 0.0, 0.58, 1.0)
    assert c(0.0) == 0.0 and c(1.0) == 1.0
    assert c(-0.5) == 0.0 and c(1.5) == 1.0


def test_linear_control_points_give_identity():
    c = CubicBezier(0.25, 0.25, 0.75, 0.75)
    for u in (0.1, 0.3, 0.5, 0.77, 0.95):
        assert c(u) == pytest.approx(u, abs=1e-6)


def test_ease_in_out_is_symmetric_slow_at_both_ends():
    c = CubicBezier(0.42, 0.0, 0.58, 1.0)
    assert c(0.5) == pytest.approx(0.5, abs=1e-6)
    for u in (0.1, 0.2, 0.35):
        assert c(u) + c(1 - u) == pytest.approx(1.0, abs=1e-6)
    assert c(0.05) < 0.02 and c(0.95) > 0.98


def test_solving_x_is_accurate_and_monotonic():
    c = CubicBezier(0.45, 0.0, 0.15, 1.0)
    last = -1.0
    for i in range(1, 200):
        u = i / 200
        t = c.solve_t(u)
        assert c._x(t) == pytest.approx(u, abs=1e-6)
        y = c(u)
        assert y >= last - 1e-9
        last = y


def test_y_beyond_one_overshoots_then_lands():
    c = CubicBezier(0.4, 0.0, 0.3, 1.2)
    assert max(c(i / 100) for i in range(100)) > 1.01
    assert c(1.0) == 1.0


def test_x_control_points_are_clamped_to_keep_time_monotonic():
    c = CubicBezier(-0.5, 0.0, 1.7, 1.0)
    assert c.points[0] == 0.0 and c.points[2] == 1.0
    vals = [c(i / 50) for i in range(51)]
    assert vals == sorted(vals)


def test_cached_curves_are_shared():
    assert bezier((0.42, 0, 0.58, 1)) is bezier((0.42, 0.0, 0.58, 1.0))
