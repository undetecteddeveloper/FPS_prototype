"""Tiếng do người dùng cung cấp, cắt bằng tools/prep_user_audio.py: đúng định dạng, không méo, khớp đầu ra của công cụ, cú va sát đầu lát cắt."""
import array
import math
import wave

import pytest

from fps.weapon_data import AudioData
from tools import prep_user_audio as pu

AUDIO = AudioData()
ONSET_LIMIT = {'user_mag_release': 0.020, 'user_mag_in': 0.040, 'user_mag_seat': 0.020, 'user_bolt': 0.025, 'user_step': 0.025}   # s: lúc va đầu tiên tính từ đầu lát


@pytest.fixture(scope='module')
def built():
    return pu.build()


def samples(path):
    with wave.open(str(path), 'rb') as w:
        ch, sr = w.getnchannels(), w.getframerate()
        raw = array.array('h')
        raw.frombytes(w.readframes(w.getnframes()))
    return ch, sr, [v / 32768.0 for v in raw]


def test_source_files_are_kept():
    for src, _, _ in pu.SLICES.values():
        assert (pu.SRC / src).exists(), f'thiếu {src} trong sounds/source'


def test_slices_have_the_standard_format(built):
    with wave.open(str(pu.ROOT / 'sounds' / 'm4_shot.wav'), 'rb') as ref:
        want = (ref.getnchannels(), ref.getsampwidth(), ref.getframerate())
    for name in built:
        with wave.open(str(pu.OUT / name), 'rb') as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == want, name


def test_no_clipping_no_pop(built):
    for name, (ch, sr, x) in built.items():
        peak = max(abs(v) for v in x)
        assert 0.2 < peak <= 0.95, name
        assert abs(x[0]) < 1e-4 and abs(x[-1]) < 1e-3, f'{name}: mở đầu / cuối không về 0 (tiếng "bụp")'


def test_hit_is_right_at_the_start(built):
    """Mốc khung của SoundCue đặt thẳng vào lúc va, nên lát cắt không được có khoảng lặng dài ở đầu."""
    for name, (ch, sr, x) in built.items():
        group = name.rsplit('_', 1)[0]
        peak = max(abs(v) for v in x)
        first = next(i for i in range(0, len(x), ch) if abs(x[i]) > 0.25 * peak) / ch / sr
        assert first < ONSET_LIMIT[group], f'{name}: va đầu tiên ở {first * 1000:.0f} ms'


def test_committed_files_are_up_to_date(built):
    for name, (ch, sr, x) in built.items():
        path = pu.OUT / name
        assert path.exists(), f'thiếu {name}: chạy tools\\prep_user_audio.py'
        ch2, sr2, y = samples(path)
        assert (ch2, sr2, len(y)) == (ch, sr, len(x)), name
        assert max(abs(a - b) for a, b in zip(x, y)) < 2.0 / 32768, name


def test_steps_are_even_in_loudness(built):
    peaks = [max(abs(v) for v in x) for n, (_, _, x) in built.items() if n.startswith('user_step')]
    assert len(peaks) >= 4 and max(peaks) - min(peaks) < 0.02


def test_every_logical_name_points_at_a_real_file_group():
    names = {c.sound for cues in AUDIO.cues.values() for c in cues} | {'step_walk', 'step_run', 'land', 'jump', AUDIO.cancel_sound}
    for name in names:
        group = AUDIO.sound_files.get(name, name)
        files = list(pu.OUT.glob(f'{group}_*.wav'))
        assert files, f'{name} -> {group}: không có file nào'


def test_reload_cues_stay_in_frame_order():
    for key, cues in AUDIO.cues.items():
        frames = [c.frame for c in cues]
        assert frames == sorted(frames), key


def test_pitch_scale_is_sane():
    for name, k in AUDIO.pitch_scale.items():
        assert 0.5 < k < 2.0 and not math.isnan(k), name
