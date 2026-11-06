"""Builds the gunshot sound used in the game from the original file (the original is kept).

The original file is 2 s long but the blast lasts only ~0.36 s, and it starts with ~48 ms of silence: left as is, the shot sounds ~3 frames late
after the trigger pull. This tool: (1) removes the leading silence (keeping a `PRE_ROLL` pad so the start of the blast is not cut),
(2) cuts the tail at `KEEP` seconds after the blast and fades out over `FADE` seconds so it does not click. Sample rate and channel count are unchanged.

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\build\\prep_sound.py [src.wav] [dst.wav]
Default: assets\\sounds\\source\\m4_shot_original.wav -> assets\\sounds\\m4_shot.wav
"""
import array
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONSET_THRESHOLD = 0.02      # fraction of full scale: the first sample above this level is the blast
PRE_ROLL = 0.003            # seconds kept before the blast
KEEP = 0.50                 # seconds kept after the blast
FADE = 0.08                 # seconds of fade-out at the end


def find_onset(samples, channels: int, threshold: float = ONSET_THRESHOLD) -> int:
    """FRAME index (not sample index) of the first frame whose amplitude exceeds `threshold` * full scale (16 bit)."""
    limit = threshold * 32768
    for i, x in enumerate(samples):
        if abs(x) > limit:
            return i // channels
    return 0


def trim(samples, channels: int, rate: int, pre_roll: float = PRE_ROLL, keep: float = KEEP, fade: float = FADE):
    """Returns the 16-bit sample array with the head and tail trimmed and the end faded out."""
    start = max(0, find_onset(samples, channels) - round(pre_roll * rate))
    end = min(len(samples) // channels, start + round((pre_roll + keep) * rate))
    out = array.array('h', samples[start * channels:end * channels])
    frames = len(out) // channels
    fade_frames = min(round(fade * rate), frames)
    for f in range(frames - fade_frames, frames):
        gain = 0.5 * (1.0 + math.cos(math.pi * (f - (frames - fade_frames)) / fade_frames))   # 1 -> 0, half cosine
        for c in range(channels):
            out[f * channels + c] = int(out[f * channels + c] * gain)
    return out


def convert(src: Path, dst: Path) -> dict:
    with wave.open(str(src), 'rb') as w:
        if w.getsampwidth() != 2 or w.getcomptype() != 'NONE':
            raise SystemExit(f'{src.name}: chỉ hỗ trợ WAV PCM 16 bit')
        channels, rate, n = w.getnchannels(), w.getframerate(), w.getnframes()
        samples = array.array('h')
        samples.frombytes(w.readframes(n))
    out = trim(samples, channels, rate)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return dict(rate=rate, channels=channels, src_seconds=n / rate, dst_seconds=len(out) // channels / rate,
                onset_ms=find_onset(samples, channels) / rate * 1000)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'assets' / 'sounds' / 'source' / 'm4_shot_original.wav'
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'assets' / 'sounds' / 'm4_shot.wav'
    info = convert(src, dst)
    print(f"{src.name} ({info['src_seconds']:.2f} s, nổ lúc {info['onset_ms']:.1f} ms) -> {dst.name} ({info['dst_seconds']:.2f} s), "
          f"{info['channels']} kênh {info['rate']} Hz")
