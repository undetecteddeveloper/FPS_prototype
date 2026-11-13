"""Sounds generated with ElevenLabs (tools/build/prep_elevenlabs.py): all files present, correct format, impact right at the start of each file, no distortion; plus the maths of the hit sound."""
import shutil
import subprocess
import sys
import wave
import array
from pathlib import Path

import pytest

from fps.core.cues import impact_sound
from fps.weapon_data import AudioData

ROOT = Path(__file__).resolve().parent.parent
AUDIO = AudioData()
GROUPS = sorted(set(v for v in AUDIO.sound_files.values() if v.startswith('el_')))


def read(path):
    with wave.open(str(path), 'rb') as w:
        assert w.getframerate() == 44100 and w.getsampwidth() == 2
        data = array.array('h', w.readframes(w.getnframes()))
        return [s / 32768.0 for s in data], w.getnchannels()


def all_files():
    out = []
    for g in GROUPS:
        out += sorted((ROOT / AUDIO.folder).glob(f'{g}_*.wav'))
    return out


@pytest.mark.parametrize('group', GROUPS)
def test_every_mapped_sound_has_files(group):
    assert list((ROOT / AUDIO.folder).glob(f'{group}_*.wav')), group


def test_every_wav_has_its_source_mp3():
    for f in all_files():
        if not f.name.startswith('el_'):
            continue                                                # the M4 shot is the user's own file now (m4_shot_new.wav): it has no ElevenLabs source
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


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='cần ffmpeg')
def test_wavs_match_the_tool_output():
    proc = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools' / 'build' / 'prep_elevenlabs.py'), '--check'], capture_output=True, encoding='utf-8', errors='replace', cwd=ROOT)
    assert proc.returncode == 0, proc.stdout


def test_impact_sound_arrives_late_and_quiet_from_far_away():
    near = impact_sound(AUDIO, 10.0)
    far = impact_sound(AUDIO, 200.0)
    assert near[0] == pytest.approx(10.0 / AUDIO.speed_of_sound)
    assert far[0] == pytest.approx(200.0 / AUDIO.speed_of_sound) and 0.5 < far[0] < 0.7
    assert far[1] < 0.4 * near[1]
    half = impact_sound(AUDIO, AUDIO.hit_reference_distance)[1]
    assert half == pytest.approx(AUDIO.hit_hard_volume / 2)
