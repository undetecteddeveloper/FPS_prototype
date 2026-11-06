import dataclasses
import statistics

import pytest

from fps.core.shake import Shake, hash_unit, signed_pow, smooth_noise
from fps.weapon_data import M4

D = M4.shake
SHOT_INTERVAL = 60.0 / M4.rpm


def burst_trace(shots, fps, seed=None, ads=0.0, settle=0.0, data=D, interval=SHOT_INTERVAL, gun=False):
    """Fires `shots` rounds `interval` apart (default 750 rounds/min) at `fps`, in the exact order of Combat: on_shot(age) of the frame, then update(dt).
    Returns ([(end-of-frame time, heat, camera_pose | gun_pose)] per frame, Shake)."""
    sh = Shake(data, seed)
    dt = 1.0 / fps
    out = []
    fired = 0
    frames = round((shots * interval + settle) * fps) + 1
    for i in range(1, frames + 1):
        t1 = i * dt
        while fired < shots and fired * interval <= t1 + 1e-9:
            sh.on_shot(max(0.0, t1 - fired * interval))
            fired += 1
        sh.update(dt)
        out.append((t1, sh.heat, sh.gun_pose(ads) if gun else sh.camera_pose(ads)))
    return out, sh


def max_abs_per_axis(trace):
    return [max(abs(p[i]) for _, _, p in trace) for i in range(6)]


def single_shot_trace(n, seed=None, data=D, dt=1 / 480, seconds=0.5):
    """A single shot (shot number `n` of the random sequence) from rest; [(t, camera_pose)]."""
    sh = Shake(data, seed)
    sh.shot_count = n
    sh.on_shot()
    sh.update(0.0)
    out = []
    t = 0.0
    while t < seconds:
        sh.update(dt)
        t += dt
        out.append((t, sh.camera_pose()))
    return out


def test_noise_is_bounded_deterministic_and_smooth():
    vals = [smooth_noise(7, a, u / 50.0) for a in range(6) for u in range(-500, 500)]
    assert max(abs(v) for v in vals) <= 1.0 + 1e-12
    assert max(abs(v) for v in vals) > 0.9                      # uses the full range
    assert smooth_noise(7, 2, 3.37) == smooth_noise(7, 2, 3.37)
    assert smooth_noise(7, 2, 3.37) != smooth_noise(8, 2, 3.37)    # other seed -> other curve
    assert smooth_noise(7, 2, 3.37) != smooth_noise(7, 3, 3.37)    # other axis -> other curve
    # smooth: a 1/1000 step of the cell changes by at most ~0.01 (not white noise)
    steps = [abs(smooth_noise(7, 0, (k + 1) / 1000.0) - smooth_noise(7, 0, k / 1000.0)) for k in range(5000)]
    assert max(steps) < 0.01
    assert hash_unit(1, 0, -5) == hash_unit(1, 0, -5)


def test_signed_pow_keeps_sign_and_pushes_outward():
    assert signed_pow(0.0, 0.6) == 0.0
    assert signed_pow(-0.25, 0.5) == pytest.approx(-0.5)
    assert signed_pow(0.25, 0.5) == pytest.approx(0.5)
    assert signed_pow(1.0, 0.6) == 1.0 and signed_pow(-1.0, 0.6) == -1.0


# --- single shots: each shot is one clear kick ---
def test_single_shot_is_a_clear_short_kick():
    pitch_peaks, roll_peaks = [], []
    for n in range(30):
        tr = single_shot_trace(n)
        pitch = [p[3] for _, p in tr]
        roll_peaks.append(max(abs(p[5]) for _, p in tr))
        pitch_peaks.append(max(pitch))
        assert max(pitch) > 2 * abs(min(pitch)), n                 # pitch mainly kicks UP (small reverse bounce)
        assert max(pitch) >= 0.35, n                               # even the lightest shot is visible
        t_peak = next(t for t, p in tr if p[3] == max(pitch))
        assert t_peak < 0.06, n                                    # a fast kick, no drift
        quiet = [t for t, p in tr if max(abs(p[3]), abs(p[4]), abs(p[5])) > 0.02]
        assert max(quiet) < 0.35, n                                # fully off (below 0.02 deg) before the next shot in the single-tap rhythm
        assert max(abs(p[i]) for _, p in tr for i in range(3)) < 0.01      # displacement < 1 cm
    assert statistics.mean(pitch_peaks) >= 0.75                    # ~1 degree
    assert statistics.mean(roll_peaks) >= 0.9                      # roll is the most visible channel
    assert max(roll_peaks) >= 2.0                                  # some shots lean strongly
    assert max(pitch_peaks) >= 1.3


