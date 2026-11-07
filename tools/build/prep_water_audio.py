r"""G10: builds the game's water sounds from the ElevenLabs drafts in assets/review/water/ (decoded by Panda3D itself: no ffmpeg needed).

One-shots -> assets/sounds/foley/<group>_<n>.wav (mono 44.1 kHz): leading silence cut (the splash starts on the step / landing), tail cut once it has died away, short fade, same peak.
Ambience -> assets/sounds/pool_ambience.wav: kept whole (it was generated as a seamless loop), stereo, quieter peak.
WITHOUT --apply it only prints the plan and a measurement table: nothing is written until the user has listened to the drafts and approved them (docs/WORKFLOW.md 6).

Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_water_audio.py [--apply] [--set wade=wade_step_a,wade_step_b] [--set water_hit=water_bullet_d] ...
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
TAIL_THRESHOLD = 0.015     # share of the peak (RMS over 10 ms) below which the sound has died away
FADE = 0.04                # s
PEAK = 0.8
AMBIENCE_PEAK = 0.5
MAX_SECONDS = {'wade': 0.9, 'wade_run': 0.7, 'wade_deep': 1.1, 'water_land': 1.6, 'water_hit': 0.9, 'drip': 1.6}

# group -> draft names (assets/review/water/<name>_eleven_v3.mp3). The DEFAULT proposal; the user's choice overrides it with --set.
PLAN = {
    'wade': ['wade_step_a', 'wade_step_b'],
    'wade_deep': ['wade_step_deep'],
    'wade_run': ['wade_run'],
    'water_land': ['water_jump_a', 'water_land_b'],
    'water_hit': ['water_bullet_d', 'water_splash_a', 'water_bullet_c'],
    'drip': ['water_drip'],
    'ambience': ['pool_ambience_loop'],
}


def decode(path: Path) -> tuple:
    """(rate, channels, [int16 samples interleaved]) via Panda's movie audio (it decodes MP3 itself)."""
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
    start = max(0, start - int(HEAD_KEEP * rate))
    x = x[start:]
    win = int(0.01 * rate)
    end = len(x)
    for i in range(len(x) - win, 0, -win):                    # from the end back to the last 10 ms window that is still loud
        rms = math.sqrt(sum(v * v for v in x[i:i + win]) / win)
        if rms >= TAIL_THRESHOLD * peak:
            end = min(len(x), i + win)
            break
    end = min(end, int(MAX_SECONDS.get(group, 1.5) * rate))
    x = x[:end]
    fade = min(int(FADE * rate), len(x))
    for k in range(fade):
        x[len(x) - fade + k] *= 1.0 - (k + 1) / fade
    g = PEAK / peak
    return [v * g for v in x]


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
    ap.add_argument('--apply', action='store_true', help='ghi file vào assets/ (chỉ sau khi người dùng đã nghe và duyệt)')
    ap.add_argument('--set', action='append', default=[], help='nhóm=bản1,bản2 (thay đề xuất mặc định)')
    args = ap.parse_args(argv)
    plan = {k: list(v) for k, v in PLAN.items()}
    for item in args.set:
        group, names = item.split('=')
        if group not in plan:
            sys.exit(f'nhóm lạ: {group} (có: {", ".join(plan)})')
        plan[group] = [n for n in names.split(',') if n]
    print(f'{"nhóm":12s} {"bản nháp":24s} {"gốc s":>6s} {"sau s":>6s} {"đỉnh":>6s}  -> file')
    for group, names in plan.items():
        for i, name in enumerate(names):
            src = REVIEW / f'{name}_eleven_v3.mp3'
            if not src.exists():
                sys.exit(f'thiếu {src}')
            rate, ch, s = decode(src)
            if rate != RATE:
                sys.exit(f'{src.name}: {rate} Hz, cần {RATE}')
            if group == 'ambience':
                frames = [v / 32768.0 for v in s]
                peak = max(abs(v) for v in frames) or 1.0
                frames = [v * AMBIENCE_PEAK / peak for v in frames]
                out, n_out, chans = AMBIENCE_OUT, len(frames) // ch, ch
            else:
                mono = to_mono(s, ch)
                frames = shape_one_shot(mono, rate, group)
                out, n_out, chans = FOLEY / f'{group}_{i}.wav', len(frames), 1
            print(f'{group:12s} {name:24s} {len(s) / ch / rate:6.2f} {n_out / RATE:6.2f} {max(abs(v) for v in frames):6.2f}  -> {out.relative_to(ROOT)}')
            if args.apply:
                write_wav(out, frames, chans)
    print('ĐÃ GHI.' if args.apply else 'Chưa ghi gì (thêm --apply sau khi người dùng duyệt).')


if __name__ == '__main__':
    main()
