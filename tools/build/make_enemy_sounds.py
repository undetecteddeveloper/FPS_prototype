r"""G18: synthesise the sounds of the Backrooms enemies with numpy (no AI asset, no credit): assets/sounds/enemy/*.wav, mono 44.1 kHz 16 bit.

  alert   a low detuned groan with a slow wobble (an enemy turns hostile)
  windup  a rising hiss + breath (the telegraph before a strike)
  strike  a heavy body thud (the strike lands on the player)
  hurt    a short wet thump (a bullet hits a capsule)
  die     a falling groan ending in a thud
  player_hurt  a muffled low knock with a short ring (the player is hit; heard 'inside the head')
  lift_hum     G19: the lift motor during a ride (4.2 s: hum, whine, rumble)
  lift_ding    G19: the arrival chime
  door_slide   G19: a door / lift leaf sliding

Deterministic (fixed seeds): running it again gives the same files. Run: .venv\Scripts\python.exe -X utf8 tools\build\make_enemy_sounds.py
"""
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets' / 'sounds' / 'enemy'
SR = 44100


def env(n, attack, release, shape=2.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((n / SR - t) / max(release, 1e-4), 0, 1) ** shape
    return a * r


def lowpass(x, cutoff):
    """One-pole low-pass (run twice: 12 dB / octave)."""
    k = np.exp(-2 * np.pi * np.asarray(cutoff) / SR)
    for _ in range(2):
        y = np.empty_like(x)
        acc = 0.0
        kk = np.broadcast_to(k, x.shape)
        for i in range(len(x)):
            acc = (1 - kk[i]) * x[i] + kk[i] * acc
            y[i] = acc
        x = y
    return x


def saw(freq):
    phase = np.cumsum(freq / SR)
    return 2.0 * (phase % 1.0) - 1.0


def groan(seconds, f0, f1, seed, rough=0.4):
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * (t / seconds) + 3.0 * np.sin(2 * np.pi * 5.5 * t)
    x = sum(saw(f * d) for d in (1.0, 1.013, 0.991)) / 3.0
    x += rough * rng.standard_normal(n) * (0.5 + 0.5 * np.sin(2 * np.pi * f * 0.5 / SR * np.arange(n)))
    x = lowpass(x, 420.0 + 260.0 * np.sin(2 * np.pi * 1.3 * t) ** 2)
    return x * env(n, 0.08, seconds * 0.5)


def thud(seconds, f, seed, click=0.4):
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (f * t - 18.0 * t * t)) * np.exp(-t * 18.0)
    noise = lowpass(rng.standard_normal(n), 900.0) * np.exp(-t * 60.0)
    hit = rng.standard_normal(n) * np.exp(-t * 400.0) * click
    return body + noise * 0.8 + hit


def hiss(seconds, seed):
    n = int(seconds * SR)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = lowpass(x, 500.0 + 2500.0 * (t / seconds) ** 1.5) - lowpass(x, 250.0)
    return x * env(n, seconds * 0.8, 0.05, 1.0)


def normalise(x, peak=0.85):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def write(name, x):
    OUT.mkdir(parents=True, exist_ok=True)
    data = (np.clip(x, -1, 1) * 32767).astype('<i2')
    with wave.open(str(OUT / f'{name}.wav'), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(f'{name}.wav  {len(x) / SR:.2f} s')


def main():
    write('alert', normalise(groan(0.95, 95.0, 70.0, 1)))
    write('windup', normalise(hiss(0.42, 2) * 0.8 + groan(0.42, 120.0, 150.0, 3, rough=0.8) * 0.5))
    write('strike', normalise(thud(0.35, 70.0, 4, click=0.6)))
    write('hurt', normalise(thud(0.16, 140.0, 5, click=0.25) * 0.8 + lowpass(np.random.default_rng(6).standard_normal(int(0.16 * SR)), 1800.0) * env(int(0.16 * SR), 0.002, 0.12) * 0.5))
    d = groan(1.25, 90.0, 38.0, 7, rough=0.6)
    tail = thud(0.4, 55.0, 8, click=0.5)
    write('die', normalise(np.concatenate([d, np.zeros(int(0.05 * SR))]) + np.concatenate([np.zeros(len(d) + int(0.05 * SR) - len(tail)), tail * 0.9])))
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    ring = np.sin(2 * np.pi * 1850.0 * t) * np.exp(-t * 9.0) * 0.12
    write('player_hurt', normalise(lowpass(thud(0.45, 60.0, 9, click=0.2), 600.0) + ring, 0.8))
    # G19 the lift
    n = int(4.2 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(10)
    hum = 0.5 * np.sin(2 * np.pi * 50.0 * t) + 0.3 * np.sin(2 * np.pi * 100.0 * t) + 0.12 * np.sin(2 * np.pi * (182.0 + 6.0 * np.sin(2 * np.pi * 0.7 * t)) * t)
    rumble = lowpass(rng.standard_normal(n), 140.0) * 1.5
    write('lift_hum', normalise((hum + rumble) * env(n, 0.6, 0.9, 1.5), 0.7))
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    bell = lambda f, t0: np.where(t >= t0, (np.sin(2 * np.pi * f * (t - t0)) + 0.35 * np.sin(2 * np.pi * 2.76 * f * (t - t0))) * np.exp(-(t - t0) * 2.8), 0.0)
    write('lift_ding', normalise(bell(1318.5, 0.0) + 0.9 * bell(1046.5, 0.32), 0.6))
    n = int(0.75 * SR)
    t = np.arange(n) / SR
    swish = lowpass(np.random.default_rng(11).standard_normal(n), 700.0) * env(n, 0.08, 0.25, 1.0)
    write('door_slide', normalise(swish, 0.6))


if __name__ == '__main__':
    sys.exit(main())
