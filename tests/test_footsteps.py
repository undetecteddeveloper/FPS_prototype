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
    assert sum(right) / len(right) > sum(left) / len(left)             # right foot is higher than left foot
    assert len({round(e.gain, 4) for e in steps}) > len(steps) // 2    # volume really is random


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
    for _ in range(120):                                               # still sliding very slowly after the keys are released does not count as walking
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
    events += fs.update(1 / 60, 0.0, False, 6.4, 0.0, False, False)     # the frame leaves the ground, moving up
    assert [e.kind for e in events] == ['jump']
    for _ in range(40):                                                 # in the air, still moving sideways
        events += fs.update(1 / 60, 4.5 / 60, False, 1.0, 0.0, False, False)
    assert [e.kind for e in events] == ['jump']
    events += fs.update(1 / 60, 4.5 / 60, True, 0.0, 6.4, False, False)   # touches down
    assert [e.kind for e in events] == ['jump', 'land']
    assert events[-1].gain > A.step_volume * 1.2                        # louder than a footstep


def test_land_volume_grows_with_fall_speed_and_small_falls_are_ignored():
    def land(speed):
        fs = Footsteps(A, random.Random(5))
        fs.update(1 / 60, 0.0, False, 1.0, 0.0, False, False)
        return fs.update(1 / 60, 0.0, True, 0.0, speed, False, False)

    assert land(1.0) == []
    gains = [land(v)[0].gain for v in (2.5, 4.0, 6.4, 9.0)]
    assert gains == sorted(gains) and gains[0] < gains[2]
    assert gains[-1] < A.land_volume * A.land_gain_range[1] * 1.11     # clamped at the maximum (+ randomness)


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


# --- footstep rhythm MATCHES the bob phase of Sway ---
import dataclasses  # noqa: E402
import math  # noqa: E402

from fps.core.movement import MoveState as S  # noqa: E402
from fps.core.sway import Sway, SwayInput  # noqa: E402
from fps.weapon_data import SwayData  # noqa: E402


def bob_walk(meters, state=S.WALK, speed=4.5, fps=60.0, seed=1, sway_data=None, hitch=None):
    """Walks `meters` metres with a real Sway; returns [(seconds, step event, bob phase, phase step per frame)]."""
    sd = sway_data or SwayData()
    sway, fs = Sway(sd), Footsteps(A, random.Random(seed))
    dt, t, moved, out = 1.0 / fps, 0.0, 0.0, []
    sprint = 1.0 if state is S.SPRINT else 0.0
    while moved < meters:
        step = dt if not (hitch and abs(t - hitch[0]) < dt / 2) else hitch[1]
        d = speed * step
        moved += d
        t += step
        sway.update(step, SwayInput(state, speed, 0.0, sprint))
        for ev in fs.update(step, d, True, 0.0, 0.0, state is S.SPRINT, state is S.CROUCH_WALK, sway.phase):
            rate = sd.bob_sprint_rate if state is S.SPRINT else sd.bob_rate
            out.append((t, ev, sway.phase, 2 * math.pi * speed * step * rate / sd.bob_stride))
    return out, sway


@pytest.mark.parametrize('state,speed,rate_name', [(S.WALK, 4.5, 'bob_rate'), (S.SPRINT, 6.8, 'bob_sprint_rate'), (S.CROUCH_WALK, 2.2, 'bob_rate')])
def test_bob_steps_follow_the_bob_cadence(state, speed, rate_name):
    sd = SwayData()
    out, _ = bob_walk(30.0, state, speed)
    expect = 2 * 30.0 * getattr(sd, rate_name) / sd.bob_stride        # two steps per bob cycle
    assert abs(len(out) - expect) <= 1.0


@pytest.mark.parametrize('fps', [30, 60, 144, 240])
def test_bob_steps_do_not_depend_on_fps(fps):
    sd = SwayData()
    out, _ = bob_walk(30.0, fps=fps)
    assert abs(len(out) - 2 * 30.0 * sd.bob_rate / sd.bob_stride) <= 1


def test_step_lands_on_the_lowest_point_of_the_bob():
    out, _ = bob_walk(30.0)
    for _, ev, phase, dphase in out:
        off = (phase - A.step_bob_phase) % math.pi
        assert off <= dphase + 1e-6 or math.pi - off <= 1e-6, (phase, dphase)       # just passed the mark, at most one frame earlier


def test_bob_feet_alternate():
    out, _ = bob_walk(30.0)
    feet = [ev.foot for _, ev, _, _ in out]
    assert len(feet) >= 6 and all(a != b for a, b in zip(feet, feet[1:]))


def test_bob_steps_never_pile_up_into_continuous_noise():
    """Old bug: stepping by distance at 0.75 m per step and 4.5 m/s gave 6 sounds/s, each 0.31 s long, so it buzzed continuously. Stepping by bob is much sparser."""
    for state, speed in ((S.WALK, 4.5), (S.SPRINT, 6.8), (S.CROUCH_WALK, 2.2)):
        out, _ = bob_walk(30.0, state, speed)
        gaps = [b[0] - a[0] for a, b in zip(out, out[1:])]
        assert min(gaps) > 0.33, (state, min(gaps))       # a footstep sound lasts at most 0.32 s (MAX_SECONDS), so they never overlap


def test_bob_steps_scale_with_bob_rate():
    base, _ = bob_walk(30.0)
    fast, _ = bob_walk(30.0, sway_data=dataclasses.replace(SwayData(), bob_rate=2 * SwayData().bob_rate))
    assert abs(len(fast) - 2 * len(base)) <= 2


def test_bob_silent_when_standing_and_airborne():
    out, sway = bob_walk(5.0)
    fs = Footsteps(A, random.Random(2))
    fs.update(1 / 60, 0.0, True, 0.0, 0.0, False, False, sway.phase)
    for _ in range(180):                                              # standing still for 3 s: bob phase is still, no steps
        sway.update(1 / 60, SwayInput(S.IDLE, 0.0, 0.0, 0.0))
        assert fs.update(1 / 60, 0.0, True, 0.0, 0.0, False, False, sway.phase) == []
    for _ in range(60):                                               # airborne: silent even while moving sideways
        assert [e for e in fs.update(1 / 60, 0.08, False, -1.0, 0.0, False, False, (sway.phase + 1.0) % (2 * math.pi)) if e.kind == 'step'] == []


def test_a_long_frame_does_not_burst():
    out, _ = bob_walk(40.0, S.SPRINT, 6.8, hitch=(1.0, 0.6))
    per_frame = {}
    for t, *_ in out:
        per_frame[round(t, 4)] = per_frame.get(round(t, 4), 0) + 1
    assert max(per_frame.values()) <= 2
