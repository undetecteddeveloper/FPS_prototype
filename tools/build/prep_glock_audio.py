r"""Builds the Glock 17 sounds the user supplied (8/11/2026) from assets/sounds/source/glock/*.wav. Needs numpy (build time only: the game never imports it).

  single_gunshot_of_glock17-*.wav        ->  assets/sounds/glock_shot_0.wav            (stereo, exactly as recorded from the blast on: NO pitch-shifted copies, they dulled it; the per-shot random
                                             pitch of GunData.shot_pitch_variation keeps a string of shots from sounding like a loop). The source starts with ~0.45 s of faint hum
                                             (peak 4.7% of the blast) and 0.19 s of digital silence; the blast itself is at 0.66 s. Everything before it is dropped.
  glock_reloading_first-twobeats-*.wav   ->  assets/sounds/foley/glock_release_0.wav   beat 1: the release press (soft click) + the magazine sliding out (clack + two small rattles)
                                             assets/sounds/foley/glock_magout_0.wav    beat 2: the old magazine comes clear (the loud double thump)
  glock_reloading_lastbeat-*.wav         ->  assets/sounds/foley/glock_seat_0.wav      the LAST beat: the new magazine slams home
  source/glock/pistol_slide_release_elevenlabs.wav -> foley/glock_slide_0.wav  the slide release with its second, extra beat (a late 'settle' ~0.34 s after the release) cut off
  every foley file also gets a muffled twin in assets/sounds/foley_under (same filter as tools/build/prep_underwater.py).
The source reload files hold more than the wanted beats (a whole reload, 2.76 s each): only the segments below are cut out, the rest is dropped.

SYNC: each foley file starts exactly `lead` whole animation frames (1/30 s) before the moment its main transient hits (first sample >= ANCHOR_LEVEL x the beat's peak, so the soft click before
the clack does not count). weapon_data.GLOCK_SOUND_CUES then puts the file start at (animation event frame - lead): the transient lands on the frame of the visible impact, to the sample.
tests/test_glock_audio.py measures the transient in the built files and checks the cue table against the animation events. Change a `lead` here => change the cue frames there (the test says so).

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_glock_audio.py [--check]       --check: only verifies that the existing WAVs match the sources, writes nothing
"""
import argparse
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep_underwater  # noqa: E402  (same folder; muffled twins)

SOURCE = ROOT / 'assets' / 'sounds' / 'source' / 'glock'
SOUNDS = ROOT / 'assets' / 'sounds'
FOLEY = SOUNDS / 'foley'
FOLEY_UNDER = SOUNDS / 'foley_under'
FPS = 30.0

SHOT_SRC = 'single_gunshot_of_glock17-1794096011065.wav'
FIRST_SRC = 'glock_reloading_first-twobeats-1794097166031.wav'
LAST_SRC = 'glock_reloading_lastbeat-1794097100718.wav'

SHOT_PEAK = 0.95
SHOT_HEAD_LEVEL = 0.10                 # fraction of the peak: from here on counts as the start of the blast. NOT lower: the hum before the blast reaches 4.7% (a 4% threshold started the cut inside the hum,
                                       # so the first build contained only hum and no gunshot at all, 8/11/2026)
SHOT_HEAD_KEEP = 0.003                 # s kept before it, so the start is not clipped
SHOT_PEAK_WITHIN = 0.04                # s: the loudest sample of the built file must lie this close to its start (guard against cutting in the wrong place)
SHOT_MAX = 0.55                        # s
SHOT_FADE = 0.12                       # s fade-out (the source file is cut off at 1.2 s, still ringing)

SLIDE_SRC = SOURCE / 'pistol_slide_release_elevenlabs.wav'   # copy of the old ElevenLabs foley file (prep_elevenlabs.py output): a release snap at 0-0.08 s, silence, then an extra beat at 0.34-0.42 s
SLIDE_KEEP = 0.20                      # s: the first beat and its tail (the file is digital silence from ~0.10 s to ~0.32 s)
SLIDE_FADE = 0.04

ANCHOR_LEVEL = 0.40                    # fraction of a beat's peak: the first sample above this is the transient the animation event is matched to
TAIL_LEVEL = 0.004                     # fraction of a beat's peak: the beat ends when the 10 ms RMS stays below this
BEAT_FADE_IN = 0.001                   # s
BEAT_FADE_OUT = 0.040                  # s

