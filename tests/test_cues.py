import dataclasses

import pytest

from fps.core.cues import CueSchedule
from fps.core.handling import Handling
from fps.core.weapon import Weapon
from fps.weapon_data import M4, AudioData, ReloadData

AUDIO = AudioData()


def run_schedule(sch, seconds, fps=60.0):
    out = []
    for _ in range(round(seconds * fps)):
        out += sch.update(1.0 / fps)
    return out


def start(key, speed=1.0):
    sch = CueSchedule()
    sch.start(AUDIO.cues[key], M4.clips[key], speed)
    return sch


def test_every_cue_lies_inside_its_clip_and_is_sorted():
    for key, cues in AUDIO.cues.items():
        clip = M4.clips[key]
        frames = [c.frame for c in cues]
        assert frames == sorted(frames), key
        assert all(clip.start <= f <= clip.end for f in frames), key


def test_mag_seat_cue_is_exactly_the_swap_frame():
    for key in ('reload', 'reload_empty'):
        seat = [c for c in AUDIO.cues[key] if c.sound == 'mag_seat']
        assert len(seat) == 1 and seat[0].frame == M4.clips[key].swap


def test_cues_fire_in_order_and_once():
    sch = start('reload')
    got = [name for name, _ in run_schedule(sch, M4.clips['reload'].duration + 0.5)]
    assert got == [c.sound for c in AUDIO.cues['reload']]
    assert run_schedule(sch, 1.0) == []


def test_cue_time_matches_frame_at_speed_one():
    sch = start('reload_empty')
    seat_frame = M4.clips['reload_empty'].swap
    t = 0.0
    while 'mag_seat' not in [n for n, _ in sch.update(1 / 120)]:
        t += 1 / 120
        assert t < 5
    assert t == pytest.approx((seat_frame - M4.clips['reload_empty'].start) / 30.0, abs=0.02)


@pytest.mark.parametrize('speed', [0.5, 1.5, 2.0])
def test_cue_times_divide_by_clip_speed(speed):
    sch = start('reload', speed)
    t, seat_t = 0.0, None
    while seat_t is None:
        t += 1 / 120
        if 'mag_seat' in [n for n, _ in sch.update(1 / 120)]:
            seat_t = t
        assert t < 10
    assert seat_t == pytest.approx(M4.clips['reload'].swap_time / speed, abs=0.02)


def test_cancel_drops_pending_cues_and_adds_one_settle_sound():
    sch = start('reload')
    fired = [n for n, _ in run_schedule(sch, 1.0)]                   # t = 1,0 s: chốt băng + băng rời; băng mới chưa vào
    assert fired == ['mag_release', 'mag_out']
    sch.cancel(AUDIO)
    assert sch.pending_names == [AUDIO.cancel_sound]
    later = [n for n, _ in run_schedule(sch, 3.0)]
    assert later == [AUDIO.cancel_sound]                             # không có mag_in / mag_seat / bolt_tick sau huỷ


def test_cancel_before_the_first_cue_is_silent():
    sch = start('reload')
    run_schedule(sch, 0.2)                                           # cue đầu ở 0,83 s
    sch.cancel(AUDIO)
    assert sch.pending_names == []
    assert run_schedule(sch, 3.0) == []


def test_flush_plays_the_rest_when_the_clip_finishes():
    sch = start('reload_empty')
    run_schedule(sch, 1.0)
    rest = [n for n, _ in sch.flush()]
    assert rest == [c.sound for c in AUDIO.cues['reload_empty']][2:]
    assert sch.flush() == []


def drive(h, sch, seconds, fps=60.0):
    """Mô phỏng Game.update: Handling.update(dt) -> các sự kiện vào lịch -> lịch.update(dt). Trả về [(giây, tên)] và giây của sự kiện swap."""
    heard, swap_t, t = [], None, 0.0
    dt = 1.0 / fps
    for _ in range(round(seconds * fps)):
        h.update(dt)
        t += dt
        for ev in h.drain():
            if ev[0] == 'start':
                sch.start(AUDIO.cues[ev[1]], M4.clips[ev[1]], ev[2])
            elif ev[0] == 'swap':
                swap_t = t
            elif ev[0] == 'done':
                heard += [(t, n) for n, _ in sch.flush()]
            elif ev[0] == 'cancel':
                sch.cancel(AUDIO)
        heard += [(t, n) for n, _ in sch.update(dt)]
    return heard, swap_t


@pytest.mark.parametrize('mag,key', [(12, 'reload'), (0, 'reload_empty')])
@pytest.mark.parametrize('speed', [1.0, 1.5])
def test_schedule_stays_in_step_with_handling(mag, key, speed):
    gun = dataclasses.replace(M4, reload=ReloadData(speed=speed))
    w = Weapon(gun)
    w.mag, w.reserve = mag, 150
    h = Handling(gun, w)
    sch = CueSchedule()
    h.start_reload()
    heard, swap_t = drive(h, sch, 6.0)
    assert [n for _, n in heard] == [c.sound for c in AUDIO.cues[key]]            # đủ số tiếng, đúng thứ tự
    seat_t = next(t for t, n in heard if n == 'mag_seat')
    assert abs(seat_t - swap_t) < 0.04                                            # tiếng băng vào chỗ trùng lúc đạn được cập nhật (<= 2 khung)


def test_cancelling_a_real_reload_stops_the_remaining_sounds():
    w = Weapon(M4)
    w.mag, w.reserve = 12, 150
    h = Handling(M4, w)
    sch = CueSchedule()
    h.start_reload()
    heard, _ = drive(h, sch, 1.2)
    assert [n for _, n in heard] == ['mag_release', 'mag_out']
    h.cancel()
    heard, _ = drive(h, sch, 4.0)
    assert [n for _, n in heard] == [AUDIO.cancel_sound]


def test_draw_has_two_quiet_cues():
    names = [c.sound for c in AUDIO.cues['draw']]
    assert names == ['draw_a', 'draw_b']
    assert all(c.volume < 1.0 for c in AUDIO.cues['draw'])
