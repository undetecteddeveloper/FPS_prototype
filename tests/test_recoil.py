import random

import pytest

from fps.core.recoil import CameraRecoil, GunKick
from fps.core.spring import burst_peak_ratio
from fps.weapon_data import GunKickData, RecoilData


def spray(rec, shots=30, fps=60, settle=0.0):
    """Fires `shots` rounds back to back (750 rounds/min), then keeps running for `settle` seconds.
    Returns (up, right) accumulated AFTER EACH FRAME, and the accumulation at the moment each shot fires."""
    dt = 1.0 / fps
    up = right = 0.0
    at_shot = []
    next_shot = 0.0
    fired = 0
    trace = []
    for i in range(round((shots * 0.08 + settle) * fps) + 1):
        t = i * dt
        while fired < shots and next_shot <= t + 1e-9:
            at_shot.append((up, right))
            rec.on_shot()
            fired += 1
            next_shot += 0.08
        du, dr = rec.step(dt)
        up += du
        right += dr
        trace.append((up, right))
    return trace, at_shot


FIXED = dict(up_noise=0.0, right_noise=0.0, right_walk=0.0, right_bias=0.1, camera_share=1.0)      # no randomness, every kick goes into the camera


def test_no_noise_no_recovery_total_is_shots_times_kick():
    d = RecoilData(recovery=0.0, **FIXED)
    trace, _ = spray(CameraRecoil(d), settle=1.0)
    assert trace[-1][0] == pytest.approx(30 * d.up, abs=1e-3)
    assert trace[-1][1] == pytest.approx(30 * d.right_bias, abs=1e-3)


def test_recoil_has_no_fixed_pattern():
    """Two bursts with different random seeds must follow clearly different paths: it cannot be memorised like CoD's 30-step pattern."""
    a = spray(CameraRecoil(RecoilData(camera_share=1.0, recovery=0.0), random.Random(1)), settle=0.2)[0][-1]
    b = spray(CameraRecoil(RecoilData(camera_share=1.0, recovery=0.0), random.Random(2)), settle=0.2)[0][-1]
    assert abs(a[1] - b[1]) > 0.3
    assert abs(a[0] - b[0]) > 0.05


def test_recoil_is_mostly_up():
    ups, rights = [], []
    for seed in range(30):
        last = spray(CameraRecoil(RecoilData(camera_share=1.0, recovery=0.0), random.Random(seed)), settle=0.2)[0][-1]
        ups.append(last[0])
        rights.append(last[1])
    assert sum(ups) / 30 == pytest.approx(30 * RecoilData().up, rel=0.05)
    assert abs(sum(rights) / 30) < 0.35 * sum(ups) / 30
    assert sum(rights) / 30 > 0                                             # the average trend leans right


def test_each_shot_stays_within_its_random_range():
    d = RecoilData(camera_share=1.0, recovery=0.0)
    rec = CameraRecoil(d, random.Random(7))
    seen = []
    for _ in range(300):
        rec.pending = [0.0, 0.0]
        rec.on_shot()
        seen.append(tuple(rec.pending))
        rec.step(1.0)
    ups = [u for u, _ in seen]
    assert min(ups) >= d.up - d.up_noise - 1e-9 and max(ups) <= d.up + d.up_noise + 1e-9
    assert max(ups) - min(ups) > d.up_noise                                 # really spread out
    limit = d.right_bias + d.right_noise + d.right_walk_max
    assert all(abs(r) <= limit + 1e-9 for _, r in seen)


def test_camera_share_splits_the_kick_between_camera_and_gun():
    d = RecoilData(recovery=0.0, up_noise=0.0, right_noise=0.0, right_walk=0.0, right_bias=0.2, camera_share=0.25)
    rec = CameraRecoil(d)
    gun_up, gun_right = rec.on_shot()
    assert rec.pending[0] == pytest.approx(d.up * 0.25) and rec.pending[1] == pytest.approx(0.2 * 0.25)
    assert gun_up == pytest.approx(d.up * 0.75) and gun_right == pytest.approx(0.2 * 0.75)


def test_posture_reduces_the_kick():
    d = RecoilData()
    rec = CameraRecoil(d)
    assert rec.posture_scale(0.0, False) == 1.0
    assert rec.posture_scale(1.0, False) == pytest.approx(d.ads_scale)
    assert rec.posture_scale(0.0, True) == pytest.approx(d.crouch_scale)
    assert rec.posture_scale(1.0, True) == pytest.approx(d.ads_scale * d.crouch_scale)


def test_horizontal_trend_restarts_after_a_pause_but_not_in_a_burst():
    d = RecoilData()
    rec = CameraRecoil(d, random.Random(3))
    for _ in range(6):
        rec.on_shot()
        rec.step(0.08)
    assert rec.walk != 0.0
    during = rec.walk
    rec.on_shot()                                                           # still inside the burst: only takes one more step
    assert abs(rec.walk - during) <= d.right_walk + 1e-9
    rec.step(d.burst_reset_time + 0.1)
    rec.on_shot()                                                           # paused long enough: starts again from 0, so it is only one step away from 0
    assert abs(rec.walk) <= d.right_walk + 1e-9


