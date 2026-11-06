"""Idle breathing sound: one breath per breath cycle of the sway, on the same clock as the gun's bob."""
import array
import math
import wave
from pathlib import Path

import pytest

from fps.core.breath import SWAY_BREATH_OFFSET, Breathing
from fps.core.sway import Sway, SwayInput
from fps.core.movement import MoveState as S
from fps.weapon_data import M4, AudioData

ROOT = Path(__file__).resolve().parent.parent
AUDIO, SWAY = AudioData(), M4.sway
PERIOD = 1.0 / SWAY.breath_freq


def run(seconds, fps=60, bob=0.0, ads=0.0, grounded=True, breathing=None):
    b = breathing or Breathing(AUDIO, SWAY)
    out, t = [], 0.0
    for _ in range(int(seconds * fps)):
        t += 1.0 / fps
        v = b.update(t, bob, ads, grounded)
        if v is not None:
            out.append((t, v))
    return out


def test_one_breath_per_sway_cycle():
    out = run(30.0)
    assert abs(len(out) - 30.0 / PERIOD) <= 1
    gaps = [b[0] - a[0] for a, b in zip(out, out[1:])]
    assert all(g == pytest.approx(PERIOD, abs=0.03) for g in gaps)


@pytest.mark.parametrize('fps', [30, 60, 144, 240])
def test_breath_cadence_does_not_depend_on_fps(fps):
    out = run(30.0, fps)
    assert abs(len(out) - 30.0 / PERIOD) <= 1


def test_breath_starts_when_the_gun_starts_rising():
    """Breathing starts at vertical phase sin(2w + 0.6) = 0 while rising: the gun starts to rise."""
    out = run(12.0, 240)
    for t, _ in out:
        arg = 2 * math.pi * SWAY.breath_freq * t * 2 + SWAY_BREATH_OFFSET
        assert abs((arg + math.pi) % (2 * math.pi) - math.pi) < 0.2


def test_no_breath_in_the_first_cycle_mid_way():
    """The first breath is not played right in the middle of a cycle."""
    assert run(0.5) == []


def test_silent_when_moving_airborne():
    assert run(20.0, bob=1.0) == []
    assert run(20.0, grounded=False) == []


def test_breath_quieter_when_aiming_and_when_moving_a_little():
    hip = run(10.0)[-1][1]
    ads = run(10.0, ads=1.0)[-1][1]
    assert ads == pytest.approx(hip * AUDIO.breath_ads_scale)
    assert run(10.0, bob=0.2)[-1][1] < hip


def test_breath_clock_is_the_sways():
    """The breath clock is taken from Sway.clock: with a real Sway running, the breath count matches the cycle."""
    sway, b, n = Sway(SWAY), Breathing(AUDIO, SWAY), 0
    for _ in range(60 * 30):
        sway.update(1 / 60, SwayInput(S.IDLE, 0.0, 0.0, 0.0))
        n += b.update(sway.clock, sway.bob_amount, 0.0, True) is not None
    assert abs(n - 30.0 / PERIOD) <= 1


def test_breath_sound_files_fit_one_sway_cycle():
    """Each breath file lasts about one cycle (the game stretches it by 0.85-1.2x to fit), with no click at either end."""
    files = sorted((ROOT / AUDIO.folder).glob('el_breath_*.wav'))
    assert len(files) >= 2
    for f in files:
        with wave.open(str(f), 'rb') as w:
            assert w.getframerate() == 44100 and w.getnchannels() == 1
            x = array.array('h', w.readframes(w.getnframes()))
        seconds = len(x) / 44100
        assert 0.85 <= seconds * SWAY.breath_freq <= 1.2, (f.name, seconds)
        assert abs(x[0]) < 600 and abs(x[-1]) < 600
        assert max(abs(v) for v in x) / 32768 > 0.3