def test_shots_differ_in_strength_and_direction():
    sh = Shake(D)
    rows = [sh.shot_peak(n) for n in range(40)]
    strengths = [s for _, s, _ in rows]
    assert min(strengths) >= 1 - D.strength_var - 1e-9 and max(strengths) <= 1 + D.strength_var + 1e-9
    assert sum(s > 1.25 for s in strengths) >= 5 and sum(s < 0.75 for s in strengths) >= 5    # some shots clearly strong, some clearly weak
    assert all(b == 1.0 for _, _, b in rows)                       # cold: no heat multiplier
    peaks = [p for p, _, _ in rows]
    assert all(p[3] > 0 for p in peaks)                            # pitch always kicks up
    assert all(p[2] < 0 for p in peaks)                            # always pushes back
    for axis in (0, 1, 4, 5):                                      # x, y, yaw, roll: both signs
        assert sum(p[axis] > 0 for p in peaks) >= 10 and sum(p[axis] < 0 for p in peaks) >= 10, axis
    assert len({round(p[5], 6) for p in peaks}) == len(peaks)      # no two shots are identical
    # fully hot: the same shot is exactly 1 + heat_boost times stronger
    hot, _, boost = sh.shot_peak(3, heat=1.0)
    cold, _, _ = sh.shot_peak(3)
    assert boost == pytest.approx(1 + D.heat_boost)
    for a, b in zip(hot, cold):
        assert a == pytest.approx(b * (1 + D.heat_boost))


def test_on_shot_scale_scales_only_that_kick():
    data = dataclasses.replace(D, tremor_amp=(0.0,) * 6)          # compare only the kick (hand tremor follows heat, not scale)
    a = single_shot_trace(4, data=data)
    sh = Shake(data)
    sh.shot_count = 4
    sh.on_shot(0.0, scale=0.5)
    sh.update(0.0)
    assert sh.heat == pytest.approx(1 / D.heat_shots)             # heat does not follow scale
    for (_, pa) in a[:100]:
        sh.update(1 / 480)
        pb = sh.camera_pose()
        for x, y in zip(pa, pb):
            assert y == pytest.approx(0.5 * x, abs=1e-12)


# --- spraying ---
def test_heat_builds_during_spray_holds_and_cools():
    trace, sh = burst_trace(30, 240, settle=1.0)
    end = 29 * SHOT_INTERVAL                                       # last shot
    heat_at = lambda t: min(trace, key=lambda r: abs(r[0] - t))[1]   # noqa: E731
    assert heat_at(5 * SHOT_INTERVAL + 0.01) == pytest.approx(6 / D.heat_shots, abs=1e-9)
    assert heat_at(end + 0.01) == 1.0                              # 30 shots > heat_shots: fully hot
    # no cooling during the burst: heat only rises
    during = [h for t, h, _ in trace if t <= end + 1e-9]
    assert all(b >= a for a, b in zip(during, during[1:]))
    assert heat_at(end + D.heat_hold - 0.01) == 1.0                # still held
    assert heat_at(end + D.heat_hold + 1.0 / D.heat_cool + 0.01) == 0.0
    assert sh.heat == 0.0


def test_slow_taps_never_heat_up():
    trace, _ = burst_trace(10, 240, interval=0.3, settle=0.3)
    assert max(h for _, h, _ in trace) == pytest.approx(1 / D.heat_shots)


def test_spray_peak_is_about_twice_the_single_shots():
    """30 sprayed rounds (750 rounds/min) vs 30 single shots 1 s apart, with the SAME random sequence (same seed): pitch and roll peaks ~2x
    (mean over 10 seeds; the peak of the 30 single shots is already the strongest random shot, so they are compared on equal terms)."""
    rp, rr = [], []
    for seed in range(1, 11):
        single = max_abs_per_axis(burst_trace(30, 240, seed=seed, interval=1.0)[0])
        spray = max_abs_per_axis(burst_trace(30, 240, seed=seed)[0])
        rp.append(spray[3] / single[3])
        rr.append(spray[5] / single[5])
    assert 1.7 <= statistics.mean(rp) <= 2.3, rp
    assert 1.7 <= statistics.mean(rr) <= 2.3, rr
    assert min(rp + rr) >= 1.2                                     # every seed sprays clearly stronger


