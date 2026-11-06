"""Builds game sounds from the MP3 files made with ElevenLabs (assets/sounds/source/elevenlabs/<name>_<index>.mp3) into WAV (assets/sounds/foley/el_<name>_<index>.wav; gunshots: assets/sounds/el_shot_<index>.wav).

Each file: decoded with ffmpeg to 44.1 kHz (gunshots keep stereo, the rest are mono), leading silence is cut so the impact sits right at the start of the file (the game's sound cues land exactly on the impact), the tail is cut once it has died away,
the end fades out, and peaks are brought to the same level. ffmpeg must be on PATH at build time; the game reads only WAV.
Prints a table of measurements (length, peak, RMS, impact count) to catch files that contain two sounds instead of one.

Run: .venv\\Scripts\\python.exe -X utf8 tools\\build\\prep_elevenlabs.py [--check]        --check: only verifies that the existing WAVs match their sources, writes nothing
"""
import argparse
import array
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'assets' / 'sounds' / 'source' / 'elevenlabs'
FOLEY = ROOT / 'assets' / 'sounds' / 'foley'
RATE = 44100
HEAD_THRESHOLD = 0.04          # fraction of the peak: from here on counts as the start of the sound
TAIL_THRESHOLD = 0.012         # fraction of the peak: below this level (RMS over 10 ms) the sound counts as finished
HEAD_KEEP = 0.002              # s kept before the impact, so the start is not clipped
# The gunshot has ONE source file per gun (shot_0.mp3 for the M4, pistol_shot_0.mp3 for the Glock; chosen by the user); the two other variants are the same clip with the pitch changed (playback speed factor), so a burst does not sound like a loop machine
SHOT_PITCHES = (1.0, 0.94, 1.07)
SHOT_GROUPS = ('shot', 'pistol_shot')           # gunshot groups: built from <group>_0.mp3 into el_<group>_<i>.wav next to the M4 shots, with the same shaping
PEAK = {'shot': 0.95, 'pistol_shot': 0.95, 'breath': 0.7, 'step': 0.85, 'hit_target': 0.85, 'hit_hard': 0.85}      # the rest use DEFAULT_PEAK
DEFAULT_PEAK = 0.8
TAIL_FADE = {'shot': 0.10, 'pistol_shot': 0.10, 'breath': 0.06}     # s fade-out at the end of the file; the rest use DEFAULT_FADE
DEFAULT_FADE = 0.03
# Each gunshot must stay separable at 750 rounds/min (80 ms apart): the thick reverb tail of the original clip hid the next shot (seen: 3 rounds sounded like 1, because only 1 of the 3 variants stood out above the background).
# The blast holds for SHOT_HOLD, then decays along two paths: fast (the body of the sound) and slow (room reverb). All variants share the same strength over the first SHOT_PUNCH_WINDOW; above 1 it soft-saturates (a camera mic distorts the same way).
SHOT_HOLD = 0.008              # s
SHOT_FAST = (0.80, 0.030)      # (fraction, time constant in s)
SHOT_ROOM = (0.20, 0.200)      # reverb like a metal roof (the user wants it loud and harsh); larger and the next shot is masked by the tail of the previous one (measured: 0.25 / 0.22 leaves only 8.6 dB)
SHOT_PUNCH_WINDOW = 0.025      # s
SHOT_PUNCH_RMS = 0.50          # RMS of the blast, -6 dB
MAX_SECONDS = {'breath': 4.0, 'shot': 0.55, 'pistol_shot': 0.55, 'step': 0.32, 'hit_target': 0.40, 'hit_hard': 0.50, 'dry': 0.20}


def group_of(stem: str) -> str:
    return stem.rsplit('_', 1)[0]


def decode(path: Path, channels: int, speed: float = 1.0) -> list:
    """Interleaved sample list, -1..1. `speed` != 1: plays faster or slower like a turntable (changes both pitch and length)."""
    af = [] if speed == 1.0 else ['-af', f'asetrate={RATE * speed:.1f},aresample={RATE}']
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'd.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-ac', str(channels), '-ar', str(RATE), *af, '-sample_fmt', 's16', str(out)], check=True)
        with wave.open(str(out), 'rb') as w:
            data = array.array('h', w.readframes(w.getnframes()))
    return [s / 32768.0 for s in data]


