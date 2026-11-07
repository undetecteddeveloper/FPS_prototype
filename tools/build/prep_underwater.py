r"""G12: builds the sounds heard with the head UNDER the water (user's choice 7/11/2026: "nghẹt nhiều", the ElevenLabs drafts were dropped). Needs numpy (build time only: the game never imports it).
  assets/sounds/foley/<name>.wav  ->  assets/sounds/foley_under/<name>.wav   every foley sound muffled (the game swaps to this bank while the eye is under the surface: fps/game/foley.py)
  assets/sounds/pool_ambience.wav ->  assets/sounds/under_ambience.wav       the room tone muffled harder + a low hum + a few soft bubbles (cross-faded with the room tone: fps/game/underwater.py)
Why not a live filter: Panda's OpenAL backend cannot filter (`configure_filters` returns False; FMOD Ex can, but it is a 2014 library with no newer Panda binding: user chose pre-filtered copies).

Method: a ZERO-PHASE low-pass applied in the frequency domain, |H| = 1 / sqrt(1 + (f / cutoff)^(2 * order)) (Butterworth magnitude; order 4 = 24 dB / octave), so the clicks keep their timing. One-shots are
zero-padded (the smear after the end is cut off), the ambience is filtered CIRCULARLY, which keeps a seamless loop seamless. A filtered sound is much quieter, so it is scaled back to `level` x the
original RMS (water and head also change the level; the game's volumes stay as they are), then limited to PEAK_MAX. Fixed seeds: a rerun gives the same bytes.
WITHOUT --apply nothing is written (a table of before / after is printed).

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_underwater.py [--apply] [--cutoff 400] [--level 0.5] [--amb-cutoff 220] [--no-bubbles]
"""
import argparse
import sys
import wave
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FOLEY = ROOT / 'assets' / 'sounds' / 'foley'
FOLEY_OUT = ROOT / 'assets' / 'sounds' / 'foley_under'
AMBIENCE = ROOT / 'assets' / 'sounds' / 'pool_ambience.wav'
AMBIENCE_OUT = ROOT / 'assets' / 'sounds' / 'under_ambience.wav'

CUTOFF = 400.0            # Hz: everything above is gone (-3 dB here, -24 dB at 800 Hz, -48 dB at 1.6 kHz)
ORDER = 4
LEVEL = 0.5               # muffled RMS as a share of the original RMS
PEAK_MAX = 0.9
FADE_IN = 0.002           # s (the filter smears the start; start from 0 again)
FADE_OUT = 0.010
PAD = 0.5                 # s of zeros after a one-shot while filtering

AMB_CUTOFF = 220.0
AMB_LEVEL = 1.0           # RMS of the underwater tone / RMS of the room tone (the game's volume sets the rest)
HUM = ((46.0, 0.5), (71.0, 0.35), (103.0, 0.2))     # (Hz, weight): the low pressure hum; each is rounded to a whole number of periods in the loop so it repeats exactly
NOISE_CUT = 90.0          # Hz corner of the brown-ish rumble noise
MIX = (1.0, 0.6, 0.8, 0.5)  # room tone, hum, rumble, bubbles
BUBBLES = 9               # soft bubbles over the loop


def read_wav(path: Path) -> tuple:
    """(rate, float samples shaped (frames, channels) in [-1, 1]) of a 16-bit PCM file."""
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2:
            raise ValueError(f'{path}: only 16-bit PCM')
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype='<i2').astype(np.float64) / 32768.0
    return rate, raw.reshape(-1, ch)