def test_spray_is_bounded_and_does_not_drift():
    trace, _ = burst_trace(60, 240, settle=0.5)                    # two back-to-back bursts
    peak = max_abs_per_axis(trace)
    assert peak[3] < 5.0 and peak[4] < 3.0 and peak[5] < 9.0       # strong but under control (degrees)
    assert max(peak[:3]) < 0.03                                    # displacement < 3 cm
    # no accumulated drift: the second burst's mean pitch is not much larger than the first's
    first = [p[3] for t, _, p in trace if 1.0 <= t < 2.4]
    second = [p[3] for t, _, p in trace if 3.4 <= t < 4.8]
    assert statistics.mean(second) < statistics.mean(first) * 1.3 + 0.1
    assert abs(statistics.mean(p[5] for _, _, p in trace)) < 0.5  # roll has a random sign: it does not lean toward one side


def test_shake_dies_after_spray_ends():
    trace, sh = burst_trace(30, 240, settle=1.0)
    last = 29 * SHOT_INTERVAL
    after_03 = [p for t, _, p in trace if t >= last + 0.3]
    after_05 = [p for t, _, p in trace if t >= last + 0.5]
    assert max(max(abs(v) for v in p[3:]) for p in after_03) < 0.25       # a little hand tremor still fading out
    assert max(max(abs(v) for v in p[3:]) for p in after_05) < 0.01       # ~0 after 0.5 s
    assert max(max(abs(v) for v in p[:3]) for p in after_05) < 1e-4
    assert sh.heat == 0.0 and not sh.active
    assert trace[-1][2] == (0.0,) * 6


# --- FPS independent ---
@pytest.mark.parametrize('gun', [False, True])
@pytest.mark.parametrize('fps', [30, 60, 144])
def test_pose_independent_of_frame_rate(fps, gun):
    """The same 30-round burst at 240 FPS and at `fps`: at the common times the camera pose (and gun pose) is the same (shots have an in-frame age,
    the spring is solved exactly, the gun's delayed impulse lands at the right time, hand tremor follows only the clock)."""
    ref, _ = burst_trace(30, 240, settle=0.6, gun=gun)
    got, _ = burst_trace(30, fps, settle=0.6, gun=gun)
    ref_by_t = {round(t, 6): (h, p) for t, h, p in ref}
    n = 0
    for t, h, p in got:
        key = round(t, 6)
        if key not in ref_by_t:
            continue
        rh, rp = ref_by_t[key]
        n += 1
        assert h == pytest.approx(rh, abs=1e-9)
        for a, b in zip(p, rp):
            assert a == pytest.approx(b, abs=1e-6)
    assert n > 30


def test_irregular_frames_match_fixed_frames():
    """Mixed long and short frames (like a stuttering machine) give the same result as even frames."""
    times = [0.0137 + k * SHOT_INTERVAL for k in range(20)]

    def run(dts):
        sh = Shake(D)
        t1 = 0.0
        for dt in dts:
            t0, t1 = t1, t1 + dt
            for ts in times:
                if t0 < ts <= t1:
                    sh.on_shot(t1 - ts)
            sh.update(dt)
        return sh
    irregular = [(1 / 30, 1 / 200, 1 / 61, 0.045, 1 / 144)[i % 5] for i in range(400)]
    total = sum(irregular)
    ref = run([total / 4000] * 4000)
    got = run(irregular)
    assert got.t == pytest.approx(ref.t)
    for a, b in zip(got.camera_pose(), ref.camera_pose()):
        assert a == pytest.approx(b, abs=1e-6)


def test_same_seed_repeats_and_other_seed_differs():
    a, _ = burst_trace(10, 120, seed=5)
    b, _ = burst_trace(10, 120, seed=5)
    c, _ = burst_trace(10, 120, seed=6)
    assert [p for _, _, p in a] == [p for _, _, p in b]
    assert [p for _, _, p in a] != [p for _, _, p in c]


