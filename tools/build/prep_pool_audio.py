r"""Builds the footstep and the room tone the user supplied (8/11/2026) from assets/sounds/source/pool/*.wav. Needs numpy (build time only: the game never imports it).

  tatical_boot_footstep_on_brick_ground-*.wav  ->  assets/sounds/foley/boot_step_0.wav          ONE step (the source holds 0.85 s of silence, a heel strike, a toe tap 70 ms later and a ring-out), mono,
                                                   used for BOTH walking and running (AudioData.sound_files: step_walk / step_run; running plays it 6% higher and louder, see AudioData)
  Tranquil_indoor_swim_narrow-*.wav            ->  assets/sounds/pool_ambience.wav            the room tone of the pool hall, looped by the game: made seamless by an equal-power crossfade of its end
                                                   into its start, and raised to the loudness of the room tone it replaces (the source is 19 dB quieter, so AudioData.ambience_volume keeps its meaning)
  pool_ambience.wav                            ->  assets/sounds/under_ambience.wav           the muffled tone heard with the head under the water (same builder as tools/build/prep_underwater.py)
  boot_step_0.wav                              ->  assets/sounds/foley_under/boot_step_0.wav  its muffled twin
(`Tranquil_indoor_swim_wide-*.wav` is NOT used yet: the user keeps it for later.)

SYNC WITH THE BOB: fps/core/footsteps.py plays a step in the frame where Sway.phase crosses the foot-plant point (the gun's lowest point of the bob; headcam's `footfall` trough is the same instant), so the
file must put its impact on its FIRST sample: the heel strike starts STEP_HEAD_KEEP before the 10% point and the file is cut right there. tests/test_boot_step_audio.py measures it in the built file.

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_pool_audio.py [--check]       --check: only verifies that the existing WAVs match the sources, writes nothing
"""
import argparse
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep_underwater  # noqa: E402  (same folder: the muffler and the underwater tone)

SOURCE = ROOT / 'assets' / 'sounds' / 'source' / 'pool'
SOUNDS = ROOT / 'assets' / 'sounds'
FOLEY = SOUNDS / 'foley'
FOLEY_UNDER = SOUNDS / 'foley_under'

STEP_SRC = 'tatical_boot_footstep_on_brick_ground-1794106668223.wav'
TONE_SRC = 'Tranquil_indoor_swim_narrow-1794095744410.wav'

STEP_HEAD_LEVEL = 0.10         # fraction of the peak: from here on counts as the start of the heel strike
STEP_HEAD_KEEP = 0.002         # s kept before it
STEP_MAX = 0.50                # s: two steps back to back at a sprint (~0.3 s apart, two playback copies) must not cut each other off, and a step is over by then
STEP_TAIL_LEVEL = 0.010        # fraction of the peak: the 10 ms RMS below this = died away
STEP_FADE = 0.08               # s
STEP_PEAK = 0.85               # like every other foley sound (AudioData.step_volume was set for this level)
TONE_LOOP_CROSSFADE = 0.6      # s
TONE_RMS = 0.085               # RMS of the room tone this replaces (measured on the old pool_ambience.wav): ambience_volume 0.30 stays as loud as it was
TONE_PEAK_MAX = 0.9


def read_wav(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        assert w.getsampwidth() == 2, path
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, raw.reshape(-1, ch)


def write_wav(path: Path, rate: int, x: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(np.round(x * 32767.0), -32768, 32767).astype('<i2').tobytes())


def anchor_time(x: np.ndarray, rate: int, level: float = 0.40) -> float:
    m = np.abs(x).max(axis=1)
    return float(np.argmax(m >= level * m.max())) / rate


def build_step(src: np.ndarray, rate: int) -> np.ndarray:
    mono = src.mean(axis=1, keepdims=True)                      # the two channels are 99.9% the same
    m = np.abs(mono[:, 0])
    start = max(0, int(np.argmax(m >= STEP_HEAD_LEVEL * m.max())) - int(STEP_HEAD_KEEP * rate))
    y = mono[start:start + int(STEP_MAX * rate)].copy()
    win = int(0.01 * rate)
    rms = np.sqrt(np.convolve(y[:, 0] ** 2, np.ones(win) / win, mode='same'))
    live = np.nonzero(rms >= STEP_TAIL_LEVEL * np.abs(y).max())[0]
    y = y[:int(live[-1]) + win]
    fade = min(int(STEP_FADE * rate), y.shape[0])
    y[-fade:] *= 0.5 * (1.0 + np.cos(np.pi * np.arange(1, fade + 1) / fade))[:, None]     # raised-cosine fade-out
    assert int(np.abs(y[:, 0]).argmax()) < 0.02 * rate, 'the heel strike is not at the start'
    return y * (STEP_PEAK / np.abs(y).max())


def build_tone(src: np.ndarray, rate: int) -> np.ndarray:
    """Seamless loop (equal-power crossfade of the last TONE_LOOP_CROSSFADE s into the first ones, the end cut off) at the loudness of the old room tone."""
    xf = int(TONE_LOOP_CROSSFADE * rate)
    n = src.shape[0]
    w = (np.arange(xf) / xf)[:, None]
    out = src[:n - xf].copy()
    out[:xf] = src[:xf] * np.sqrt(w) + src[n - xf:] * np.sqrt(1.0 - w)
    gain = TONE_RMS / float(np.sqrt(np.mean(out * out)))
    gain = min(gain, TONE_PEAK_MAX / float(np.abs(out).max()))
    return out * gain


def jobs() -> list:
    """[(output path, rate, samples)]."""
    rate, step = read_wav(SOURCE / STEP_SRC)
    step_out = build_step(step, rate)
    out = [(FOLEY / 'boot_step_0.wav', rate, step_out), (FOLEY_UNDER / 'boot_step_0.wav', rate, prep_underwater.muffle(step_out, rate))]
    rate, tone = read_wav(SOURCE / TONE_SRC)
    room = build_tone(tone, rate)
    out += [(SOUNDS / 'pool_ambience.wav', rate, room), (SOUNDS / 'under_ambience.wav', rate, prep_underwater.build_ambience(room, rate))]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    bad = 0
    print(f'{"file":34s} {"dài (s)":>8s} {"đỉnh":>6s} {"RMS":>7s}')
    for path, rate, y in jobs():
        print(f'{str(path.relative_to(SOUNDS)):34s} {y.shape[0] / rate:8.3f} {np.abs(y).max():6.2f} {np.sqrt(np.mean(y * y)):7.4f}')
        if args.check:
            try:
                _, old = read_wav(path)
                same = old.shape == y.shape and np.array_equal(np.round(y * 32767.0).clip(-32768, 32767).astype('<i2'), np.round(old * 32768.0).astype('<i2'))
            except FileNotFoundError:
                same = False
            if not same:
                print(f'  KHÁC NGUỒN / THIẾU: {path.relative_to(ROOT)}')
                bad += 1
        else:
            write_wav(path, rate, y)
    print('kiểm xong' if args.check else 'đã ghi')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
