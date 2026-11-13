r"""G20: synthesise the UI sounds of the boot splash and the graphics panel with numpy (no AI asset, no credit): assets/sounds/ui/*.wav, mono 44.1 kHz 16 bit.

  splash   boot_degauss  CRT power-on: a low thump, a 60 Hz buzz that dies away, a rising hiss (0.9 s)
           boot_hum      the terminal's hum bed (3.0 s, loops with no seam: whole cycles + periodic noise)
           key_0..2      a keystroke of the typewriter effect (three variants, played round-robin so fast typing does not retrigger one sample)
           blip          a section header tick
           ok            a status line turning OK (two short notes)
           relay         a relay clack (RECORDING ARMED)
           rec_start     the recording-start double beep (two rising beeps, like a body camera arming)
  panel    ui_open / ui_close  a short rising / falling sweep       ui_move  a soft tick on a row change       ui_change  a relay-lite click + blip on a value change

Deterministic (fixed seeds). Run: .venv\Scripts\python.exe -X utf8 tools\build\make_ui_sounds.py
No speaker here: the player judges how it sounds; the numbers (peak, length, loop seam, no click at the edges) are checked by tests/test_ui_sounds.py.
"""
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets' / 'sounds' / 'ui'
SR = 44100


def axis(seconds: float) -> np.ndarray:
    return np.arange(int(round(seconds * SR))) / SR


def band_noise(n: int, lo: float, hi: float, seed: int) -> np.ndarray:
    """White noise kept between `lo` and `hi` Hz (FFT mask with soft edges): vectorised, and periodic over the buffer (a loop of it has no seam)."""
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1.0 / SR)
    mask = np.clip((f - lo) / max(lo * 0.3, 1.0), 0, 1) * np.clip((hi - f) / max(hi * 0.3, 1.0), 0, 1)
    out = np.fft.irfft(spec * mask, n)
    return out / (np.max(np.abs(out)) + 1e-9)


def decay(t: np.ndarray, tau: float) -> np.ndarray:
    return np.exp(-t / tau)


def sine(f, t: np.ndarray) -> np.ndarray:
    """A sine at constant frequency `f`, or following the array `f` (phase = running sum, so a sweep has no jumps)."""
    f = np.broadcast_to(np.asarray(f, dtype=float), t.shape)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def edges(x: np.ndarray, fade_in_ms: float = 0.5, fade_out_ms: float = 3.0) -> np.ndarray:
    """Removes the DC offset (a decaying low tone is lopsided: a 150 Hz thock had +0.01), then a very short fade at both ends: no sample jumps (a click) at the start or the end."""
    x = x - np.mean(x)
    a, b = max(int(fade_in_ms * SR / 1000), 1), max(int(fade_out_ms * SR / 1000), 1)
    x[:a] *= np.linspace(0.0, 1.0, a)
    x[-b:] *= np.linspace(1.0, 0.0, b)
    return x


def normalise(x: np.ndarray, peak: float) -> np.ndarray:
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def place(total: float, *parts) -> np.ndarray:
    """Mix `(start seconds, signal)` parts into a buffer of `total` seconds."""
    out = np.zeros(int(round(total * SR)))
    for start, sig in parts:
        i = int(round(start * SR))
        out[i:i + len(sig)] += sig[:max(len(out) - i, 0)]
    return out


# ------------------------------------------------------------------ the sounds
def boot_degauss() -> np.ndarray:
    t = axis(0.9)
    thump = (sine(55.0, t) + 0.4 * sine(110.0, t)) * decay(t, 0.11)
    buzz = sine(60.0, t) * (0.6 + 0.4 * sine(7.0, t)) * decay(t, 0.22) * 0.55
    hiss = band_noise(len(t), 2500, 9000, 1) * np.clip(t / 0.22, 0, 1) * decay(t, 0.30) * 0.16
    whine = sine(np.linspace(6200, 9000, len(t)), t) * decay(t, 0.18) * 0.05
    return normalise(edges(thump + buzz + hiss + whine, 1.0, 12.0), 0.8)


def boot_hum() -> np.ndarray:
    """3.000 s loop: 60 Hz and its harmonics (whole cycles in the buffer) + a slow swell of one cycle per loop + periodic band noise = no seam."""
    t = axis(3.0)
    base = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((60, 1.0), (120, 0.5), (180, 0.2), (240, 0.1)))
    swell = 0.85 + 0.15 * np.sin(2 * np.pi * (1.0 / 3.0) * t)
    return normalise(base * swell * 0.5 + band_noise(len(t), 150, 1400, 2) * 0.12, 0.4)


