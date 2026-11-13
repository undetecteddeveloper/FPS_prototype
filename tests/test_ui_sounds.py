"""G20: the synthesised UI sounds (tools/build/make_ui_sounds.py -> assets/sounds/ui/*.wav). No speaker in the tests, so they check what can be measured:
format, length, level, no click at the edges, the hum loops with no seam, and that the files are exactly what the tool writes (nobody edited one by hand)."""
import wave
from pathlib import Path

import numpy as np
import pytest

from tools.build import make_ui_sounds as ms

DIR = Path(__file__).resolve().parents[1] / 'assets' / 'sounds' / 'ui'
# name: (min seconds, max seconds)
EXPECTED = {
    'boot_degauss': (0.6, 1.2), 'boot_hum': (2.9, 3.1), 'key_0': (0.02, 0.08), 'key_1': (0.02, 0.08), 'key_2': (0.02, 0.08), 'blip': (0.04, 0.12),
    'ok': (0.06, 0.2), 'relay': (0.1, 0.3), 'rec_start': (0.2, 0.5), 'ui_open': (0.08, 0.25), 'ui_close': (0.08, 0.25), 'ui_move': (0.015, 0.06), 'ui_change': (0.04, 0.12),
}


def load(name: str):
    with wave.open(str(DIR / f'{name}.wav'), 'rb') as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, ms.SR)
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype='<i2').astype(float) / 32767.0, raw


def test_every_sound_the_game_asks_for_exists():
    assert set(EXPECTED) == set(ms.SOUNDS)
    assert {p.stem for p in DIR.glob('*.wav')} == set(EXPECTED)


@pytest.mark.parametrize('name', sorted(EXPECTED))
def test_length_level_and_edges(name):
    x, _ = load(name)
    lo, hi = EXPECTED[name]
    assert lo <= len(x) / ms.SR <= hi
    peak = np.max(np.abs(x))
    assert 0.3 <= peak <= 0.9                                       # audible but never near clipping
    assert np.sqrt(np.mean(x ** 2)) > 0.02                           # not a near-silent file
    assert abs(np.mean(x)) < 0.01                                    # no DC offset
    if name != 'boot_hum':                                           # the hum is a loop: its ends meet each other (next test), they are not faded
        assert abs(x[0]) < 0.03 and abs(x[-1]) < 0.01                # starts and ends at ~0: no click


def test_the_hum_loops_without_a_seam():
    x, _ = load('boot_hum')
    seam = abs(x[0] - x[-1])
    assert seam <= 5.0 * np.std(np.diff(x))                          # the jump from the last sample to the first is an ordinary step of the signal
    assert abs(len(x) / ms.SR - 3.0) < 1e-6                          # whole 60 Hz cycles: 3.000 s exactly


def test_the_three_keystrokes_are_different():
    a, b, c = (load(f'key_{i}')[0] for i in range(3))
    assert not np.allclose(a, b) and not np.allclose(a, c) and not np.allclose(b, c)


def test_the_files_are_exactly_what_the_tool_writes():
    for name, make in ms.SOUNDS.items():
        assert ms.to_pcm16(make()) == load(name)[1], f'{name}.wav differs from make_ui_sounds.py: run the tool again (or the tool changed)'


def test_the_whole_set_is_small():
    assert sum(p.stat().st_size for p in DIR.glob('*.wav')) < 1_000_000
