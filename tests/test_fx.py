import math

import pytest

from fps.core import fx
from fps.core.fx import Tracer


def test_flash_envelope_is_bright_then_gone():
    assert fx.flash_envelope(0.0, 0.05) == 1.0
    assert 0.0 < fx.flash_envelope(0.025, 0.05) < 1.0
    assert fx.flash_envelope(0.05, 0.05) == 0.0 and fx.flash_envelope(0.2, 0.05) == 0.0
    assert fx.flash_envelope(-0.01, 0.05) == 0.0
    ages = [i * 0.005 for i in range(10)]
    values = [fx.flash_envelope(a, 0.05) for a in ages]
    assert values == sorted(values, reverse=True)                 # only decreasing


def test_convergence_goes_from_full_offset_to_none():
    assert fx.convergence(0.0, 18.0) == 1.0
    assert fx.convergence(18.0, 18.0) == 0.0 and fx.convergence(100.0, 18.0) == 0.0
    assert fx.convergence(9.0, 18.0) == pytest.approx(0.5)
    assert fx.convergence(5.0, 0.0) == 0.0


@pytest.mark.parametrize('every, expected', [(3, [1, 4, 7, 10]), (1, list(range(1, 12))), (5, [1, 6, 11])])
def test_tracer_every_nth_shot_starting_with_the_first(every, expected):
    assert [n for n in range(1, 12) if fx.is_traced(n, every)] == expected


def test_tracer_disabled_with_zero():
    assert not any(fx.is_traced(n, 0) for n in range(1, 20))


def test_ribbon_width_never_thinner_than_a_few_pixels():
    near = fx.ribbon_width(5.0, 0.05, 2.2, 80.0, 1280)
    far = fx.ribbon_width(150.0, 0.05, 2.2, 80.0, 1280)
    assert near == 0.05                                           # near: keep the true width
    one_px = 150.0 * math.radians(80.0) / 1280
    assert far == pytest.approx(2.2 * one_px)                     # far: the true width is still under 1 pixel, so it is widened
    assert far > near


def test_lens_ratio_puts_the_streak_where_the_muzzle_is_on_screen():
    # muzzle offset 6.77 cm at 73 cm depth in the gun scene (FOV 70): normalized screen coordinates
    ndc_view = 0.0677 / 0.7326 / math.tan(math.radians(70) / 2)
    k = fx.lens_ratio(80.0, 70.0)
    ndc_world = 0.0677 * k / 0.7326 / math.tan(math.radians(80) / 2)
    assert ndc_world == pytest.approx(ndc_view)
    assert fx.lens_ratio(70.0, 70.0) == pytest.approx(1.0)


def make_tracer(offset=(0.07, -0.07, 0.0), length=7.0, blend=18.0):
    return Tracer(offset, length, blend, 500.0)


def test_tracer_starts_at_the_muzzle_and_ends_on_the_true_path():
    t = make_tracer()
    t.follow((0.0, 0.0, 0.2), (0.0, 0.0, 1.0), 0.2)               # just fired, has travelled 20 cm
    tail, head = t.endpoints()
    assert head[0] == pytest.approx(0.07 * fx.convergence(0.2, 18.0), abs=1e-3)
    assert tail == pytest.approx((0.07, -0.07, 0.0), abs=1e-3)    # the tail is still at the muzzle (full offset)
    t.follow((0.0, 0.0, 120.0), (0.0, 0.0, 1.0), 120.0)           # has travelled far: the streak lies on the true bullet path
    tail, head = t.endpoints()
    assert head == pytest.approx((0.0, 0.0, 120.0))
    assert tail == pytest.approx((0.0, 0.0, 113.0))
    assert t.endpoints()[1][2] - t.endpoints()[0][2] == pytest.approx(7.0)


def test_tracer_length_grows_from_zero_then_stays_constant():
    t = make_tracer(offset=(0.0, 0.0, 0.0))
    lengths = []
    for s in (1.0, 3.0, 7.0, 20.0, 80.0):
        t.follow((0.0, 0.0, s), (0.0, 0.0, 1.0), s)
        tail, head = t.endpoints()
        lengths.append(head[2] - tail[2])
    assert lengths == pytest.approx([1.0, 3.0, 7.0, 7.0, 7.0])


def test_tracer_drains_after_the_bullet_hits():
    t = make_tracer(offset=(0.0, 0.0, 0.0))
    t.follow((0.0, 0.0, 100.0), (0.0, 0.0, 1.0), 100.0)
    t.end((0.0, 0.0, 101.0), (0.0, 0.0, 1.0), 101.0)
    assert t.ended and not t.done
    t.advance(0.007)                                              # 3.5 m
    tail, head = t.endpoints()
    assert head == pytest.approx((0.0, 0.0, 101.0))               # the head stays still at the hit point
    assert head[2] - tail[2] == pytest.approx(7.0 - 3.5 + 1.0 - 1.0, abs=1.0)   # the tail catches up
    for _ in range(10):
        t.advance(0.004)
    assert t.done


def test_tracer_that_never_ended_is_never_done():
    t = make_tracer()
    t.follow((0.0, 0.0, 50.0), (0.0, 0.0, 1.0), 50.0)
    for _ in range(100):
        t.advance(0.05)
    assert not t.done
