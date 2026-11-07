import math
import random
from dataclasses import replace

import pytest

from fps.core import smoke
from fps.core.smoke import SmokeSim
from fps.weapon_data import SmokeData

UP = (0.0, 1.0, 0.0)
FWD = (0.0, 0.0, 1.0)


def quiet(**kw) -> SmokeData:
    """One puff, no randomness (no jitter, cone, turbulence), unless overridden."""
    base = dict(puffs=1, speed_jitter=0.0, cone=0.0, turbulence=0.0, life_jitter=0.0, port_puffs=0)
    base.update(kw)
    return replace(SmokeData(), **base)


def run(sim, seconds, hz, wind=(0.0, 0.0, 0.0), ground_y=-100.0):
    n = int(round(seconds * hz))
    for _ in range(n):
        sim.step(1.0 / hz, wind, ground_y)


def only(sim):
    (pos, radius, alpha), = list(sim.particles())
    return pos, radius, alpha


def test_drag_brings_velocity_to_the_wind():
    sim = SmokeSim(rng=random.Random(1))
    sim.emit(quiet(rise=0.0, life=5.0, speed=9.0), (0, 1.5, 0), FWD)
    wind = (0.6, 0.0, 0.25)
    run(sim, 1.0, 60, wind)
    (v,) = list(sim.velocities())
    assert v == pytest.approx(wind, abs=0.01)
    pos, _, _ = only(sim)
    assert pos[2] == pytest.approx(9.0 / 7.0 + 0.25 * 1.0, abs=0.05)       # stops after ~speed/drag, then drifts


def test_rise_lifts_the_puff():
    sim = SmokeSim(rng=random.Random(2))
    sim.emit(quiet(rise=0.35, speed=0.0, life=2.0), (0, 1.0, 0), FWD)
    run(sim, 1.0, 60)
    pos, _, _ = only(sim)
    assert pos[1] > 1.02
    (v,) = list(sim.velocities())
    assert 0.0 < v[1] <= 0.35 / 7.0 + 1e-6                                     # never faster than the terminal climb rise/drag


def test_ground_is_never_penetrated_and_a_puff_fired_at_it_spreads():
    data = quiet(rise=0.0, speed=9.0, drag=7.0, life=1.0, ground_spread=0.6)
    sim = SmokeSim(rng=random.Random(3))
    down = (0.0, -1.0, 0.0)
    sim.emit(data, (0, 0.3, 0), down)
    lowest = 10.0
    for _ in range(50):
        sim.step(1 / 60, (0, 0, 0), 0.0)
        for pos, r, _ in sim.particles():
            assert pos[1] >= smoke.GROUND_LIFT * r - 1e-9
            lowest = min(lowest, pos[1])
    pos, _, _ = only(sim)
    assert math.hypot(pos[0], pos[2]) > 0.1                                   # straight down with no sideways speed: random heading, still spreads
    # slanted at the ground: spreads further along its horizontal direction
    sim2 = SmokeSim(rng=random.Random(4))
    sim2.emit(data, (0, 0.3, 0), (0.0, -0.8, 0.6))
    run(sim2, 0.5, 60, ground_y=0.0)
    pos2, _, _ = only(sim2)
    free = SmokeSim(rng=random.Random(4))
    free.emit(replace(data, ground_spread=0.0), (0, 0.3, 0), (0.0, -0.8, 0.6))
    run(free, 0.5, 60, ground_y=0.0)
    pos3, _, _ = only(free)
    assert pos2[2] > pos3[2] + 0.05 and abs(pos2[0]) < 1e-6


def test_alpha_reaches_zero_and_puff_is_removed_at_end_of_life():
    sim = SmokeSim(rng=random.Random(5))
    sim.emit(quiet(life=1.0), (0, 1.5, 0), FWD)
    alphas = []
    for _ in range(59):
        sim.step(1 / 60, (0, 0, 0))
        alphas.append(only(sim)[2])
    assert max(alphas) == pytest.approx(SmokeData().opacity, rel=0.05)
    assert alphas[-1] < 0.002
    assert alphas[5:] == sorted(alphas[5:], reverse=True)
    sim.step(1 / 60, (0, 0, 0))
    sim.step(1 / 60, (0, 0, 0))
    assert sim.count == 0 and list(sim.particles()) == []
    assert smoke.puff_alpha(1.0, 1.0, 0.3) == 0.0 and smoke.puff_alpha(0.0, 1.0, 0.3) == 0.0


