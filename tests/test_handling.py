import dataclasses

import pytest

from fps.core.handling import Handling, Phase
from fps.core.weapon import Weapon
from fps.weapon_data import M4, ReloadData


def make(mag=30, reserve=150, **reload_kw):
    gun = dataclasses.replace(M4, reload=ReloadData(**reload_kw))
    w = Weapon(gun)
    w.mag, w.reserve = mag, reserve
    return Handling(gun, w), w


def run(h, seconds, fps=60.0):
    for _ in range(round(seconds * fps)):
        h.update(1.0 / fps)


def test_reload_changes_ammo_only_at_the_swap_frame():
    h, w = make(mag=12)
    assert h.start_reload()
    run(h, M4.clips['reload'].swap_time - 0.1)
    assert (w.mag, w.reserve) == (12, 150)                  # the new magazine has not seated yet
    run(h, 0.2)
    assert (w.mag, w.reserve) == (30, 132)                  # takes exactly 18 rounds
    assert h.busy                                           # but the clip keeps playing (the hand still releasing the magazine, pulling the bolt)


def test_reload_finishes_after_the_clip_duration():
    h, w = make(mag=12)
    h.start_reload()
    run(h, M4.clips['reload'].duration - 0.05)
    assert h.phase is Phase.RELOAD and not h.can_fire
    run(h, 0.1)
    assert h.phase is Phase.READY and h.can_fire


def test_empty_magazine_uses_the_empty_clip_and_it_is_longer():
    h, w = make(mag=0)
    h.start_reload()
    assert h.key == 'reload_empty'
    h2, _ = make(mag=5)
    h2.start_reload()
    assert h2.key == 'reload'
    assert M4.clips['reload_empty'].duration > M4.clips['reload'].duration
    assert M4.clips['reload'].duration == pytest.approx(3.63, abs=0.05)
    assert M4.clips['reload_empty'].duration == pytest.approx(3.77, abs=0.05)


def test_total_rounds_are_conserved():
    for mag, reserve in ((0, 150), (1, 150), (17, 150), (29, 3), (0, 7), (0, 30), (10, 20)):
        h, w = make(mag=mag, reserve=reserve)
        total = w.mag + w.reserve
        h.start_reload()
        run(h, 5.0)
        assert w.mag + w.reserve == total
        assert w.mag == min(30, total)


def test_partial_reload_when_reserve_is_short():
    h, w = make(mag=0, reserve=5)
    h.start_reload()
    run(h, 5.0)
    assert (w.mag, w.reserve) == (5, 0)


@pytest.mark.parametrize('mag, reserve', [(30, 150), (10, 0), (0, 0)])
def test_no_reload_when_full_or_no_reserve(mag, reserve):
    h, w = make(mag=mag, reserve=reserve)
    assert not h.start_reload()
    assert h.phase is Phase.READY and h.drain() == []


def test_cannot_start_a_reload_while_busy():
    h, w = make(mag=10)
    assert h.start_reload()
    assert not h.start_reload()
    assert not h.start_draw()
    h2, _ = make()
    h2.start_draw()
    assert not h2.start_reload()                            # cannot reload while the gun is being drawn


def test_cancel_before_swap_keeps_ammo_untouched():
    h, w = make(mag=12)
    h.start_reload()
    run(h, 1.0)
    assert h.cancel()
    assert h.phase is Phase.READY
    assert (w.mag, w.reserve) == (12, 150)
    run(h, 5.0)
    assert (w.mag, w.reserve) == (12, 150)                  # after the cancel, it no longer reloads by itself


def test_cancel_after_swap_keeps_the_new_magazine():
    h, w = make(mag=12)
    h.start_reload()
    run(h, M4.clips['reload'].swap_time + 0.3)
    assert h.cancel()
    assert (w.mag, w.reserve) == (30, 132)


def test_cancel_event_carries_the_frame_it_stopped_at():
    h, w = make(mag=12)
    h.start_reload()
    run(h, 1.0)
    h.drain()
    h.cancel()
    (name, key, frame), = h.drain()
    assert (name, key) == ('cancel', 'reload')
    assert frame == pytest.approx(M4.clips['reload'].start + 30.0, abs=1.0)


def test_draw_cannot_be_cancelled_and_blocks_fire_then_releases():
    h, w = make()
    h.start_draw()
    assert not h.can_fire and not h.cancel()
    run(h, M4.clips['draw'].duration - 0.05)
    assert not h.can_fire
    run(h, 0.1)
    assert h.can_fire
    assert (w.mag, w.reserve) == (30, 150)                  # drawing the gun does not touch the ammo


def test_speed_scales_the_time_but_not_the_swap_frame():
    h, w = make(mag=12, speed=2.0)
    h.start_reload()
    half = M4.clips['reload'].swap_time / 2
    run(h, half - 0.05)
    assert w.mag == 12
    run(h, 0.1)
    assert w.mag == 30                                      # speed x2: the magazine is swapped after half the time
    clip = M4.clips['reload']
    assert h.remaining == pytest.approx((clip.duration - clip.swap_time) / 2 - 0.05, abs=0.02)   # has really run half + 0.05 s


def test_frame_follows_the_clip_and_stays_in_range():
    h, w = make(mag=12)
    h.start_reload()
    clip = M4.clips['reload']
    assert h.frame == clip.start
    run(h, 1.0)
    assert h.frame == pytest.approx(clip.start + 30.0, abs=0.6)
    h.update(0.5)
    assert clip.start < h.frame <= clip.end
    run(h, 5.0)
    assert h.frame is None                                  # when finished, there is no frame any more


def test_hitch_frame_jumping_over_the_swap_still_swaps_once():
    h, w = make(mag=12)
    h.start_reload()
    h.update(0.2)
    h.update(3.0)                                           # one frame hangs for 3 s: it passes the magazine-swap mark
    assert (w.mag, w.reserve) == (30, 132)
    events = [e[0] for e in h.drain()]
    assert events.count('swap') == 1


def test_events_come_in_order():
    h, w = make(mag=12)
    h.start_reload()
    run(h, 5.0)
    assert [e[0] for e in h.drain()] == ['start', 'swap', 'done']
    assert h.drain() == []


def test_progress_and_remaining():
    h, w = make(mag=12)
    assert h.progress == 0.0 and h.remaining == 0.0
    h.start_reload()
    run(h, 1.8)
    assert h.progress == pytest.approx(0.5, abs=0.02)
    assert h.remaining == pytest.approx(M4.clips['reload'].duration - 1.8, abs=0.05)
