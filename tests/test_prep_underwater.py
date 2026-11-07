"""G12: the underwater sounds (tools/build/prep_underwater.py): a real low-pass, loudness, no clipping, an exactly repeating loop, deterministic output, and a muffled twin for every foley sound."""
import numpy as np
import pytest

from tools.build import prep_underwater as pu

RATE = 44100


def tone(hz, seconds=1.0):
    t = np.arange(int(seconds * RATE)) / RATE
    return np.sin(2 * np.pi * hz * t)[:, None]


def gain_db(hz, circular=True):
    x = tone(hz)
    y = pu.lowpass(x, RATE, pu.CUTOFF, circular=circular)
    mid = slice(RATE // 4, 3 * RATE // 4)                                   # away from the ends
    return 20 * np.log10(pu.rms(y[mid]) / pu.rms(x[mid]))


def test_lowpass_passes_the_lows_and_kills_the_highs():
    assert gain_db(100) == pytest.approx(0.0, abs=0.3)
    assert gain_db(pu.CUTOFF) == pytest.approx(-3.0, abs=0.3)                # the corner
    assert gain_db(800) < -23                                                 # 24 dB per octave
    assert gain_db(4000) < -60


def test_lowpass_is_zero_phase_the_click_keeps_its_place():
    x = np.zeros((RATE // 2, 1))
    x[RATE // 4, 0] = 1.0
    y = pu.lowpass(x, RATE, pu.CUTOFF)
    assert abs(int(np.argmax(np.abs(y[:, 0]))) - RATE // 4) <= 1


def test_muffle_is_dull_quieter_than_the_original_and_never_clips():
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, (RATE // 3, 1)) * np.exp(-np.arange(RATE // 3) / 2000.0)[:, None]      # a bright decaying noise burst (a metal click)
    y = pu.muffle(x, RATE)
    assert y.shape == x.shape
    assert pu.centroid(y, RATE) < 600 < pu.centroid(x, RATE)
    assert np.max(np.abs(y)) <= pu.PEAK_MAX + 1e-9
    assert abs(y[0, 0]) < 0.01 and abs(y[-1, 0]) < 0.01                       # starts and ends at zero: no pop
    assert pu.rms(y) == pytest.approx(pu.LEVEL * pu.rms(x), rel=0.1)          # (fades take a little)


def test_muffle_limits_a_loud_sound():
    x = tone(60, 0.3) * 0.99
    y = pu.muffle(x, RATE, level=3.0)
    assert np.max(np.abs(y)) <= pu.PEAK_MAX + 1e-9


def test_periodic_noise_repeats_exactly_and_is_deterministic():
    n = RATE
    a = pu.periodic_noise(n, RATE, pu.NOISE_CUT, np.random.default_rng(5))
    b = pu.periodic_noise(n, RATE, pu.NOISE_CUT, np.random.default_rng(5))
    assert np.array_equal(a, b)
    assert abs(a[-1] - a[0]) < 5 * np.median(np.abs(np.diff(a)))             # the seam is like any other place
    assert pu.rms(a[:, None]) == pytest.approx(1.0)


def synthetic_room(seconds=3.0):
    """A stereo 'room tone' that is exactly periodic in `seconds` (whole cycles), bright and low."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    left = 0.2 * np.sin(2 * np.pi * 2 / seconds * t) + 0.1 * np.sin(2 * np.pi * 900 / 1.0 * t)
    right = 0.2 * np.sin(2 * np.pi * 3 / seconds * t) + 0.1 * np.sin(2 * np.pi * 1500 / 1.0 * t)
    return np.stack([left, right], axis=1)


def test_underwater_tone_is_a_seamless_loop_and_dull():
    room = synthetic_room()
    y = pu.build_ambience(room, RATE)
    assert y.shape == room.shape
    for ch in range(2):
        seam = abs(y[0, ch] - y[-1, ch])
        typical = np.median(np.abs(np.diff(y[:, ch])))
        assert seam < 6 * typical + 1e-3, ch                                  # no click when the loop restarts (the bubbles never straddle the seam)
    assert pu.centroid(y, RATE) < 400 < pu.centroid(room, RATE)
    assert np.max(np.abs(y)) <= pu.PEAK_MAX + 1e-9
    assert pu.rms(y) == pytest.approx(pu.AMB_LEVEL * pu.rms(room), rel=0.05)


def test_underwater_tone_is_deterministic_and_bubbles_can_be_left_out():
    room = synthetic_room(2.0)
    a, b = pu.build_ambience(room, RATE), pu.build_ambience(room, RATE)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, pu.build_ambience(room, RATE, bubbles=0))


def test_every_foley_sound_has_a_muffled_twin_of_the_same_length():
    sources = sorted(pu.FOLEY.glob('*.wav'))
    assert sources
    for src in sources:
        twin = pu.FOLEY_OUT / src.name
        assert twin.exists(), f'chạy tools\\build\\prep_underwater.py --apply: thiếu {twin.name}'
        r0, x = pu.read_wav(src)
        r1, y = pu.read_wav(twin)
        assert (r0, x.shape) == (r1, y.shape), src.name
        assert pu.centroid(y, r1) < 800, src.name


def test_the_built_underwater_tone_loops_and_is_dull():
    r0, room = pu.read_wav(pu.AMBIENCE)
    r1, y = pu.read_wav(pu.AMBIENCE_OUT)
    assert (r0, room.shape) == (r1, y.shape)
    assert pu.centroid(y, r1) < 450
    for ch in range(y.shape[1]):
        assert abs(y[0, ch] - y[-1, ch]) < 6 * np.median(np.abs(np.diff(y[:, ch])))