def keystroke(seed: int, pitch: float = 1.0) -> np.ndarray:
    t = axis(0.045)
    click = band_noise(len(t), 1800, 6000, seed) * decay(t, 0.0035)
    thock = sine(150.0 * pitch, t) * decay(t, 0.012) * 0.7
    return normalise(edges(click + thock, 0.2, 6.0), 0.55)


def blip() -> np.ndarray:
    t = axis(0.07)
    shape = np.sin(np.pi * np.clip(t / 0.07, 0, 1)) ** 2
    return normalise(edges((sine(1500.0, t) + 0.25 * sine(3000.0, t)) * shape, 1.0, 4.0), 0.5)


def ok_tick() -> np.ndarray:
    a, b = axis(0.04), axis(0.07)
    na = sine(1400.0, a) * np.sin(np.pi * np.clip(a / 0.04, 0, 1)) ** 2
    nb = sine(2100.0, b) * np.sin(np.pi * np.clip(b / 0.07, 0, 1)) ** 2
    return normalise(edges(place(0.11, (0.0, na), (0.04, nb * 0.9)), 1.0, 4.0), 0.5)


def relay() -> np.ndarray:
    t = axis(0.18)
    thud = sine(85.0, t) * decay(t, 0.05)
    ring = sine(2400.0, t) * decay(t, 0.02) * 0.3
    clack = band_noise(len(t), 900, 7000, 3) * decay(t, 0.004)
    release = np.roll(band_noise(len(t), 1200, 6000, 4) * decay(t, 0.003), int(0.085 * SR)) * 0.5
    release[:int(0.085 * SR)] = 0.0
    return normalise(edges(thud + ring + clack + release, 0.2, 8.0), 0.75)


def rec_start() -> np.ndarray:
    """Two rising beeps (1.9 kHz, 2.5 kHz): a body camera arming. A smooth envelope, so no click."""
    def beep(f):
        t = axis(0.09)
        return (sine(f, t) + 0.15 * sine(2 * f, t)) * np.sin(np.pi * np.clip(t / 0.09, 0, 1)) ** 1.5
    return normalise(edges(place(0.30, (0.0, beep(1900.0)), (0.15, beep(2500.0))), 1.0, 5.0), 0.65)


def ui_open() -> np.ndarray:
    t = axis(0.14)
    f = 500.0 * (1500.0 / 500.0) ** (t / 0.14)
    shape = np.sin(np.pi * np.clip(t / 0.14, 0, 1)) ** 1.5
    click = band_noise(len(t), 1500, 6000, 5) * decay(t, 0.003) * 0.35
    return normalise(edges(sine(f, t) * shape + click, 0.3, 6.0), 0.5)


def ui_close() -> np.ndarray:
    t = axis(0.12)
    f = 1400.0 * (450.0 / 1400.0) ** (t / 0.12)
    shape = np.sin(np.pi * np.clip(t / 0.12, 0, 1)) ** 1.5
    return normalise(edges(sine(f, t) * shape, 0.5, 6.0), 0.45)


def ui_move() -> np.ndarray:
    t = axis(0.028)
    return normalise(edges(sine(2400.0, t) * decay(t, 0.007) + band_noise(len(t), 2000, 7000, 6) * decay(t, 0.002) * 0.4, 0.2, 4.0), 0.35)


def ui_change() -> np.ndarray:
    t = axis(0.075)
    click = band_noise(len(t), 1000, 6500, 7) * decay(t, 0.003)
    tone = sine(1300.0, t) * decay(t, 0.02) * 0.6
    return normalise(edges(click + tone, 0.2, 6.0), 0.5)


SOUNDS = {
    'boot_degauss': boot_degauss, 'boot_hum': boot_hum,
    'key_0': lambda: keystroke(10, 1.00), 'key_1': lambda: keystroke(11, 1.12), 'key_2': lambda: keystroke(12, 0.92),
    'blip': blip, 'ok': ok_tick, 'relay': relay, 'rec_start': rec_start,
    'ui_open': ui_open, 'ui_close': ui_close, 'ui_move': ui_move, 'ui_change': ui_change,
}


def to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype('<i2').tobytes()


def write(name: str, x: np.ndarray):
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f'{name}.wav'), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(to_pcm16(x))
    print(f'{name}.wav  {len(x) / SR:.3f} s  peak {np.max(np.abs(x)):.2f}')


def main():
    for name, make in SOUNDS.items():
        write(name, make())


if __name__ == '__main__':
    sys.exit(main())
