import math
import random

import pytest

from fps.core.patrol import Patrol, phase_start


def make(**kw):
    args = dict(lo=-7.0, hi=7.0, speed=3.0, pause=0.0, x=0.0, direction=1.0)
    args.update(kw)
    return Patrol(**args)


def test_walks_at_the_given_speed():
    p = make()
    p.advance(1.0)
    assert p.x == pytest.approx(3.0)
    assert p.velocity == 3.0


def test_turns_back_at_the_limit_with_the_leftover_time():
    p = make(x=6.0)                      # 1 m left to the right limit, speed 3: 0.333 s to get there, leaving 0.667 s to go back 2 m
    p.advance(1.0)
    assert p.x == pytest.approx(5.0)
    assert p.direction == -1.0


def test_pause_at_each_end_then_resumes():
    p = make(x=6.9, pause=0.5, speed=1.0)
    p.advance(0.1)                       # reaches the right limit, turns around, starts the pause
    assert p.x == pytest.approx(7.0) and p.velocity == 0.0
    p.advance(0.4)
    assert p.x == pytest.approx(7.0) and p.velocity == 0.0
    p.advance(0.2)                       # the 0.5 s pause ends, then it moves 0.1 s in the negative direction
    assert p.x == pytest.approx(6.9) and p.velocity == -1.0


def test_never_leaves_the_limits_even_for_a_huge_step():
    p = make(pause=0.3)
    for dt in (0.0, 0.016, 0.05, 1.0, 37.5, 1000.0):
        p.advance(dt)
        assert -7.0 <= p.x <= 7.0


@pytest.mark.parametrize('fps', [20, 30, 60, 144, 240])
def test_position_does_not_depend_on_the_frame_rate(fps):
    ref, p = make(pause=0.35, x=-3.0), make(pause=0.35, x=-3.0)
    ref.advance(23.0)
    for _ in range(23 * fps):
        p.advance(1.0 / fps)
    assert p.x == pytest.approx(ref.x, abs=1e-6)
    assert p.direction == ref.direction


def test_irregular_steps_equal_one_big_step():
    rng = random.Random(5)
    total, p, ref = 0.0, make(pause=0.2), make(pause=0.2)
    while total < 40.0:
        dt = rng.uniform(0.001, 0.05)
        p.advance(dt)
        total += dt
    ref.advance(total)
    assert p.x == pytest.approx(ref.x, abs=1e-6)


def test_period_matches_a_full_round_trip():
    p = make(lo=0.0, hi=6.0, speed=2.0, pause=0.5, x=0.0)
    assert p.period == pytest.approx(7.0)            # 3 s out + 0.5 pause, 3 s back + 0.5 pause
    p.advance(p.period)
    assert p.x == pytest.approx(0.0) and p.direction == 1.0 and p.wait == 0.0


def test_average_speed_over_a_straight_run_is_exact():
    p = make(lo=-100.0, hi=100.0, speed=4.0)
    x0 = p.x
    n = 600
    for _ in range(n):
        p.advance(1.0 / 60.0)
    assert (p.x - x0) / (n / 60.0) == pytest.approx(4.0)


def test_zero_speed_stands_still():
    p = make(speed=0.0)
    p.advance(10.0)
    assert p.x == 0.0


def test_bad_limits_are_rejected():
    with pytest.raises(ValueError):
        Patrol(lo=1.0, hi=1.0, speed=1.0)


def test_phase_start_covers_the_round_trip():
    lo, hi = -6.0, 6.0
    assert phase_start(lo, hi, 0.0) == (lo, 1.0)
    assert phase_start(lo, hi, 0.25) == (0.0, 1.0)
    assert phase_start(lo, hi, 0.5) == (hi, -1.0)
    assert phase_start(lo, hi, 0.75) == (0.0, -1.0)
    assert phase_start(lo, hi, 1.25) == phase_start(lo, hi, 0.25)
    for ph in (0.0, 0.1, 0.37, 0.5, 0.93):
        x, d = phase_start(lo, hi, ph)
        assert lo <= x <= hi and d in (1.0, -1.0)
        assert math.isfinite(x)
