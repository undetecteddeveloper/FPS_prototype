r"""G10: builds the game's water sounds from the ElevenLabs drafts the user chose (assets/review/water/, 7/11/2026), decoded by Panda3D itself (no ffmpeg needed):
  wade_step_deep -> assets/sounds/foley/wade_0.wav        (EVERY wading step: the game calibrates pitch / volume by depth and speed, fps/game/foley.py)
  water_jump_a   -> assets/sounds/foley/water_land_0.wav  (jumping / falling into the pool)
  pool_ambience_loop -> assets/sounds/pool_ambience.wav   (room tone, looped by the game: the file is made seamless by a crossfade of its end into its start)
One-shots: leading silence cut (the splash starts on the step), tail cut once it has died away and faded out, mono 44.1 kHz, same peak as the tile steps.
Prints a table of lengths and LOUDNESS compared with the tile footsteps (RMS), which is how `AudioData.wade_volume` was calibrated.
WITHOUT --apply nothing is written.

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_water_audio.py [--apply]
"""
import argparse
import array
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'assets' / 'review' / 'water'
FOLEY = ROOT / 'assets' / 'sounds' / 'foley'
AMBIENCE_OUT = ROOT / 'assets' / 'sounds' / 'pool_ambience.wav'
RATE = 44100
HEAD_THRESHOLD = 0.05      # share of the peak where the sound starts
HEAD_KEEP = 0.004          # s kept before it
TAIL_THRESHOLD = 0.02      # share of the peak (RMS over 10 ms) below which the sound has died away
PEAK = 0.85                # like the tile steps (prep_elevenlabs.PEAK['step'])
AMBIENCE_PEAK = 0.5
LOOP_CROSSFADE = 0.6       # s
# group -> (max seconds, fade-out seconds): a wading step rings out slowly (a slosh), but not long enough to cover the next step
SHAPE = {'wade': (0.75, 0.25), 'water_land': (1.6, 0.3)}

PLAN = {                   # group -> draft name (assets/review/water/<name>_eleven_v3.mp3)
    'wade': 'wade_step_deep',
    'water_land': 'water_jump_a',
    'ambience': 'pool_ambience_loop',
}


def decode(path: Path) -> tuple:
    """(rate, channels, int16 samples interleaved) via Panda's movie audio (it decodes MP3 itself)."""
    from panda3d.core import Datagram, Filename, MovieAudio
    cur = MovieAudio.get(Filename.from_os_specific(str(path))).open()
    if cur is None:
        raise RuntimeError(f'không mở được {path}')
    dg = Datagram()
    cur.read_samples(int(cur.audio_rate() * cur.length()) + 8192, dg)
    raw = bytes(dg.get_message())
    samples = array.array('h')
    samples.frombytes(raw[: len(raw) // 2 * 2])
    return cur.audio_rate(), cur.audio_channels(), samples


def to_mono(samples, channels: int) -> list:
    if channels == 1:
        return [s / 32768.0 for s in samples]
    return [sum(samples[i + c] for c in range(channels)) / (32768.0 * channels) for i in range(0, len(samples) - channels + 1, channels)]


def shape_one_shot(x: list, rate: int, group: str) -> list:
    peak = max((abs(v) for v in x), default=0.0)
    if peak <= 1e-6:
        return x
    start = next((i for i, v in enumerate(x) if abs(v) >= HEAD_THRESHOLD * peak), 0)
    x = x[max(0, start - int(HEAD_KEEP * rate)):]
    win = int(0.01 * rate)
    end = len(x)
    for i in range(len(x) - win, 0, -win):                    # from the end back to the last 10 ms window that is still loud
        if math.sqrt(sum(v * v for v in x[i:i + win]) / win) >= TAIL_THRESHOLD * peak:
            end = min(len(x), i + win)
            break
    max_s, fade_s = SHAPE.get(group, (1.5, 0.05))
    x = x[:min(end, int(max_s * rate))]
    fade = min(int(fade_s * rate), len(x))
    for k in range(fade):                                      # smooth (raised-cosine) fade-out
        x[len(x) - fade + k] *= 0.5 * (1.0 + math.cos(math.pi * (k + 1) / fade))
    g = PEAK / peak
    return [v * g for v in x]


def make_loop(frames: list, channels: int, rate: int) -> list:
    """Seamless loop: the last `LOOP_CROSSFADE` s are blended into the first ones (equal power), and cut off the end. Playing the result around gives a continuous signal."""
    xf = int(LOOP_CROSSFADE * rate) * channels
    n = len(frames)
    if n < 4 * xf:
        return frames
    out = list(frames[: n - xf])
    for i in range(xf):
        w = i / xf
        out[i] = frames[i] * math.sqrt(w) + frames[n - xf + i] * math.sqrt(1.0 - w)
    return out


def rms(x: list) -> float:
    return math.sqrt(sum(v * v for v in x) / max(len(x), 1))


def tile_step_rms() -> float:
    """Mean RMS of the tile footsteps (step_walk_*.wav), the loudness reference for wading."""
    vals = []
    for f in sorted(FOLEY.glob('step_walk_*.wav')):
        with wave.open(str(f), 'rb') as w:
            data = array.array('h')
            data.frombytes(w.readframes(w.getnframes()))
            vals.append(rms([v / 32768.0 for v in data]))
    return sum(vals) / len(vals) if vals else 0.0


def write_wav(path: Path, frames: list, channels: int = 1):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array.array('h', (max(-32767, min(32767, int(v * 32767))) for v in frames))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='ghi file vào assets/')
    args = ap.parse_args(argv)
    ref = tile_step_rms()
    print(f'{"nhóm":12s} {"bản":22s} {"gốc s":>6s} {"sau s":>6s} {"đỉnh":>5s} {"RMS":>6s} {"so với bước gạch":>17s}  -> file')
    for group, name in PLAN.items():
        src = REVIEW / f'{name}_eleven_v3.mp3'
        if not src.exists():
            sys.exit(f'thiếu {src}')
        rate, ch, s = decode(src)
        if rate != RATE:
            sys.exit(f'{src.name}: {rate} Hz, cần {RATE}')
        if group == 'ambience':
            frames = [v / 32768.0 for v in s]
            peak = max(abs(v) for v in frames) or 1.0
            frames = make_loop([v * AMBIENCE_PEAK / peak for v in frames], ch, rate)
            out, chans = AMBIENCE_OUT, ch
            length = len(frames) / ch / RATE
        else:
            frames = shape_one_shot(to_mono(s, ch), rate, group)
            out, chans = FOLEY / f'{group}_0.wav', 1
            length = len(frames) / RATE
        r = rms(frames)
        ratio = f'{r / ref:5.2f}x' if group != 'ambience' and ref else '      -'
        print(f'{group:12s} {name:22s} {len(s) / ch / rate:6.2f} {length:6.2f} {max(abs(v) for v in frames):5.2f} {r:6.3f} {ratio:>17s}  -> {out.relative_to(ROOT)}')
        if args.apply:
            write_wav(out, frames, chans)
    print('ĐÃ GHI.' if args.apply else 'Chưa ghi gì (thêm --apply).')


if __name__ == '__main__':
    main()
