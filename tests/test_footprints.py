import math

import pytest

from fps.core.footprints import SLOTS, FootprintTrail, pack, unpack
from fps.weapon_data import SplashData

S = SplashData()


def walk(trail, t, x, z, dx, dz, frames, in_water=False, dt=1 / 60):
    added = []
    for _ in range(frames):
        x, z, t = x + dx, z + dz, t + dt
        added += trail.update(t, x, z, dx, dz, in_water, not in_water, S.feet_dry, S.print_spacing)
        trail.dry(dt, S.feet_dry)
    return added, x, z, t


def test_no_prints_with_dry_feet():
    tr = FootprintTrail()
    added, *_ = walk(tr, 0.0, 0.0, -13.0, 0.0, 0.07, 120)
    assert added == []


def test_out_of_the_water_the_feet_leave_alternating_prints_that_get_fainter():
    tr = FootprintTrail()
    walk(tr, 0.0, 0.0, -10.0, 0.0, 0.0, 5, in_water=True)
    added, *_ = walk(tr, 0.0, 0.0, -12.0, 0.0, -0.07, 300)          # 5 s walking south on the deck at 4.2 m/s
    assert len(added) == pytest.approx(300 * 0.07 / S.print_spacing, abs=2)
    xs = [p[0] for p in added]
    assert all((a > 0) != (b > 0) for a, b in zip(xs, xs[1:]))        # left, right, left...
    strengths = [p[4] for p in added]
    assert strengths[0] > strengths[-1] > 0.0
    assert all(abs(p[3] - math.pi) < 1e-6 for p in added)              # walking south: yaw pi


def test_feet_dry_out_and_the_trail_is_a_ring():
    tr = FootprintTrail()
    walk(tr, 0.0, 0.0, -10.0, 0.0, 0.0, 2, in_water=True)
    added, *_ = walk(tr, 0.0, 0.0, -12.0, 0.04, 0.0, int(S.feet_dry * 60) + 120)
    assert tr.wet == 0.0 and added
    assert tr.count > SLOTS or len([p for p in tr.prints if p[2] > -1]) == tr.count


def test_pack_roundtrip():
    for yaw, s in ((0.0, 1.0), (3.1, 0.42), (6.2, 0.0)):
        w = pack(0, 0, 0, yaw, s)[3]
        y2, s2 = unpack(w)
        assert y2 == pytest.approx(yaw, abs=1e-6) and s2 == pytest.approx(round(s * 100) / 100)
