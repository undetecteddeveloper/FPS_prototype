"""Sounds generated with ElevenLabs (tools/build/prep_elevenlabs.py): all files present, correct format, impact right at the start of each file, no distortion; plus the maths of the hit sound."""
import math
import shutil
import subprocess
import sys
import wave
import array
from pathlib import Path

import pytest

from fps.core.cues import impact_sound
from fps.weapon_data import M4, AudioData

ROOT = Path(__file__).resolve().parent.parent
AUDIO = AudioData()
GROUPS = sorted(set(v for v in AUDIO.sound_files.values() if v.startswith('el_')))


def read(path):
    with wave.open(str(path), 'rb') as w:
        assert w.getframerate() == 44100 and w.getsampwidth() == 2
        data = array.array('h', w.readframes(w.getnframes()))
        return [s / 32768.0 for s in data], w.getnchannels()


def all_files():
    out = [ROOT / p for p in M4.shot_sound]
    for g in GROUPS:
        out += sorted((ROOT / AUDIO.folder).glob(f'{g}_*.wav'))
    return out


@pytest.mark.parametrize('group', GROUPS)
def test_every_mapped_sound_has_files(group):
    assert list((ROOT / AUDIO.folder).glob(f'{group}_*.wav')), group


def test_every_wav_has_its_source_mp3():
    for f in all_files():
        stem = f.stem[3:]
        if stem.startswith('shot_'):
            stem = 'shot_0'                                         # every gun-shot variant is built from one source (pitch-shifted)
        assert (ROOT / 'assets' / 'sounds' / 'source' / 'elevenlabs' / (stem + '.mp3')).exists(), f.name


@pytest.mark.parametrize('path', all_files(), ids=lambda p: p.stem)
def test_sound_starts_at_the_hit_and_does_not_clip(path):
    x, ch = read(path)
    assert x, path.name
    peak = max(abs(v) for v in x)
    assert 0.5 < peak <= 0.98
    if 'breath' in path.stem:                                       # breaths have no impact; checked separately in test_breath
        return
    first = next(i for i, v in enumerate(x) if abs(v) >= 0.04 * peak) // ch
    assert first / 44100 < 0.006                                    # the sound mark sits right at the impact: no leading silence allowed
    assert abs(x[-1]) < 0.02                                        # fades out: no click at the end
    assert len(x) / ch / 44100 < 1.0                                # short, does not hog memory


def test_gun_has_several_shot_variants_short_enough_for_the_pool():
    assert len(M4.shot_sound) >= 3
    interval = 60.0 / M4.rpm
    for p in M4.shot_sound:
        x, ch = read(ROOT / p)
        assert len(x) / ch / 44100 <= (M4.shot_pool - 1) * interval    # the old sound has already died before the whole pool cycles round


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='cần ffmpeg')
def test_wavs_match_the_tool_output():
    proc = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools' / 'build' / 'prep_elevenlabs.py'), '--check'], capture_output=True, encoding='utf-8', errors='replace', cwd=ROOT)
    assert proc.returncode == 0, proc.stdout


def test_impact_sound_arrives_late_and_quiet_from_far_away():
    near = impact_sound(AUDIO, 10.0, True)
    far = impact_sound(AUDIO, 200.0, True)
    assert near[0] == pytest.approx(10.0 / AUDIO.speed_of_sound)
    assert far[0] == pytest.approx(200.0 / AUDIO.speed_of_sound) and 0.5 < far[0] < 0.7
    assert far[1] < 0.4 * near[1]
    half = impact_sound(AUDIO, AUDIO.hit_reference_distance, True)[1]
    assert half == pytest.approx(AUDIO.hit_target_volume / 2)


def test_target_hit_is_louder_than_wall_hit():
    assert impact_sound(AUDIO, 25.0, True)[1] > impact_sound(AUDIO, 25.0, False)[1]


def _rms(x):
    return math.sqrt(sum(v * v for v in x) / max(len(x), 1))


def _db(v):
    return 20.0 * math.log10(max(v, 1e-6))


def _shot_mix():
    """Mixed exactly as in the game: 30 shots spaced 60 / rpm seconds apart, one variant after another (GunAudio plays round-robin). Returns (mix, mono list of each variant, samples per beat)."""
    variants = []
    for p in M4.shot_sound:
        x, ch = read(ROOT / p)
        variants.append([sum(x[i * ch + c] for c in range(ch)) / ch for i in range(len(x) // ch)])
    gap = round(44100 * 60.0 / M4.rpm)
    mix = [0.0] * (gap * 30 + 44100)
    for k in range(30):
        for i, v in enumerate(variants[k % len(variants)]):
            mix[k * gap + i] += v
    return mix, variants, gap


def test_every_shot_stands_out_at_full_auto():
    """Old bug: firing 3 rounds sounded like only 1, because the reverb tail of the previous shot masked 2 of the 3 variants (only 2-4 dB above the floor, the other variant 8 dB).
    Each shot, in every variant, must stand out clearly from the reverb still left just before it."""
    mix, variants, gap = _shot_mix()
    window, before = int(0.025 * 44100), int(0.015 * 44100)
    contrast = {}
    for k in range(6, 24):                       # skip the first few shots: the reverb tail has not built up yet
        t = k * gap
        contrast.setdefault(k % len(variants), []).append(_db(_rms(mix[t:t + window])) - _db(_rms(mix[t - before:t])))
    for v, values in contrast.items():
        assert min(values) >= 8.0, (v, values)


def test_shot_variants_are_equally_strong():
    _, variants, _ = _shot_mix()
    punch = [_db(_rms(x[:int(0.025 * 44100)])) for x in variants]
    assert max(punch) - min(punch) <= 1.0, punch


def test_shot_tail_is_gone_before_the_next_shot():
    _, variants, gap = _shot_mix()
    for x in variants:
        head = _rms(x[:int(0.025 * 44100)])
        at_next = _rms(x[gap - int(0.015 * 44100):gap])
        assert _db(at_next) - _db(head) <= -10.0