def test_recovery_gives_back_the_configured_fraction():
    for fraction in (0.0, 0.3, 0.5, 1.0):
        d = RecoilData(recovery=fraction, **FIXED)
        trace, _ = spray(CameraRecoil(d), settle=3.0)
        assert trace[-1][0] == pytest.approx(30 * d.up * (1 - fraction), abs=0.02), fraction


def test_recovery_only_starts_after_the_delay_and_is_gradual():
    d = RecoilData(recovery=0.3, **FIXED)
    rec = CameraRecoil(d)
    for _ in range(10):
        rec.on_shot()
        rec.step(0.08)
    total = 0.0
    for _ in range(3):                                                     # last shot was 0.08 s ago; another 30 ms = 110 ms < 120 ms
        total += rec.step(0.01)[0]
    assert total >= 0                                                      # no recovery yet: only the rest of the kick not yet applied
    got = []
    for _ in range(100):                                                   # then recovers gradually, with no jump
        got.append(rec.step(0.01)[0])
    assert min(got) < 0 and max(abs(g) for g in got) < 0.3


def test_firing_again_cancels_the_recovery():
    d = RecoilData(recovery=0.5, **FIXED)
    rec = CameraRecoil(d)
    for _ in range(5):
        rec.on_shot()
        rec.step(0.08)
    for _ in range(5):                                                     # 0.25 s: recovery has started but is not finished
        rec.step(0.05)
    assert rec.rec[0] > 0
    rec.on_shot()
    assert rec.rec == [0.0, 0.0]


@pytest.mark.parametrize('fps', [30, 60, 144, 500])
def test_total_recoil_does_not_depend_on_fps(fps):
    d = RecoilData(recovery=0.3, **FIXED)
    trace, _ = spray(CameraRecoil(d), fps=fps, settle=3.0)
    assert trace[-1][0] == pytest.approx(30 * d.up * 0.7, abs=0.03)


def test_gun_kick_returns_to_rest_and_peaks_near_the_setting():
    kick = GunKick(GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0), random.Random(1))
    kick.on_shot()
    zs, pitches = [], []
    for _ in range(120):
        kick.update(1 / 240)
        zs.append(kick.pose[2])
        pitches.append(kick.pose[3])
    d = GunKickData()
    assert min(zs) == pytest.approx(d.back_peak, rel=0.01)                 # pushed backward (negative z)
    assert max(pitches) == pytest.approx(d.peak[3], rel=0.01)
    for _ in range(240):
        kick.update(1 / 60)
    assert all(abs(v) < 1e-6 for v in kick.pose)


def test_gun_kick_is_smaller_and_faster_than_camera_recoil():
    d = GunKickData()
    assert abs(d.back_peak) < 0.05 and d.peak[3] < 3.0
    kick = GunKick(d, random.Random(1))
    kick.on_shot()
    t = 0.0
    while t < 2.0:
        kick.update(1 / 240)
        t += 1 / 240
        if max(abs(v) for v in kick.pose[:3]) < 0.05 * max(abs(d.back_peak), abs(d.peak[1])) and t > 0.05:
            break
    assert t < 0.8


# --- pushback (z) ---
def burst_z(shots, fps, ads=0.0, settle=1.0, rpm=750.0, seed=3, data=None):
    """Fires `shots` rounds back to back at `fps`, like Combat (each shot's age within the frame). Returns [(time, z)] per frame."""
    kick = GunKick(data or GunKickData(), random.Random(seed))
    interval, dt = 60.0 / rpm, 1.0 / fps
    out, fired = [], 0
    for i in range(1, round((shots * interval + settle) * fps) + 1):
        t1 = i * dt
        while fired < shots and fired * interval <= t1 + 1e-9:
            kick.on_shot(ads, max(0.0, t1 - fired * interval))
            fired += 1
        kick.update(dt)
        out.append((t1, kick.pose[2]))
    return out


NO_RANDOM = GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0)


def test_pushback_single_shot_peaks_at_back_peak_toward_the_eye():
    z = min(v for _, v in burst_z(1, 480, data=NO_RANDOM))
    assert z == pytest.approx(NO_RANDOM.back_peak, rel=0.03)
    assert z < 0                                       # negative = toward the eye
    assert 0.02 <= abs(z) <= 0.06                      # a few cm (not 0, nor half a metre if someone mistypes the unit)