# name -> (source file, search window in the source (s), lead frames, peak after normalising, cue volume suggested in weapon_data)
#  release : window 0.20-0.78 s holds the soft click (0.282), the clack (0.438) and two rattles (0.462, 0.506); the next beat starts at 0.82
#  magout  : window 0.78-1.50 s holds the loud double thump (0.852, 0.886); the source then goes quiet until 1.87 s (the extra beats of that file are not used)
#  seat    : window 1.46-2.20 s of the other file: a soft slide-in at 1.50 and the slam at ~1.52-1.54 (the beats before it, release / magazine out / slide in, are not used)
BEATS = {
    'glock_release': (FIRST_SRC, (0.20, 0.78), 6, 0.90),
    'glock_magout': (FIRST_SRC, (0.78, 1.50), 2, 0.90),
    'glock_seat': (LAST_SRC, (1.46, 2.20), 2, 0.90),
}


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


def resample(x: np.ndarray, count: int) -> np.ndarray:
    """x (frames, channels) -> `count` frames by spectrum truncation / padding (band-limited, no aliasing). Played at the same rate: pitch changes by len(x) / count."""
    n = x.shape[0]
    spec = np.fft.rfft(x, axis=0)
    out = np.zeros((count // 2 + 1, x.shape[1]), dtype=complex)
    k = min(out.shape[0], spec.shape[0])
    out[:k] = spec[:k]
    return np.fft.irfft(out, count, axis=0) * (count / n)


def anchor_time(x: np.ndarray, rate: int, level: float = ANCHOR_LEVEL) -> float:
    """Time (s) of the first sample whose level reaches `level` x the peak of x (x: frames x channels)."""
    m = np.abs(x).max(axis=1)
    return float(np.argmax(m >= level * m.max())) / rate


def build_shot(src: np.ndarray, rate: int) -> np.ndarray:
    m = np.abs(src).max(axis=1)
    start = max(0, int(np.argmax(m >= SHOT_HEAD_LEVEL * m.max())) - int(SHOT_HEAD_KEEP * rate))
    y = src[start:start + int(SHOT_MAX * rate)].copy()
    assert int(np.abs(y).max(axis=1).argmax()) < SHOT_PEAK_WITHIN * rate, 'the cut missed the blast'
    fade = min(int(SHOT_FADE * rate), y.shape[0] // 2)
    y[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None] ** 2
    return y * (SHOT_PEAK / np.abs(y).max())


def build_slide(src: np.ndarray, rate: int) -> np.ndarray:
    """The first beat of the old slide-release sound only: it starts on the impact (the cue frame is the impact frame) and the second cluster, SLIDE_KEEP seconds later, is cut away."""
    y = src[:int(SLIDE_KEEP * rate)].copy()
    fade = int(SLIDE_FADE * rate)
    y[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
    return y


def build_beat(name: str, src: np.ndarray, rate: int) -> np.ndarray:
    """One beat as a MONO clip (the two channels of the source are 98% the same): starts `lead` frames before the transient, ends when it has died away."""
    _, (t0, t1), lead, peak = BEATS[name]
    mono = src.mean(axis=1, keepdims=True)
    seg = mono[int(t0 * rate):int(t1 * rate)]
    anchor = anchor_time(seg, rate) + t0
    start = int(round((anchor - lead / FPS) * rate))
    rms = np.sqrt(np.convolve((seg[:, 0]) ** 2, np.ones(int(0.01 * rate)) / int(0.01 * rate), mode='same'))
    live = np.nonzero(rms >= TAIL_LEVEL * np.abs(seg).max())[0]
    end = int(t0 * rate) + int(live[-1]) + int(0.01 * rate)
    y = mono[start:end].copy()
    a, b = int(BEAT_FADE_IN * rate), min(int(BEAT_FADE_OUT * rate), y.shape[0])
    y[:a] *= np.linspace(0.0, 1.0, a)[:, None]
    y[-b:] *= np.linspace(1.0, 0.0, b)[:, None]
    return y * (peak / np.abs(y).max())


def jobs() -> list:
    """[(output path, rate, samples)] for every file this script owns (foley twins excluded)."""
    out = []
    rate, shot = read_wav(SOURCE / SHOT_SRC)
    out.append((SOUNDS / 'glock_shot_0.wav', rate, build_shot(shot, rate)))
    rate, slide = read_wav(SLIDE_SRC)
    out.append((FOLEY / 'glock_slide_0.wav', rate, build_slide(slide, rate)))
    cache = {}
    for name, (srcfile, *_rest) in BEATS.items():
        if srcfile not in cache:
            cache[srcfile] = read_wav(SOURCE / srcfile)
        rate, src = cache[srcfile]
        out.append((FOLEY / f'{name}_0.wav', rate, build_beat(name, src, rate)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    bad = 0
    print(f'{"file":26s} {"dài (s)":>8s} {"đỉnh":>6s} {"đầu->cú va chính (s)":>22s} {"= khung":>8s}')
    for path, rate, y in jobs():
        t = anchor_time(y, rate)
        print(f'{path.name:26s} {y.shape[0] / rate:8.3f} {np.abs(y).max():6.2f} {t:22.4f} {t * FPS:8.2f}')
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