def test_radius_grows_like_sqrt_of_age():
    d = SmokeData()
    assert smoke.puff_radius(0.0, 1.0, d.size, d.growth) == d.size
    assert smoke.puff_radius(0.25, 1.0, d.size, d.growth) == pytest.approx(d.size + d.growth * 0.5)
    assert smoke.puff_radius(1.0, 1.0, d.size, d.growth) == pytest.approx(d.size + d.growth)


def test_capacity_reuses_the_oldest():
    sim = SmokeSim(capacity=8, rng=random.Random(6))
    data = quiet(puffs=3, life=10.0)
    sim.emit(data, (0, 1, 0), FWD)
    sim.step(0.5, (0, 0, 0))
    sim.emit(data, (0, 1, 0), FWD)
    sim.emit(replace(data, puffs=2), (0, 1, 0), FWD)
    assert sim.count == 8
    sim.emit(replace(data, puffs=1), (0, 1, 0), FWD)                          # full: one of the 3 old puffs is replaced
    assert sim.count == 8 and sorted(sim.ages()).count(0.5) == 2
    for _ in range(5):
        sim.emit(data, (0, 1, 0), FWD)
        assert sim.count == 8
    assert max(sim.ages()) == 0.0                                             # the old ones went first


def test_frame_rate_independent():
    data = replace(SmokeData(), puffs=5, port_puffs=0)
    out = []
    for hz in (30, 120):
        sim = SmokeSim(rng=random.Random(7))
        sim.emit(data, (0, 1.5, 0), (0.0, 0.1, 0.995))
        run(sim, 0.6, hz, (0.6, 0.0, 0.25), 0.0)
        out.append(sorted(p for p, _, _ in sim.particles()))
    for a, b in zip(*out):
        assert math.dist(a, b) < 0.02


def test_port_puffs_only_with_a_port():
    data = replace(SmokeData(), puffs=5, port_puffs=2)
    sim = SmokeSim(rng=random.Random(8))
    sim.emit(data, (0, 1.5, 0), FWD)
    assert sim.count == 5
    sim.emit(data, (0, 1.5, 0), FWD, port=(0.05, 1.45, -0.2), port_dir=(1.0, 0.5, 0.0))
    assert sim.count == 12
    sim.step(1 / 60, (0, 0, 0))
    small = [r for _, r, _ in sim.particles() if r < 0.08]
    assert len(small) == 2                                                     # the port puffs are the smaller ones


def test_zero_puffs_emits_nothing():
    sim = SmokeSim(rng=random.Random(9))
    sim.emit(replace(SmokeData(), puffs=0, port_puffs=0), (0, 1.5, 0), FWD, port=(0, 1.4, 0))
    assert sim.count == 0
    sim.step(1 / 60, (0, 0, 0))
    assert sim.count == 0


def test_muzzle_puffs_stay_in_the_cone_and_slow_ones_form_a_core():
    data = replace(SmokeData(), puffs=6, port_puffs=0, turbulence=0.0)
    sim = SmokeSim(rng=random.Random(10))
    sim.emit(data, (0, 0, 0), FWD)
    speeds = []
    for vx, vy, vz in sim.velocities():
        s = math.sqrt(vx * vx + vy * vy + vz * vz)
        speeds.append(s)
        assert math.degrees(math.acos(vz / s)) <= data.cone + 1e-6
    assert max(speeds) > 2.5 * min(speeds)


def test_thin_items_keeps_a_stable_half_and_keeps_the_cloud_opacity():
    """G13 'Khói súng: Đơn giản': the same puffs every frame (by seed), about half of them, each denser so two stacked puffs' opacity is kept."""
    import random
    from fps.core.smoke import thin_items
    rnd = random.Random(5)
    items = [(rnd.random(), 0.0, 0.0, 0.1, rnd.uniform(0.0, 0.4), rnd.random()) for _ in range(2000)]
    kept = thin_items(items, 0.5)
    assert 900 < len(kept) < 1100
    assert {k[5] for k in kept} == {i[5] for i in items if i[5] < 0.5}            # chosen by seed only: no flicker when the list order changes
    assert thin_items(list(reversed(items)), 0.5) == list(reversed(kept))
    for (x, y, z, r, a, s), k in zip([i for i in items if i[5] < 0.5], kept):
        assert abs(k[4] - (1.0 - (1.0 - a) ** 2)) < 1e-12 and k[:4] == (x, y, z, r) and a <= k[4] <= 2 * a + 1e-12
    assert thin_items(items, 1.0) is items
