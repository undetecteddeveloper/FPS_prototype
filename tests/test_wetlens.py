"""G12: wet lens after surfacing (core/wetlens.py): the film runs off in ~film_time, drops dry within a few seconds, nothing depends on the frame rate."""
import random

import pytest

from fps.core.wetlens import WetLens, film_front, film_passes
from fps.weapon_data import UnderwaterData

U = UnderwaterData()


def run(dt, seconds, dip=1.0, top=1.0, seed=3, dip_time=0.5):
    """Under the water for `dip_time`, then out for `seconds`, in steps of dt. Returns the lens."""
    w = WetLens(U, random.Random(seed))
    for _ in range(round(dip_time / dt)):
        w.update(dt, dip, top)
    w.update(dt, 0.0, -1.0)                                     # the frame it comes out
    for _ in range(round(seconds / dt) - 1):
        w.update(dt, 0.0, -1.0)
    return w


def test_film_front_runs_from_the_top_to_the_bottom_in_film_time():
    assert film_front(0.0, 1.0, U.film_time) == pytest.approx(1.0)
    assert film_front(U.film_time, 1.0, U.film_time) == pytest.approx(-1.0)
    ys = [film_front(t * 0.05, 1.0, U.film_time) for t in range(21)]
    assert all(a >= b for a, b in zip(ys, ys[1:]))
    assert ys[1] - ys[2] < ys[18] - ys[19]                                                   # slow start, then it runs off
    for y in (0.8, 0.0, -0.7):
        assert film_front(film_passes(y, 1.0, U.film_time), 1.0, U.film_time) == pytest.approx(y)


def test_film_is_gone_after_about_a_second_and_drops_dry_in_a_few_seconds():
    w = run(1 / 60, 0.1)
    assert w.film()[1] > 0.9
    w = run(1 / 60, U.film_time + 0.05)
    assert w.film()[1] == 0.0
    assert U.film_time == pytest.approx(1.0)
    w = run(1 / 60, U.film_time)
    assert len(w.visible_drops()) >= U.drops // 2                                          # behind the film: drops
    w = run(1 / 60, U.film_time + U.drop_life * 1.3 + 0.1)
    assert w.visible_drops() == [] and not w.active()
    assert U.drop_life * 1.3 + U.film_time < 8.0


def test_drops_shrink_creep_down_and_fade():
    w = run(1 / 60, 0.0)
    d = max(w.drops, key=lambda dr: dr.life)
    a = d.at(d.appear + 0.1)
    b = d.at(d.appear + d.life * 0.8)
    assert b[1] < a[1] and b[2] < a[2] and b[3] < a[3]
    assert d.at(d.appear - 0.01) is None and d.at(d.appear + d.life + 0.01) is None


def test_same_picture_at_30_and_240_fps():
    a = run(1 / 30, 1.5)
    b = run(1 / 240, 1.5)
    assert a.age == pytest.approx(b.age, abs=1 / 30)
    da, db = a.packed(12), b.packed(12)
    for p, q in zip(da, db):
        assert p == pytest.approx(q, abs=0.02)                                             # positions / sizes within a frame of 1/30 s of drift
    assert a.film()[1] == b.film()[1]


def test_a_partial_dip_leaves_a_lower_film_and_fewer_drops_and_a_tiny_one_nothing():
    full = run(1 / 60, 0.0)
    part = run(1 / 60, 0.0, dip=0.3, top=-0.4)
    assert part.top == pytest.approx(-0.4) and part.film()[0] <= -0.4 + 1e-9
    assert len(part.drops) < len(full.drops)
    assert all(dr.y0 <= -0.4 for dr in part.drops)
    tiny = run(1 / 60, 0.0, dip=0.01, top=-0.98)
    assert not tiny.active()


def test_back_in_the_water_clears_the_lens_until_the_next_exit():
    w = run(1 / 60, 0.3)
    assert w.active()
    w.update(1 / 60, 1.0, 1.0)
    assert not w.active()
