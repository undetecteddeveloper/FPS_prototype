"""Reload gaze (core/gaze.py): saccades with minimum-jerk easing, rests, slow pursuit, per-reload variation, look back up when the window closes."""
import pytest

from fps.core.gaze import ReloadGaze, min_jerk
from fps.weapon_data import HeadCamData

D = HeadCamData()
DT = 1 / 120


def run(g, seconds, active, target=None, **kw):
    out = []
    for _ in range(int(round(seconds / DT))):
        out.append(g.update(DT, active, target, **kw))
    return out


def test_min_jerk_starts_and_ends_at_rest_and_is_fastest_in_the_middle():
    assert min_jerk(0.0) == 0.0 and min_jerk(1.0) == pytest.approx(1.0)
    h = 1e-4
    speed = lambda u: (min_jerk(u + h) - min_jerk(u - h)) / (2 * h)
    assert speed(0.02) < 0.05 and speed(0.98) < 0.05
    assert speed(0.5) > speed(0.25) > speed(0.05)


def test_first_dip_eases_in_and_out_instead_of_a_linear_slide():
    g = ReloadGaze(D, seed=1)
    trace = [p for p, _ in run(g, 0.6, True, (-15.0, 0.0), enter_time=0.3)]
    steps = [a - b for a, b in zip(trace, trace[1:])]           # downward speed per frame
    peak = max(range(len(steps)), key=lambda i: steps[i])
    assert steps[1] < 0.3 * steps[peak]                         # slow start
    assert 5 < peak < 40                                        # fastest somewhere in the middle of the move, not at the start
    assert trace[-1] < -12.0                                    # reached the target area


def test_gaze_jumps_to_a_new_point_only_after_resting_and_only_when_it_moved_far_enough():
    g = ReloadGaze(D, seed=2)
    run(g, 0.8, True, (-15.0, 0.0), enter_time=0.25)
    n = g.saccades
    run(g, 0.5, True, (-15.0 + D.gaze_threshold * 0.5, 0.0))      # target moves a little: no new glance
    assert g.saccades == n
    run(g, 0.6, True, (-4.0, 8.0))                               # target jumps far: a new glance
    assert g.saccades == n + 1


def test_looks_back_up_when_the_window_closes():
    g = ReloadGaze(D, seed=3)
    run(g, 1.0, True, (-15.0, 3.0), enter_time=0.3)
    run(g, 0.8, False, leave_time=0.35)
    assert abs(g.pitch) < 0.05 and abs(g.yaw) < 0.05


def test_two_reloads_do_not_trace_the_same_path():
    g = ReloadGaze(D, seed=4)
    a = run(g, 1.0, True, (-15.0, 0.0), enter_time=0.3)
    run(g, 1.0, False, leave_time=0.35)
    b = run(g, 1.0, True, (-15.0, 0.0), enter_time=0.3)
    assert max(abs(x[0] - y[0]) for x, y in zip(a, b)) > 0.3


def test_no_variation_when_jitter_is_zero():
    import dataclasses
    d = dataclasses.replace(HeadCamData(), gaze_jitter=0.0, glance_drift=0.0, gaze_overshoot=0.0)
    g = ReloadGaze(d, seed=5)
    a = run(g, 1.0, True, (-15.0, 0.0), enter_time=0.3)
    run(g, 1.0, False, leave_time=0.35)
    b = run(g, 1.0, True, (-15.0, 0.0), enter_time=0.3)
    assert max(abs(x[0] - y[0]) for x, y in zip(a, b)) < 1e-6


def test_gaze_stays_inside_its_limits():
    g = ReloadGaze(D, seed=6)
    for p, y in run(g, 1.5, True, (-80.0, 60.0), enter_time=0.3):
        assert p >= -D.glance_pitch * 1.25 * (1 + D.gaze_overshoot) - D.glance_drift - 1e-6
        assert abs(y) <= D.gaze_max_yaw * (1 + D.gaze_overshoot) + D.glance_drift + 1e-6


def test_without_a_target_it_dips_to_the_default_glance():
    g = ReloadGaze(D, seed=7)
    run(g, 1.2, True, None, enter_time=0.3)
    assert g.pitch == pytest.approx(-D.glance_pitch, rel=0.25)
