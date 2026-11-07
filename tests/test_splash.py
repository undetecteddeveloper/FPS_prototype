import math
import random

import pytest

from fps.core.splash import SplashSim, Wake, wade_speed_factor, water_depth
from fps.weapon_data import SplashData

S = SplashData()
SURFACE = -0.12


def run(sim, seconds, dt=1 / 60):
    fell = []
    for _ in range(round(seconds / dt)):
        fell += sim.step(dt, S.gravity, S.drag, SURFACE)
    return fell


def test_drops_fly_up_and_fall_back_into_the_water():
    sim = SplashSim(rng=random.Random(1))
    sim.burst((0.0, SURFACE, 0.0), 20, S.bullet_speed, 0.0, 0.0, S.drop_size, S.drop_life)
    run(sim, 0.2)
    assert sim.count == 20 and all(d[1] > SURFACE for d in sim.draw_items())
    fell = run(sim, 2.0)
    assert sim.count == 0 and len(fell) == 20


def test_flight_matches_the_ballistic_height_and_does_not_depend_on_the_frame_rate():
    tops = []
    for dt in (1 / 30, 1 / 240):
        sim = SplashSim(rng=random.Random(1))
        sim.burst((0.0, 0.0, 0.0), 1, 3.0, 0.0, 0.0, 0.01, 5.0)
        best = 0.0
        for _ in range(round(0.6 / dt)):
            sim.step(dt, 9.81, 0.0, -10.0)
            best = max(best, sim.drops[0][1])
        tops.append(best)
    assert tops[0] == pytest.approx(3.0 ** 2 / (2 * 9.81), abs=0.02)
    assert tops[1] == pytest.approx(3.0 ** 2 / (2 * 9.81), abs=0.005)


def test_drag_slows_the_drops():
    a, b = SplashSim(rng=random.Random(2)), SplashSim(rng=random.Random(2))
    for sim, drag in ((a, 0.0), (b, 2.0)):
        sim.burst((0.0, 0.0, 0.0), 1, 4.0, 0.0, 0.0, 0.01, 5.0, up=(1.0, 0.0, 0.0))
        for _ in range(30):
            sim.step(1 / 60, 0.0, drag, -10.0)
    assert b.drops[0][0] < a.drops[0][0]


def test_pool_is_capped():
    sim = SplashSim(capacity=10, rng=random.Random(3))
    sim.burst((0, 0, 0), 25, 2.0, 0.3, 30.0, 0.01, 1.0)
    assert sim.count == 10 and sim.spawned == 25


def test_wading_is_slower_the_deeper_the_water():
    assert water_depth(0.0, SURFACE) == 0.0
    assert water_depth(-0.62, SURFACE) == pytest.approx(0.5)
    assert wade_speed_factor(0.0, 1.25, S.wade_slow) == 1.0
    assert wade_speed_factor(1.25, 1.25, S.wade_slow) == pytest.approx(S.wade_slow)
    assert 1.0 > wade_speed_factor(0.5, 1.25, S.wade_slow) > wade_speed_factor(1.0, 1.25, S.wade_slow)


def test_the_wake_pushes_every_spacing_and_at_once_when_entering():
    w = Wake()
    assert w.update(0, 0, 0.1, 0.0, 1.0, S.wake_spacing, S.wake_push, S.wake_radius, 1.25) == []      # on the deck: nothing
    first = w.update(0, 0, 0.0, 0.5, 1.0, S.wake_spacing, S.wake_push, S.wake_radius, 1.25)
    assert len(first) == 1 and first[0][3] < 0.0                                                            # stepping in pushes the water at once
    pushes = 0
    for _ in range(100):                                                                                     # 100 x 3.2 cm = 3.2 m walked
        pushes += len(w.update(0, 0, 0.032, 0.5, 1.9, S.wake_spacing, S.wake_push, S.wake_radius, 1.25))
    assert pushes == pytest.approx(3.2 / S.wake_spacing, abs=1)
    deep = w.update(0, 0, S.wake_spacing, 1.2, 1.9, S.wake_spacing, S.wake_push, S.wake_radius, 1.25)
    shallow = Wake()
    shallow.update(0, 0, 0.0, 0.2, 1.9, S.wake_spacing, S.wake_push, S.wake_radius, 1.25)
    low = shallow.update(0, 0, S.wake_spacing, 0.2, 1.9, S.wake_spacing, S.wake_push, S.wake_radius, 1.25)
    assert abs(deep[0][3]) > abs(low[0][3])                                                                 # deeper water: a bigger wave