# --- scale, aim, gun ---
@pytest.mark.parametrize('fps', [60, 240])
def test_fire_scale_multiplies_every_fire_amplitude_by_exactly_the_ratio(fps):
    """fire_scale 1.5 vs 1.0: every axis of the camera and of the gun is exactly 1.5x larger on every frame (kick and hand tremor)."""
    base = dataclasses.replace(D, fire_scale=1.0)
    big = dataclasses.replace(D, fire_scale=1.5)
    for gun in (False, True):
        a, _ = burst_trace(30, fps, data=base, settle=0.3, gun=gun)
        b, _ = burst_trace(30, fps, data=big, settle=0.3, gun=gun)
        for (_, _, pa), (_, _, pb) in zip(a, b):
            for x, y in zip(pa, pb):
                assert y == pytest.approx(x * 1.5, abs=1e-12)


def test_fire_scale_does_not_touch_reload_beats():
    base = dataclasses.replace(D, fire_scale=1.0)
    big = dataclasses.replace(D, fire_scale=2.0)
    for kind in D.beat_peaks:
        poses = []
        for data in (base, big):
            sh = Shake(data)
            sh.on_beat(kind)
            sh.update(0.0)
            row = []
            for _ in range(40):
                sh.update(1 / 240)
                row.append(sh.camera_pose())
            poses.append(row)
        assert poses[0] == poses[1]


def test_ads_reduces_the_shake_to_the_configured_fraction():
    hip, _ = burst_trace(20, 120)
    ads, _ = burst_trace(20, 120, ads=1.0)
    for (_, _, h), (_, _, a) in zip(hip, ads):
        for x, y in zip(h, a):
            assert y == pytest.approx(x * D.ads_multiplier, abs=1e-12)
    half, _ = burst_trace(20, 120, ads=0.5)
    mid = D.ads_multiplier + (1 - D.ads_multiplier) * 0.5          # smoothstep(0.5) = 0.5
    peak_hip = max(abs(p[5]) for _, _, p in hip)
    assert max(abs(p[5]) for _, _, p in half) == pytest.approx(peak_hip * mid, rel=1e-6)
    assert max(abs(p[5]) for _, _, p in ads) < peak_hip


def test_disabled_shake_is_silent():
    sh = Shake(D)
    sh.enabled = False
    sh.on_shot()
    sh.on_beat('seat')
    sh.watch_reload('reload', 100.0)
    sh.update(0.016)
    assert sh.camera_pose() == (0.0,) * 6 and sh.gun_pose() == (0.0,) * 6 and not sh.active


def test_gun_pose_opposes_world_follows_partially_and_lags():
    cam, _ = burst_trace(1, 1000, settle=0.4)
    gun, _ = burst_trace(1, 1000, settle=0.4, gun=True)
    cam_pitch = [p[3] for _, _, p in cam]
    gun_pitch = [p[3] for _, _, p in gun]
    assert min(gun_pitch) == pytest.approx(-max(cam_pitch) * D.gun_follow, rel=1e-6)    # sign flipped, smaller (one shot: no hand tremor)
    t_cam = cam[cam_pitch.index(max(cam_pitch))][0]
    t_gun = gun[gun_pitch.index(min(gun_pitch))][0]
    assert t_gun - t_cam == pytest.approx(D.gun_delay, abs=2e-3)      # lags by exactly gun_delay
    # the whole burst without lag: gun = -gun_follow x camera on every frame (kick, hand tremor and beat impulse)
    no_lag = dataclasses.replace(D, gun_delay=0.0)
    sh = Shake(no_lag)
    for i in range(240):
        if i % 10 == 0:
            sh.on_shot(0.003)
        if i == 120:
            sh.on_beat('seat')
        sh.update(1 / 120)
        for c, g in zip(sh.camera_pose(0.3), sh.gun_pose(0.3)):
            assert g == pytest.approx(-c * D.gun_follow, abs=1e-12)


def test_reset_clears_everything():
    _, sh = burst_trace(10, 120)
    assert sh.active and sh.heat > 0 and sh.amplitude > 0
    sh.reset()
    assert not sh.active and sh.heat == 0.0 and sh.trauma == 0.0
    assert sh.camera_pose() == (0.0,) * 6 and sh.gun_pose() == (0.0,) * 6


