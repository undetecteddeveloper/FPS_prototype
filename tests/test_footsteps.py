import random

import pytest

from fps.core.footsteps import Footsteps, pick_variant
from fps.weapon_data import AudioData

A = AudioData()


def walk(meters, speed=4.5, fps=60.0, sprinting=False, crouching=False, seed=1, fs=None):
    fs = fs or Footsteps(A, random.Random(seed))
    dt = 1.0 / fps
    events, moved = [], 0.0
    while moved < meters:
        d = speed * dt
        moved += d
        events += fs.update(dt, d, True, 0.0, 0.0, sprinting, crouching)
    return events, fs


def kinds(events, kind):
    return [e for e in events if e.kind == kind]


@pytest.mark.parametrize('sprinting,crouching,speed,stride', [(False, False, 4.5, 0.75), (True, False, 6.8, 1.0), (False, True, 2.2, 0.5)])
def test_step_count_follows_distance_over_stride(sprinting, crouching, speed, stride):
    events, _ = walk(15.0, speed, sprinting=sprinting, crouching=crouching)
    assert abs(len(kinds(events, 'step')) - 15.0 / stride) <= 1.5


@pytest.mark.parametrize('fps', [30, 60, 144, 240])
def test_step_count_does_not_depend_on_fps(fps):
    events, _ = walk(15.0, fps=fps)
    assert abs(len(kinds(events, 'step')) - 20) <= 1.5


def test_step_count_does_not_depend_on_speed():
    slow, _ = walk(9.0, speed=2.0)
    fast, _ = walk(9.0, speed=4.5)
    assert abs(len(slow) - len(fast)) <= 1


def test_feet_alternate_and_variation_stays_in_range():
    events, _ = walk(30.0)
    steps = kinds(events, 'step')
    assert [e.foot for e in steps] == [i % 2 for i in range(len(steps))]
    pv, vv, fp = A.step_pitch_variation, A.step_volume_variation, A.foot_pitch
    for e in steps:
        assert 1 - pv - fp - 1e-9 <= e.pitch <= 1 + pv + fp + 1e-9
        assert A.step_volume * (1 - vv) - 1e-9 <= e.gain <= A.step_volume * (1 + vv) + 1e-9
    left = [e.pitch for e in steps if e.foot == 0]
    right = [e.pitch for e in steps if e.foot == 1]
    assert sum(right) / len(right) > sum(left) / len(left)             # chân phải cao hơn chân trái
    assert len({round(e.gain, 4) for e in steps}) > len(steps) // 2    # âm lượng thật sự ngẫu nhiên


def test_crouch_is_quiet_and_sprint_is_louder():
    walk_events, _ = walk(15.0)
    crouch_events, _ = walk(15.0, 2.2, crouching=True)
    run_events, _ = walk(15.0, 6.8, sprinting=True)

    def mean(ev):
        return sum(e.gain for e in ev) / len(ev)

    assert mean(crouch_events) == pytest.approx(mean(walk_events) * A.step_crouch_multiplier, rel=0.12)
    assert mean(run_events) > mean(walk_events)
    assert all(e.run for e in run_events) and not any(e.run for e in walk_events)


def test_silent_when_standing_still_and_after_stopping():
    fs = Footsteps(A, random.Random(2))
    walk(6.0, fs=fs)
    quiet = []
    for _ in range(120):
        quiet += fs.update(1 / 60, 0.0, True, 0.0, 0.0, False, False)
    assert quiet == []
    for _ in range(120):                                               # trượt nốt rất chậm sau khi thả phím cũng không tính là đi
        quiet += fs.update(1 / 60, 0.3 / 60, True, 0.0, 0.0, False, False)
    assert quiet == []


def test_first_step_after_standing_comes_early():
    fs = Footsteps(A, random.Random(3))
    fs.update(1 / 60, 0.0, True, 0.0, 0.0, False, False)
    events, moved = [], 0.0
    while not events:
        events += fs.update(1 / 60, 4.5 / 60, True, 0.0, 0.0, False, False)
        moved += 4.5 / 60
    assert moved < A.step_stride_walk * (1 - A.step_start_phase) + 0.1


def test_airborne_is_silent_and_jump_and_land_play_once():
    fs = Footsteps(A, random.Random(4))
    events = []
    events += fs.update(1 / 60, 0.0, False, 6.4, 0.0, False, False)     # khung rời đất, đang đi lên
    assert [e.kind for e in events] == ['jump']
    for _ in range(40):                                                 # trên không, vẫn đang đi ngang
        events += fs.update(1 / 60, 4.5 / 60, False, 1.0, 0.0, False, False)
    assert [e.kind for e in events] == ['jump']
    events += fs.update(1 / 60, 4.5 / 60, True, 0.0, 6.4, False, False)   # chạm đất
    assert [e.kind for e in events] == ['jump', 'land']
    assert events[-1].gain > A.step_volume * 1.2                        # to hơn bước chân


def test_land_volume_grows_with_fall_speed_and_small_falls_are_ignored():
    def land(speed):
        fs = Footsteps(A, random.Random(5))
        fs.update(1 / 60, 0.0, False, 1.0, 0.0, False, False)
        return fs.update(1 / 60, 0.0, True, 0.0, speed, False, False)

    assert land(1.0) == []
    gains = [land(v)[0].gain for v in (2.5, 4.0, 6.4, 9.0)]
    assert gains == sorted(gains) and gains[0] < gains[2]
    assert gains[-1] < A.land_volume * A.land_gain_range[1] * 1.11     # kẹp ở mức tối đa (+ ngẫu nhiên)


def test_pick_variant_never_repeats_and_covers_all():
    rng = random.Random(6)
    last, seen = None, set()
    for _ in range(500):
        v = pick_variant(rng, 5, last)
        assert 0 <= v < 5 and v != last
        seen.add(v)
        last = v
    assert seen == set(range(5))
    assert pick_variant(rng, 1, 0) == 0
