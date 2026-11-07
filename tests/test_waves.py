import math

import pytest

from fps.core.waves import RippleBuffer, ambient_slope, ring_slope, surface_normal, surface_slope
from fps.weapon_data import WaterData

W = WaterData()


def test_ambient_ripples_are_bounded_by_the_strength_and_move_with_time():
    slopes = [ambient_slope(x * 0.37, z * 0.41, t, W) for x in range(12) for z in range(12) for t in (0.0, 1.3, 7.7)]
    assert max(math.hypot(*s) for s in slopes) <= W.ripple_strength * 1.0001
    assert max(math.hypot(*s) for s in slopes) > 0.3 * W.ripple_strength
    assert ambient_slope(3.0, 2.0, 0.0, W) != ambient_slope(3.0, 2.0, 2.0, W)


def test_zero_strength_is_a_flat_mirror():
    flat = WaterData(ripple_strength=0.0)
    assert ambient_slope(1.0, 2.0, 5.0, flat) == (0.0, 0.0)
    assert surface_normal(1.0, 2.0, 5.0, [], flat) == pytest.approx((0.0, 1.0, 0.0))


def test_ripples_depend_on_absolute_time_only():
    """The same absolute time gives the same slope however the time was reached: there is no state that a frame rate could change."""
    ring = (1.0, 2.0, 0.5, 1.0)
    a = surface_slope(2.2, 3.1, 1.7, [ring], W)
    b = surface_slope(2.2, 3.1, 1.7, [ring], W)
    assert a == b


def test_ring_is_zero_before_it_starts_and_after_its_life():
    ring = (0.0, 0.0, 10.0, 1.0)
    assert ring_slope(1.0, 0.0, 9.9, ring, W) == (0.0, 0.0)
    assert ring_slope(1.0, 0.0, 10.0 + W.impact_life, ring, W) == pytest.approx((0.0, 0.0), abs=1e-12)    # (float rounding may leave it 1 ulp before the end: the fade makes it ~0 anyway)
    assert ring_slope(1.0, 0.0, 10.0 + W.impact_life + 5, ring, W) == (0.0, 0.0)


def test_ring_slope_is_radial_and_peaks_on_the_expanding_front():
    ring = (0.0, 0.0, 0.0, 1.0)
    age = 0.8
    front = W.impact_speed * age
    sx, sz = ring_slope(front, 0.0, age, ring, W)
    assert sz == pytest.approx(0.0, abs=1e-12) and abs(sx) > 0                      # points along x on the +x axis: purely radial
    ux, uz = ring_slope(0.0, front, age, ring, W)
    assert ux == pytest.approx(0.0, abs=1e-12) and abs(uz) == pytest.approx(abs(sx), rel=1e-9)   # the same ring, rotated: symmetric
    peak = max(abs(ring_slope(r / 100.0, 0.0, age, ring, W)[0]) for r in range(0, 900))
    far = abs(ring_slope(front + 4 * W.impact_width, 0.0, age, ring, W)[0])
    assert peak > 20 * far                                                            # the packet is localised on the front, not everywhere


def test_ring_fades_with_age_and_spreads_with_distance():
    ring = (0.0, 0.0, 0.0, 1.0)

    def peak(age):
        return max(abs(ring_slope(r / 50.0, 0.0, age, ring, W)[0]) for r in range(1, 600))
    assert peak(0.3) > peak(1.2) > peak(2.4)
    assert peak(2.5) < 0.01 * peak(0.3)


def test_ring_has_no_jump_at_the_centre_or_at_the_end_of_life():
    ring = (0.0, 0.0, 0.0, 1.0)
    assert ring_slope(0.0, 0.0, 0.1, ring, W) == (0.0, 0.0)
    assert abs(ring_slope(1e-3, 0.0, 0.1, ring, W)[0]) < 5e-3                         # vanishes smoothly at the centre
    just_before = max(abs(ring_slope(r / 20.0, 0.0, W.impact_life - 1e-3, ring, W)[0]) for r in range(1, 200))
    assert just_before < 1e-4                                                          # no pop when the ring is switched off


def test_amp_scales_the_ring():
    a = ring_slope(1.0, 0.0, 0.6, (0.0, 0.0, 0.0, 1.0), W)[0]
    b = ring_slope(1.0, 0.0, 0.6, (0.0, 0.0, 0.0, 0.5), W)[0]
    assert b == pytest.approx(0.5 * a)


def test_surface_normal_is_unit_and_tilts_against_the_slope():
    n = surface_normal(1.0, 2.0, 0.5, [(0.5, 2.0, 0.0, 1.0)], W)
    assert math.sqrt(sum(c * c for c in n)) == pytest.approx(1.0)
    sx, sz = surface_slope(1.0, 2.0, 0.5, [(0.5, 2.0, 0.0, 1.0)], W)
    assert n[0] * sx <= 0 and n[2] * sz <= 0 and n[1] > 0.9


def test_ripple_buffer_reuses_the_oldest_slot_and_counts_the_living():
    buf = RippleBuffer(3)
    for i in range(4):
        buf.add(i, 0.0, float(i))
    assert [r[0] for r in buf.rings] == [3.0, 1.0, 2.0]                               # the fourth shot replaced the first
    assert buf.alive(3.5, 2.6) == 3 and buf.alive(10.0, 2.6) == 0
    assert len(buf.packed()) == 3
    assert RippleBuffer(5).alive(0.0, 2.6) == 0                                        # empty slots are 'born' in the far past
