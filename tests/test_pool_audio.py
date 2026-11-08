"""The footstep (user's boot-on-brick recording) and the room tone (user's 'Tranquil indoor swim, narrow'), 8/11/2026: built files, loudness, seamless loops, and the step landing on the bob."""
import math
import wave
from pathlib import Path

import numpy as np
import pytest

from fps.app import AUDIO_PRELOAD_BYTES
from fps.core.footsteps import Footsteps
from fps.core.headcam import footfall
from fps.weapon_data import AudioData

ROOT = Path(__file__).resolve().parent.parent
AUDIO = AudioData()
FOLEY = ROOT / AUDIO.folder
UNDER = ROOT / AUDIO.folder_under


def read(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, x.reshape(-1, ch)


def step_file() -> Path:
    files = sorted(FOLEY.glob(f'{AUDIO.sound_files["step_walk"]}_*.wav'))
    assert files
    return files[0]


# --- the step ---
def test_walking_and_running_use_the_boot_step_and_it_has_an_underwater_twin():
    assert AUDIO.sound_files['step_walk'] == AUDIO.sound_files['step_run'] == 'boot_step'
    f = step_file()
    assert (UNDER / f.name).exists()
    assert len(list(FOLEY.glob('boot_step_*.wav'))) == 1


def test_the_step_is_one_short_mono_impact_that_starts_on_its_first_sample():
    rate, x = read(step_file())
    m = np.abs(x[:, 0])
    assert x.shape[1] == 1 and 0.10 <= x.shape[0] / rate <= 0.50
    assert m.max() == pytest.approx(0.85, abs=0.01)
    assert int(np.argmax(m >= 0.10 * m.max())) / rate < 0.004                 # the heel strike starts at the very start: no silence before the impact
    assert int(np.argmax(m >= 0.40 * m.max())) / rate < 0.008                 # and is at full strength within 8 ms
    assert abs(x[-1, 0]) < 0.005                                              # no click at the end


def test_a_step_is_played_in_the_frame_the_bob_reaches_its_lowest_point_and_lands_in_time():
    """The sound plays in the frame where Sway.phase crosses the foot-plant phase; at that phase the gun's bob (sin 2 phase) and the head's footfall wave are both at their trough,
    and the file puts the impact on its first sample, so the heel strike is heard at the bottom of the bob (to one frame)."""
    for k in (0, 1):
        phase = AUDIO.step_bob_phase + k * math.pi
        assert math.sin(2.0 * phase) == pytest.approx(-1.0, abs=1e-3)
        assert footfall(phase, 1.0) == pytest.approx(-1.0, abs=1e-3)
        assert footfall(phase, 0.0) == pytest.approx(-1.0, abs=1e-3)
    fps, speed_phase = 60.0, 2.0 * math.pi * 1.7                              # a walk of 1.7 bob cycles per second
    steps = Footsteps(AUDIO)
    phase, last_hit, gaps = 0.0, None, []
    for frame in range(int(fps * 4)):
        phase = (phase + speed_phase / fps) % (2.0 * math.pi)
        for ev in steps.update(1.0 / fps, 0.05, True, 0.0, 0.0, False, False, bob_phase=phase):
            if ev.kind == 'step':
                crossing = (phase - AUDIO.step_bob_phase) % math.pi            # how far past the foot-plant point this frame's phase already is
                assert crossing <= speed_phase / fps + 1e-9                    # the step fires in the very frame of the crossing, never later
                gaps.append(frame / fps if last_hit is None else frame / fps - last_hit)
                last_hit = frame / fps
    assert len(gaps) >= 12
    assert np.std(gaps[1:]) < 1.0 / fps                                        # evenly spaced: two steps per bob cycle


# --- the room tone ---
@pytest.mark.parametrize('name', ['pool_ambience.wav', 'under_ambience.wav'])
def test_room_tones_are_seamless_stereo_loops_that_stay_in_memory(name):
    path = ROOT / 'assets' / 'sounds' / name
    rate, x = read(path)
    assert x.shape[1] == 2 and 11.0 <= x.shape[0] / rate <= 12.0
    assert path.stat().st_size < AUDIO_PRELOAD_BYTES
    for ch in range(2):
        seam = abs(x[0, ch] - x[-1, ch])
        assert seam < 6.0 * np.median(np.abs(np.diff(x[:, ch]))) + 1e-3, (name, ch)      # no click when the loop restarts


def test_the_room_tone_is_as_loud_as_the_one_it_replaced_and_is_the_narrow_recording():
    rate, x = read(ROOT / AUDIO.ambience_file)
    assert float(np.sqrt(np.mean(x * x))) == pytest.approx(0.085, rel=0.05)          # ambience_volume keeps its meaning
    assert np.abs(x).max() <= 0.9 + 1e-3
    src_rate, src = read(ROOT / 'assets' / 'sounds' / 'source' / 'pool' / 'Tranquil_indoor_swim_narrow-1794095744410.wav')
    assert rate == src_rate
    n = int(0.3 * rate)                                                              # past the crossfaded start: it IS the source, only louder (correlation, not equality)
    mid = int(2 * rate)
    assert np.corrcoef(x[mid:mid + n, 0], src[mid:mid + n, 0])[0, 1] > 0.999


def test_a_step_is_at_least_as_loud_as_the_steps_it_replaced():
    """The user found the first boot steps too quiet (8/11/2026): the file is short and sharp, so AudioData.volume_scale trims it up. Reference: the old ElevenLabs steps at step_volume 0.30 had an RMS over their
    first 100 ms of 0.18 (mean of the four) = 0.053 as played; the same measure for the boot step must not fall below it, and the loudest step (sprint, +10% random) must stay under full scale."""
    rate, x = read(step_file())
    body = float(np.sqrt(np.mean(x[:int(0.1 * rate), 0] ** 2)))
    for name in ('step_walk', 'step_run'):
        assert AUDIO.step_volume * AUDIO.volume_scale[name] * body >= 0.053, name
    loudest = AUDIO.step_volume * AUDIO.step_sprint_multiplier * (1.0 + AUDIO.step_volume_variation) * AUDIO.volume_scale['step_run']
    assert loudest <= 1.0                                                     # (Foley clamps at 1, but a clamped step would flatten)
