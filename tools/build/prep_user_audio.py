r"""Cut the two user-supplied audio files into separate game sounds (pure stdlib, no numpy).

Sources (kept as they are, in assets\sounds\source):
  reload_user_original.wav          1.0 s: 3 metal impacts (magazine catch, magazine seated, bolt) + a very quiet magazine slide between them
  footstep_wood_user_original.wav   3.0 s: 4 footsteps on a wooden floor, ~0.7 s apart (each step is heel, then toe)
Output assets\sounds\foley\user_<name>_<index>.wav, same format as the other sounds (48 000 Hz, 2 channels, 16 bit).

Cut points are measured with a 5 ms envelope (see SLICES). `onset` is when the impact starts, MEASURED FROM THE START of the slice: each slice is cut tight (10-15 ms before the cue)
so the frame cue of SoundCue in weapon_data lands exactly on the impact, with no offset. Each slice fades in at the start (FADE_IN), fades out at the end (fade_out), and its volume is multiplied by `peak`
(peak after normalizing each slice; the original footsteps differ in loudness by up to 7 dB, so they are normalized to the same peak for evenness).

Run:  .venv\Scripts\python.exe -X utf8 tools\build\prep_user_audio.py
The game links them through AudioData.sound_files (logical name -> file group), so changing a file only needs this tool re-run.
"""
import array
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'assets' / 'sounds' / 'source'
OUT = ROOT / 'assets' / 'sounds' / 'foley'
FADE_IN = 0.002      # s

# (group, source file, [(start s, end s, fade-out s)], target peak after normalization)
SLICES = {
    # reload: magazine catch (onset 0.070), magazine slide-in (quiet, 0.245..0.358), magazine seated (onset 0.363), bolt (onset 0.605; a light extra knock at 0.65)
    'user_mag_release': ('reload_user_original.wav', [(0.058, 0.200, 0.020)], 0.60),
    'user_mag_in':      ('reload_user_original.wav', [(0.245, 0.358, 0.006)], 0.25),
    'user_mag_seat':    ('reload_user_original.wav', [(0.353, 0.560, 0.030)], 0.80),
    'user_bolt':        ('reload_user_original.wav', [(0.590, 0.780, 0.040)], 0.85),
    # wood footsteps: 4 steps, onset 0.530 / 1.240 / 1.970 / 2.640; each slice runs from 12 ms before its onset to 0.30 s after
    'user_step':        ('footstep_wood_user_original.wav',
                         [(0.518, 0.832, 0.050), (1.228, 1.542, 0.050), (1.958, 2.272, 0.050), (2.628, 2.942, 0.050)], 0.85),
}


def read(path: Path):
    with wave.open(str(path), 'rb') as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        assert sw == 2, f'{path.name}: cần 16 bit'
        raw = array.array('h')
        raw.frombytes(w.readframes(n))
        if sys.byteorder == 'big':
            raw.byteswap()
    return ch, sr, raw


def cut(raw: array.array, ch: int, sr: int, t0: float, t1: float, fade_out: float) -> list:
    a, b = int(round(t0 * sr)) * ch, int(round(t1 * sr)) * ch
    x = [v / 32768.0 for v in raw[a:b]]
    frames = len(x) // ch
    fi, fo = max(1, int(FADE_IN * sr)), max(1, int(fade_out * sr))
    for i in range(frames):
        g = 1.0
        if i < fi:
            g = i / fi
        if i >= frames - fo:
            g = min(g, (frames - 1 - i) / fo)
        for c in range(ch):
            x[i * ch + c] *= g
    return x


def write(path: Path, x: list, ch: int, sr: int):
    out = array.array('h', (max(-32768, min(32767, int(round(v * 32767)))) for v in x))
    if sys.byteorder == 'big':
        out.byteswap()
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())


def build() -> dict:
    """{file name: (channels, rate, interleaved float samples)} for every slice (not written yet)."""
    result = {}
    cache = {}
    for group, (src, spans, peak) in SLICES.items():
        if src not in cache:
            cache[src] = read(SRC / src)
        ch, sr, raw = cache[src]
        slices = [cut(raw, ch, sr, t0, t1, fo) for t0, t1, fo in spans]
        for i, s in enumerate(slices):
            g = peak / max(abs(v) for v in s)
            result[f'{group}_{i}.wav'] = (ch, sr, [v * g for v in s])
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (ch, sr, x) in build().items():
        write(OUT / name, x, ch, sr)
        print(f'{name}: {len(x) // ch / sr * 1000:.0f} ms, đỉnh {max(abs(v) for v in x):.2f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