def process(samples: list, channels: int, group: str) -> list:
    if group in SHOT_GROUPS:
        samples = shape_shot(samples, channels)
    n = len(samples) // channels
    frame_peak = [max(abs(samples[i * channels + c]) for c in range(channels)) for i in range(n)]
    peak = max(frame_peak) or 1.0
    start, end = 0, n
    if group != 'breath':                          # breath keeps its full timing (the inhale starts very quietly; the length must match one breath cycle of the sway)
        start = next(i for i, v in enumerate(frame_peak) if v >= HEAD_THRESHOLD * peak)
        start = max(0, start - int(HEAD_KEEP * RATE))
        win = int(0.01 * RATE)
        for i in range(n - win, start, -win):
            if math.sqrt(sum(v * v for v in frame_peak[i:i + win]) / win) >= TAIL_THRESHOLD * peak:
                end = min(n, i + win)
                break
    end = min(end, start + int(MAX_SECONDS.get(group, 9.0) * RATE))
    out = samples[start * channels:end * channels]
    count = len(out) // channels
    fade = min(int(TAIL_FADE.get(group, DEFAULT_FADE) * RATE), count // 2)
    gain = 1.0 if group in SHOT_GROUPS else PEAK.get(group, DEFAULT_PEAK) / peak      # gunshots are already balanced for strength in shape_shot
    for i in range(count):
        k = gain * (min(1.0, (count - i) / fade) if fade else 1.0)
        for c in range(channels):
            out[i * channels + c] *= k
    return out


def shape_shot(samples: list, channels: int) -> list:
    """Moves the peak to right at the start of the file, shapes it for automatic fire, and balances strength between variants."""
    n = len(samples) // channels
    frame_peak = [max(abs(samples[i * channels + c]) for c in range(channels)) for i in range(n)]
    top = max(frame_peak) or 1.0
    # the first blast must be strong enough, not a click before it
    first = next(i for i, v in enumerate(frame_peak) if v >= 0.5 * top)
    start = max(0, first - int(0.001 * RATE))
    x = samples[start * channels:]
    n = len(x) // channels
    for i in range(n):
        t = max(i / RATE - SHOT_HOLD, 0.0)
        env = SHOT_FAST[0] * math.exp(-t / SHOT_FAST[1]) + SHOT_ROOM[0] * math.exp(-t / SHOT_ROOM[1])
        for c in range(channels):
            x[i * channels + c] *= env
    w = int(SHOT_PUNCH_WINDOW * RATE) * channels
    rms = math.sqrt(sum(v * v for v in x[:w]) / max(min(w, len(x)), 1)) or 1.0
    gain = SHOT_PUNCH_RMS / rms
    drive = [math.tanh(v * gain) for v in x]
    # saturation lowers the RMS: compensate once, then clamp the peak
    rms2 = math.sqrt(sum(v * v for v in drive[:w]) / max(min(w, len(drive)), 1)) or 1.0
    k = SHOT_PUNCH_RMS / rms2
    return [min(0.97, max(-0.97, math.tanh(v * gain * k))) for v in x]


def onsets(samples: list, channels: int) -> int:
    """Number of separate impacts: a 5 ms energy window that exceeds 35% of the peak, after the level has dropped below 10% for at least 40 ms."""
    n = len(samples) // channels
    win = int(0.005 * RATE)
    env = [max(abs(s) for s in samples[i * channels:(i + win) * channels]) for i in range(0, n - win, win)]
    top = max(env) or 1.0
    count, quiet, armed = 0, 8, True
    for v in env:
        if v < 0.10 * top:
            quiet += 1
            if quiet >= 8:
                armed = True
        else:
            quiet = 0
        if armed and v >= 0.35 * top:
            count += 1
            armed = False
    return count


def to_pcm(samples: list) -> bytes:
    return array.array('h', (max(-32768, min(32767, int(round(s * 32767)))) for s in samples)).tobytes()


def jobs() -> list:
    """[(output name, source mp3 file, speed factor)]. Gunshots: every variant is built from shot_0.mp3."""
    out = []
    for f in sorted(SOURCE.glob('*.mp3')):
        g = group_of(f.stem)
        if g in SHOT_GROUPS:
            if f.stem == f'{g}_0':
                out += [(f'{g}_{i}', f, k) for i, k in enumerate(SHOT_PITCHES)]
        else:
            out.append((f.stem, f, 1.0))
    return out


def target_for(stem: str) -> Path:
    return ROOT / 'assets' / 'sounds' / f'el_{stem}.wav' if group_of(stem) in SHOT_GROUPS else FOLEY / f'el_{stem}.wav'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    files = jobs()
    if not files:
        print(f'không có file trong {SOURCE}')
        return 1
    bad = 0
    print(f'{"tên":16s} {"dài (s)":>8s} {"RMS":>7s} {"cú va":>6s}')
    for stem, f, speed in files:
        group = group_of(stem)
        channels = 2 if group in SHOT_GROUPS else 1
        out = process(decode(f, channels, speed), channels, group)
        pcm = to_pcm(out)
        rms = math.sqrt(sum(s * s for s in out) / max(len(out), 1))
        print(f'{stem:16s} {len(out) / channels / RATE:8.3f} {rms:7.3f} {onsets(out, channels):6d}')
        target = target_for(stem)
        if args.check:
            with wave.open(str(target), 'rb') as w:
                if w.readframes(w.getnframes()) != pcm:
                    print(f'  KHÁC NGUỒN: {target.name}')
                    bad += 1
            continue
        with wave.open(str(target), 'wb') as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