def write_wav(path: Path, rate: int, x: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(np.round(x * 32767.0), -32768, 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def response(freqs: np.ndarray, cutoff: float, order: int = ORDER) -> np.ndarray:
    return 1.0 / np.sqrt(1.0 + (freqs / cutoff) ** (2 * order))


def lowpass(x: np.ndarray, rate: int, cutoff: float, order: int = ORDER, circular: bool = False) -> np.ndarray:
    """Zero-phase low-pass of x shaped (frames, channels). `circular` = the signal is a loop (no padding: the filter wraps around the seam)."""
    n = x.shape[0]
    size = n if circular else n + int(PAD * rate)
    spec = np.fft.rfft(x, size, axis=0)
    h = response(np.fft.rfftfreq(size, 1.0 / rate), cutoff, order)
    return np.fft.irfft(spec * h[:, None], size, axis=0)[:n]


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def fades(x: np.ndarray, rate: int) -> np.ndarray:
    n = x.shape[0]
    a, b = min(int(FADE_IN * rate), n), min(int(FADE_OUT * rate), n)
    y = x.copy()
    if a:
        y[:a] *= np.linspace(0.0, 1.0, a)[:, None]
    if b:
        y[n - b:] *= np.linspace(1.0, 0.0, b)[:, None]
    return y


def muffle(x: np.ndarray, rate: int, cutoff: float = CUTOFF, level: float = LEVEL) -> np.ndarray:
    """A one-shot heard through water: low-passed, brought back to `level` x its original RMS, limited, faded."""
    y = lowpass(x, rate, cutoff)
    r0, r1 = rms(x), rms(y)
    if r1 > 1e-9:
        y *= level * r0 / r1
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > PEAK_MAX:
        y *= PEAK_MAX / peak
    return fades(y, rate)


def centroid(x: np.ndarray, rate: int) -> float:
    """Spectral centroid (Hz) of the mono mix."""
    m = x.mean(axis=1)
    mag = np.abs(np.fft.rfft(m))
    f = np.fft.rfftfreq(m.size, 1.0 / rate)
    return float((mag * f).sum() / max(mag.sum(), 1e-12))


def rng_for(name: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(name.encode()))


def periodic_noise(n: int, rate: int, corner: float, rng: np.random.Generator) -> np.ndarray:
    """Brown-ish noise that repeats exactly every n samples (random phases at the FFT bins of the loop): flat below `corner`, falling 12 dB / octave above."""
    f = np.fft.rfftfreq(n, 1.0 / rate)
    mag = 1.0 / (1.0 + (f / corner) ** 2)
    mag[0] = 0.0
    spec = mag * np.exp(2j * np.pi * rng.random(f.size))
    y = np.fft.irfft(spec, n)
    return y / max(rms(y[:, None]), 1e-12)


def bubble(rate: int, rng: np.random.Generator) -> np.ndarray:
    """One soft bubble: a short sine that rises in pitch (a bubble's note rises as it rises and shrinks) with a fast exponential decay."""
    dur = float(rng.uniform(0.03, 0.07))
    t = np.arange(int(dur * rate)) / rate
    f0 = float(rng.uniform(260.0, 620.0))
    phase = 2 * np.pi * (f0 * t + 0.5 * (f0 * 2.5) * t * t)
    return np.sin(phase) * np.exp(-t / (dur * 0.35)) * np.minimum(t * 400.0, 1.0)


def build_ambience(room: np.ndarray, rate: int, cutoff: float = AMB_CUTOFF, level: float = AMB_LEVEL, bubbles: int = BUBBLES, seed: str = 'under_ambience') -> np.ndarray:
    """The underwater tone from the room tone `room` (frames, channels): the room tone low-passed hard (circularly), a low hum, a brown rumble and a few bubbles. Seamless as a loop if `room` is."""
    n, ch = room.shape
    t = np.arange(n) / rate
    length = n / rate
    rng = rng_for(seed)
    base = lowpass(room, rate, cutoff, circular=True)
    hum = np.zeros(n)
    for i, (hz, weight) in enumerate(HUM):
        k = max(1, round(hz * length))                                   # whole periods in the loop: the hum repeats exactly
        slow = 1.0 + 0.3 * np.sin(2 * np.pi * (1 + i) / length * t + rng.random() * 6.28)    # slow swell, also a whole number of cycles
        hum += weight * slow * np.sin(2 * np.pi * k / length * t + rng.random() * 6.28)
    rumble = np.stack([periodic_noise(n, rate, NOISE_CUT, rng) for _ in range(ch)], axis=1)       # a different rumble in each ear
    pops = np.zeros((n, ch))
    for _ in range(bubbles):
        b = bubble(rate, rng)
        start = int(rng.integers(0, n - b.size))                         # never wraps over the seam
        pops[start:start + b.size, int(rng.integers(0, ch))] += b * float(rng.uniform(0.4, 1.0))
    mix = MIX[0] * base / max(rms(base), 1e-12) + MIX[1] * hum[:, None] / max(rms(hum[:, None]), 1e-12) + MIX[2] * rumble + MIX[3] * pops / max(rms(pops), 1e-12) * 0.25
    mix *= level * rms(room) / max(rms(mix), 1e-12)
    peak = float(np.max(np.abs(mix)))
    if peak > PEAK_MAX:
        mix *= PEAK_MAX / peak
    return mix


def plan(cutoff: float, level: float, amb_cutoff: float, bubbles: int):
    """Yields (label, source path, output path, result array, rate, source array) for every file."""
    for src in sorted(FOLEY.glob('*.wav')):
        rate, x = read_wav(src)
        yield src.name, src, FOLEY_OUT / src.name, muffle(x, rate, cutoff, level), rate, x
    rate, room = read_wav(AMBIENCE)
    yield 'pool_ambience -> under_ambience', AMBIENCE, AMBIENCE_OUT, build_ambience(room, rate, amb_cutoff, bubbles=bubbles), rate, room


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write the files (without it: only the table)')
    ap.add_argument('--cutoff', type=float, default=CUTOFF)
    ap.add_argument('--level', type=float, default=LEVEL)
    ap.add_argument('--amb-cutoff', type=float, default=AMB_CUTOFF)
    ap.add_argument('--no-bubbles', action='store_true')
    args = ap.parse_args(argv)
    print(f'{"file":38s} {"RMS truoc":>9s} {"sau":>7s} {"tam pho truoc":>14s} {"sau (Hz)":>9s}')
    for label, _, out, y, rate, x in plan(args.cutoff, args.level, args.amb_cutoff, 0 if args.no_bubbles else BUBBLES):
        print(f'{label:38s} {rms(x):9.4f} {rms(y):7.4f} {centroid(x, rate):14.0f} {centroid(y, rate):9.0f}')
        if args.apply:
            write_wav(out, rate, y)
    print('đã ghi' if args.apply else 'chưa ghi gì (thêm --apply)')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
