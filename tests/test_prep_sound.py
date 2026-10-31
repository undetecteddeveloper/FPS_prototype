import array
import math

import pytest

from tools.prep_sound import FADE, KEEP, PRE_ROLL, find_onset, trim

RATE = 48000


def stereo_shot(silence=0.048, burst=0.3, total=2.0, amp=20000):
    """Im lặng, rồi một tiếng nổ giảm dần, rồi im lặng; hai kênh giống nhau."""
    out = array.array('h')
    for i in range(round(total * RATE)):
        t = i / RATE
        x = 0
        if silence <= t < silence + burst:
            x = int(amp * math.exp(-(t - silence) * 12) * math.sin(2 * math.pi * 180 * t))
        out.extend((x, x))
    return out


def test_find_onset_reports_the_first_loud_frame():
    s = stereo_shot(silence=0.048)
    assert find_onset(s, 2) / RATE == pytest.approx(0.048, abs=0.004)
    assert find_onset(array.array('h', [0] * 100), 2) == 0                       # toàn im lặng: không có gì để cắt


def test_trim_removes_the_leading_silence_but_keeps_the_start_of_the_bang():
    s = stereo_shot(silence=0.048)
    out = trim(s, 2, RATE)
    first_loud = find_onset(out, 2) / RATE
    assert first_loud == pytest.approx(PRE_ROLL, abs=0.004)                      # nổ ngay ở đầu file (trễ ~3 ms thay vì 48 ms)
    assert max(abs(x) for x in out[:2 * round(0.012 * RATE)]) > 0.2 * 32768     # không cắt mất đầu tiếng nổ


def test_trim_length_and_fade_out():
    out = trim(stereo_shot(), 2, RATE)
    frames = len(out) // 2
    assert frames / RATE == pytest.approx(PRE_ROLL + KEEP, abs=0.001)
    assert out[-1] == 0 and out[-2] == 0                                         # kết thúc ở 0, không có tiếng "tách"
    tail = out[-2 * round(FADE * RATE):]
    peaks = [max(abs(x) for x in tail[i:i + 960]) for i in range(0, len(tail) - 960, 960)]
    assert peaks == sorted(peaks, reverse=True)                                  # mờ dần đơn điệu


def test_trim_keeps_channels_in_step():
    out = trim(stereo_shot(), 2, RATE)
    assert len(out) % 2 == 0
    assert all(out[i] == out[i + 1] for i in range(0, len(out), 2))              # hai kênh vẫn giống nhau (không lệch kênh)


def test_trim_short_sound_does_not_crash():
    s = array.array('h', [0, 0, 30000, 30000, 100, 100])
    out = trim(s, 2, RATE)
    assert len(out) > 0 and len(out) % 2 == 0