# --- reloading ---
def feed_reload(sh, key, fps, speed=1.0, cancel_at=None):
    """Runs clip `key` from its first frame at `fps`, as in Combat (watch_reload then update). Returns the beats fired in this run: [(clock, kind)]."""
    clip = M4.clips[key]
    dt = 1.0 / fps
    t = 0.0
    start_count = sh.beat_count
    while True:
        t += dt * speed
        frame = min(clip.start + t * 30.0, clip.end)
        if cancel_at is not None and frame >= cancel_at:
            sh.watch_reload(None, None)
            sh.update(dt)
            break
        sh.watch_reload(key, frame, 30.0 * speed)
        sh.update(dt)
        if frame >= clip.end:
            sh.watch_reload(None, None)
            break
    n = sh.beat_count - start_count
    return list(sh.beat_log)[len(sh.beat_log) - n:] if n else []


@pytest.mark.parametrize('fps', [30, 60, 144, 1000])
@pytest.mark.parametrize('speed', [1.0, 1.5])
def test_reload_beats_fire_once_each_at_their_frames(fps, speed):
    for key, beats in D.reload_beats.items():
        sh = Shake(D)
        t0 = sh.t
        fired = feed_reload(sh, key, fps, speed)
        assert [k for _, k in fired] == [kind for _, kind in beats]
        clip = M4.clips[key]
        for (clock, _), (f_beat, _) in zip(fired, beats):
            # real clock at firing = (beat frame - first frame) / 30 / speed, correct at every FPS thanks to the in-frame age
            assert clock - t0 == pytest.approx((f_beat - clip.start) / 30.0 / speed, abs=1.5e-3 + 1e-3 / fps)


def test_reload_beats_match_clip_swap_frame():
    for key in ('reload', 'reload_empty'):
        clip = M4.clips[key]
        seat = [f for f, kind in D.reload_beats[key] if kind == 'seat']
        assert seat == [clip.swap]                       # the new magazine seats exactly on Handling's swap frame
        assert all(clip.start < f < clip.end for f, _ in D.reload_beats[key])
        assert [f for f, _ in D.reload_beats[key]] == sorted(f for f, _ in D.reload_beats[key])


def test_cancel_drops_beats_not_reached():
    sh = Shake(D)
    fired = feed_reload(sh, 'reload_empty', 60, cancel_at=180.0)      # after the 172 mark, before the bolt at 190
    assert [k for _, k in fired] == ['mag_out', 'seat']
    sh.update(1.0)
    assert sh.beat_count == 2                                         # the bolt does not fire late after the cancel
    fired2 = feed_reload(sh, 'reload_empty', 60)                      # reloading from the start gives all the marks again
    assert [k for _, k in fired2] == ['mag_out', 'seat', 'bolt']


def test_no_beats_while_idle_or_during_draw():
    sh = Shake(D)
    for f in range(0, 400, 7):
        sh.watch_reload(None, None)
        sh.watch_reload('draw', 269 + f / 10.0)
        sh.update(0.016)
    assert sh.beat_count == 0


def test_reload_beat_is_short_and_light():
    for kind in D.beat_peaks:
        sh = Shake(D)
        sh.on_beat(kind)
        sh.update(0.0)
        peak = 0.0
        quiet_after = None
        dt = 1 / 240
        t = 0.0
        while t < 0.6:
            sh.update(dt)
            t += dt
            pose = sh.camera_pose()
            m = max(abs(pose[3]), abs(pose[4]), abs(pose[5]))
            peak = max(peak, m)
            if quiet_after is None and m < 0.02 and t > 0.05:
                quiet_after = t
        assert 0.05 <= peak <= 0.3, kind                 # light (degrees)
        assert quiet_after is not None and quiet_after < 0.4, kind       # dies out quickly, does not shake all the time
        assert sh.heat == 0.0                            # reload marks do not heat the spray burst


@pytest.mark.parametrize('fps', [30, 60, 240])
def test_beat_spring_independent_of_fps(fps):
    def run(f):
        sh = Shake(D)
        dt = 1.0 / f
        for i in range(1, round(0.6 * f) + 1):
            if i == round(0.3 * f):
                sh.on_beat('bolt', 0.0)
            sh.update(dt)
        return sh
    ref, got = run(1000), run(fps)
    for a, b in zip(got.camera_pose(), ref.camera_pose()):
        assert a == pytest.approx(b, abs=1e-9)