def test_pushback_burst_builds_up_and_saturates():
    trace = burst_z(30, 480, data=NO_RANDOM)
    peak = min(v for _, v in trace)
    ratio = peak / NO_RANDOM.back_peak                 # the whole burst relative to one shot (linear system: independent of back_peak)
    assert 1.17 <= ratio <= 2.17                       # previously 5 cm, +-30% of 3 cm: same bounds, expressed as a ratio
    model = burst_peak_ratio(NO_RANDOM.back_omega, NO_RANDOM.back_zeta, 30, 60.0 / 750.0)
    assert ratio == pytest.approx(model, rel=0.02)     # matches the closed-form spring formula (superposition of 30 impulses 0.08 s apart), independent of Spring.step
    assert peak < NO_RANDOM.back_peak * 1.3            # clearly more than a single shot
    # saturation: 30 shots do not push back much farther than 15 shots (no unbounded growth)
    half = min(v for t, v in trace if t <= 15 * 0.08)
    assert peak >= half * 1.15
    # two back-to-back bursts do not exceed it either: the spring damps out, so the build-up is capped
    assert min(v for _, v in burst_z(90, 480, data=NO_RANDOM)) >= peak * 1.1


def test_pushback_settles_after_the_burst_in_measurable_time():
    trace = burst_z(30, 480, data=NO_RANDOM, settle=1.5)
    last = 30 * 0.08
    settled = next(t for t, v in trace if t > last and all(abs(w) < 0.001 for u, w in trace if u >= t))
    assert 0.1 < settled - last < 0.6
    assert all(abs(v) < 1e-5 for _, v in trace[-20:])


def test_pushback_in_ads_is_back_ads_scale_times_hip():
    s = NO_RANDOM.back_ads_scale
    assert s != 1.0                                   # if it equals 1, aim and hip are the same and this test is meaningless
    hip = min(v for _, v in burst_z(30, 480, ads=0.0, data=NO_RANDOM))
    ads = min(v for _, v in burst_z(30, 480, ads=1.0, data=NO_RANDOM))
    assert ads / hip == pytest.approx(s, abs=0.03)
    mid = min(v for _, v in burst_z(30, 480, ads=0.5, data=NO_RANDOM))
    assert mid / hip == pytest.approx(1.0 + (s - 1.0) * 0.5, abs=0.03)    # halfway: smoothstep(0.5) = 0.5 interpolation
    assert min(hip, ads) < mid < max(hip, ads)        # lies between the two ends, whether aiming pushes back less (s < 1) or more (s > 1) than hip fire


def test_pushback_does_not_touch_the_other_axes_or_the_vertical_kick():
    kick = GunKick(NO_RANDOM, random.Random(1))
    kick.on_shot()
    for _ in range(8):                                # 33 ms: near the peak of the old spring
        kick.update(1 / 240)
    x, y, z, pitch, yaw, roll = kick.pose
    assert (yaw, roll) == (0.0, 0.0)
    assert x == pytest.approx(NO_RANDOM.back_x_ratio * z, rel=1e-9) and x < 0      # pulled toward the screen centre: shifts LEFT on pushback (hip fire)
    assert y > 0 and pitch > 0 and z < 0              # y/pitch still come from the old spring
    only_old = GunKick(GunKickData(random=(0, 0, 0, 0, 0, 0), back_random=0.0, back_peak=0.0), random.Random(1))
    only_old.on_shot()
    for _ in range(8):
        only_old.update(1 / 240)
    assert only_old.pose[1] == pytest.approx(y) and only_old.pose[3] == pytest.approx(pitch) and only_old.pose[2] == 0.0


@pytest.mark.parametrize('fps', [30, 60, 144, 240, 1000])
def test_pushback_burst_peak_is_independent_of_fps(fps):
    ref = min(v for _, v in burst_z(30, 4000, data=NO_RANDOM))
    got = min(v for _, v in burst_z(30, fps, data=NO_RANDOM))
    assert got == pytest.approx(ref, rel=0.05)


@pytest.mark.parametrize('fps', [30, 60, 144, 1000])
def test_pushback_single_shot_curve_is_exact_at_any_dt(fps):
    """The spring solves exactly: one shot (firing mid-frame) gives the same curve at every dt, even a very large dt."""
    def at(f, t_end=0.4, t_shot=0.0537):
        kick = GunKick(NO_RANDOM, random.Random(1))
        dt = 1.0 / f
        frames = round(t_end * f)
        for i in range(1, frames + 1):
            t1 = i * dt
            if t1 - dt < t_shot <= t1:
                kick.on_shot(0.0, t1 - t_shot)
            kick.update(dt)
        return kick.pose[2]
    assert at(fps) == pytest.approx(at(20000), abs=1.5e-4)


def test_pushback_sideways_pull_is_off_when_aiming_down_sights():
    """Fully aimed: the sight line must stay on the view axis, so x is 0 alongside; at the hip, x = back_x_ratio * z."""
    for ads, expect_x in ((0.0, True), (1.0, False)):
        kick = GunKick(NO_RANDOM, random.Random(1))
        kick.on_shot(ads)
        worst = 0.0
        for _ in range(60):
            kick.update(1 / 240)
            worst = max(worst, abs(kick.pose[0]))
        assert (worst > 0.005) == expect_x
