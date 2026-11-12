r"""Builds the Benelli M1014 sounds the user supplied (9/11/2026) from assets/sounds/source/m1014/*.wav. Needs numpy (build time only: the game never imports it).

  Benelli_M1014_fire_sound.wav       ->  assets/sounds/m1014_shot_0.wav          (stereo, from the blast on). The source is 2.0 s: 1.14 s of near silence (-50 .. -90 dB), then the blast, a 0.85 s
                                              tail that is still ringing when the file ends. Everything before the blast is dropped; the tail gets a short fade-out; the per-shot random pitch of
                                              GunData.shot_pitch_variation keeps a string of shots from sounding like a loop.
  Beneli_M1014_reload_sound.wav      ->  assets/sounds/foley/m1014_shell_0.wav   (mono). ONLY THE FIRST BEAT of the recording (the user's instruction): the shell pushed into the loading port,
                                              a soft click (0.46 s) and the main clack (0.58 s). The second beat (1.17 .. 1.5 s) is dropped. The game plays this one sound once per shell.
  every foley file also gets a muffled twin in assets/sounds/foley_under (same filter as tools/build/prep_underwater.py).

SYNC: the shell file starts exactly `LEAD` whole animation frames (1/30 s) before its main clack (first sample >= ANCHOR_LEVEL x the beat's peak, so the soft click before it does not count),
so weapon_data.M1014_SOUND_CUES puts the file start at (frame the shell seats - 1 - LEAD): the clack lands one frame before the shell has settled, as the shell is pushed home.
tests/test_m1014_audio.py measures the clack in the built file and checks the cue table against the animation events. Change `LEAD` here => change the cue frames there (the test says so).

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_m1014_audio.py [--check]       --check: only verifies that the existing WAVs match the sources, writes nothing
"""
import argparse
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep_underwater  # noqa: E402  (same folder; muffled twins)

SOURCE = ROOT / 'assets' / 'sounds' / 'source' / 'm1014'
SOUNDS = ROOT / 'assets' / 'sounds'
FOLEY = SOUNDS / 'foley'
FOLEY_UNDER = SOUNDS / 'foley_under'
FPS = 30.0

SHOT_SRC = 'Benelli_M1014_fire_sound.wav'
RELOAD_SRC = 'Beneli_M1014_reload_sound.wav'      # (sic: the file name as the user supplied it)

SHOT_PEAK = 0.95
SHOT_HEAD_LEVEL = 0.10                 # fraction of the peak: from here on counts as the start of the blast (the source before it stays below 0.4% of the peak)
SHOT_HEAD_KEEP = 0.003                 # s kept before it, so the start is not clipped
SHOT_PEAK_WITHIN = 0.04                # s: the loudest sample of the built file must lie this close to its start (guard against cutting in the wrong place)
SHOT_FADE = 0.15                       # s fade-out (the source is cut off at 2.0 s, still ringing at -43 dB)

# the first beat only: the window holds the soft click (~0.46 s) and the main clack (~0.58 s); the second beat starts at ~1.16 s and is not in the window
BEAT_WINDOW = (0.40, 1.00)
LEAD = 4                               # whole frames from the start of the file to its main clack
ANCHOR_LEVEL = 0.40                    # fraction of the beat's peak: the first sample above this is the transient the animation event is matched to
TAIL_LEVEL = 0.001                     # fraction of the beat's peak: the beat ends when the 10 ms RMS stays below this
BEAT_FADE_IN = 0.001                   # s
BEAT_FADE_OUT = 0.040                  # s
BEAT_PEAK = 0.90


def read_wav(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        assert w.getsampwidth() == 2, path
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, raw.reshape(-1, ch)


def pcm(x: np.ndarray) -> bytes:
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype('<i2').tobytes()


def write_wav(path: Path, rate: int, x: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm(x))


def anchor_time(x: np.ndarray, rate: int, level: float = ANCHOR_LEVEL) -> float:
    """Time (s) of the first sample whose level reaches `level` x the peak of x (x: frames x channels)."""
    m = np.abs(x).max(axis=1)
    return float(np.argmax(m >= level * m.max())) / rate


def build_shot(src: np.ndarray, rate: int) -> np.ndarray:
    m = np.abs(src).max(axis=1)
    start = max(0, int(np.argmax(m >= SHOT_HEAD_LEVEL * m.max())) - int(SHOT_HEAD_KEEP * rate))
    y = src[start:].copy()
    assert int(np.abs(y).max(axis=1).argmax()) < SHOT_PEAK_WITHIN * rate, 'the cut missed the blast'
    fade = min(int(SHOT_FADE * rate), y.shape[0] // 2)
    y[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None] ** 2
    return y * (SHOT_PEAK / np.abs(y).max())


def build_shell(src: np.ndarray, rate: int) -> np.ndarray:
    """The first beat as a MONO clip: starts LEAD frames before the clack, ends when the beat has died away."""
    t0, t1 = BEAT_WINDOW
    mono = src.mean(axis=1, keepdims=True)
    seg = mono[int(t0 * rate):int(t1 * rate)]
    anchor = anchor_time(seg, rate) + t0
    start = int(round((anchor - LEAD / FPS) * rate))
    win = int(0.01 * rate)
    rms = np.sqrt(np.convolve(seg[:, 0] ** 2, np.ones(win) / win, mode='same'))
    live = np.nonzero(rms >= TAIL_LEVEL * np.abs(seg).max())[0]
    end = int(t0 * rate) + int(live[-1]) + win
    y = mono[start:end].copy()
    a, b = int(BEAT_FADE_IN * rate), min(int(BEAT_FADE_OUT * rate), y.shape[0])
    y[:a] *= np.linspace(0.0, 1.0, a)[:, None]
    y[-b:] *= np.linspace(1.0, 0.0, b)[:, None]
    return y * (BEAT_PEAK / np.abs(y).max())


def jobs() -> list:
    """[(output path, rate, samples)] for every file this script owns (foley twins excluded)."""
    rate, shot = read_wav(SOURCE / SHOT_SRC)
    out = [(SOUNDS / 'm1014_shot_0.wav', rate, build_shot(shot, rate))]
    rate, reload_ = read_wav(SOURCE / RELOAD_SRC)
    out.append((FOLEY / 'm1014_shell_0.wav', rate, build_shell(reload_, rate)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    bad = 0
    print(f'{"file":24s} {"dài (s)":>8s} {"đỉnh":>6s} {"đầu->cú va chính (s)":>22s} {"= khung":>8s}')
    for path, rate, y in jobs():
        t = anchor_time(y, rate)
        print(f'{path.name:24s} {y.shape[0] / rate:8.3f} {np.abs(y).max():6.2f} {t:22.4f} {t * FPS:8.2f}')
        targets = [(path, y, rate)]
        if path.parent == FOLEY:
            targets.append((FOLEY_UNDER / path.name, prep_underwater.muffle(y, rate), rate))
        for target, data, r in targets:
            if args.check:
                try:
                    _, old = read_wav(target)
                    same = old.shape == data.shape and np.array_equal(np.round(data * 32767.0).clip(-32768, 32767).astype('<i2'), np.round(old * 32768.0).astype('<i2'))
                except FileNotFoundError:
                    same = False
                if not same:
                    print(f'  KHÁC NGUỒN / THIẾU: {target.relative_to(ROOT)}')
                    bad += 1
            else:
                write_wav(target, r, data)
    print('kiểm xong' if args.check else 'đã ghi')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
