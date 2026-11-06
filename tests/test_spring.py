import math

import pytest

from fps.core.spring import Spring, impulse_gain


def peak_of(omega, zeta, dt, seconds=1.0):
    s = Spring(1, omega, zeta)
    s.kick([impulse_gain(omega, zeta)])          # desired peak displacement = 1
    peak = 0.0
    for _ in range(round(seconds / dt)):
        s.step(dt)
        peak = max(peak, s.x[0])
    return peak, s


@pytest.mark.parametrize('omega,zeta', [(38.0, 0.55), (20.0, 0.3), (60.0, 0.8), (38.0, 0.99)])
def test_impulse_gain_gives_the_requested_peak(omega, zeta):
    peak, _ = peak_of(omega, zeta, 1 / 5000)
    assert peak == pytest.approx(1.0, abs=0.002)


def test_negative_peak_goes_the_other_way():
    s = Spring(1, 38.0, 0.55)
    s.kick([-0.02 * impulse_gain(38.0, 0.55)])
    low = 0.0
    for _ in range(600):
        s.step(1 / 600)
        low = min(low, s.x[0])
    assert low == pytest.approx(-0.02, rel=0.01)


@pytest.mark.parametrize('dt', [1 / 30, 1 / 60, 1 / 144, 1 / 1000, 0.05])
def test_motion_does_not_depend_on_frame_time(dt):
    ref = Spring(1, 38.0, 0.55)
    ref.kick([3.0])
    for _ in range(100):
        ref.step(0.001)                           # 0.1 s
    s = Spring(1, 38.0, 0.55)
    s.kick([3.0])
    n = round(0.1 / dt)
    for _ in range(n):
        s.step(dt)
    s.step(0.1 - n * dt) if abs(0.1 - n * dt) > 1e-12 else None
    assert s.x[0] == pytest.approx(ref.x[0], abs=1e-9)
    assert s.v[0] == pytest.approx(ref.v[0], abs=1e-9)


def test_comes_to_rest_and_stays_stable_at_a_huge_step():
    s = Spring(3, 38.0, 0.55)
    s.kick([1.0, -2.0, 0.5])
    for _ in range(200):
        s.step(0.05)
    assert all(abs(v) < 1e-6 for v in s.x + s.v)
    s.kick([1.0, 1.0, 1.0])
    s.step(5.0)                                   # a huge step does not blow up the numbers
    assert all(math.isfinite(v) and abs(v) < 1e-6 for v in s.x + s.v)


def test_components_are_independent():
    s = Spring(2, 38.0, 0.55)
    s.kick([1.0, 0.0])
    for _ in range(10):
        s.step(1 / 60)
    assert s.x[0] != 0 and s.x[1] == 0 and s.v[1] == 0


def test_overdamped_request_is_clamped_not_broken():
    s = Spring(1, 38.0, 3.0)
    s.kick([impulse_gain(38.0, 3.0)])
    for _ in range(100):
        s.step(1 / 60)
        assert math.isfinite(s.x[0])
