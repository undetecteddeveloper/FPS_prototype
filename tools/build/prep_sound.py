"""Dựng bản tiếng súng dùng trong game từ file gốc (giữ nguyên file gốc).

File gốc dài 2 s nhưng tiếng nổ chỉ ~0,36 s, và mở đầu bằng ~48 ms im lặng: để nguyên thì tiếng súng trễ ~3 khung
so với phát bắn. Công cụ này: (1) bỏ phần im lặng đầu (giữ `PRE_ROLL` đệm để không cắt vào đầu tiếng nổ),
(2) cắt đuôi ở `KEEP` giây kể từ lúc nổ, mờ dần `FADE` giây để không bị tiếng "tách". Tần số, số kênh giữ nguyên.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\build\\prep_sound.py [gốc.wav] [đích.wav]
Mặc định: assets\\sounds\\source\\m4_shot_original.wav -> assets\\sounds\\m4_shot.wav
"""
import array
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONSET_THRESHOLD = 0.02      # tỉ lệ thang: mẫu đầu tiên vượt mức này là lúc nổ
PRE_ROLL = 0.003            # s giữ lại trước lúc nổ
KEEP = 0.50                 # s giữ lại kể từ lúc nổ
FADE = 0.08                 # s mờ dần ở cuối


def find_onset(samples, channels: int, threshold: float = ONSET_THRESHOLD) -> int:
    """Chỉ số KHUNG (không phải mẫu) của khung đầu tiên có biên độ vượt `threshold` * thang đầy (16 bit)."""
    limit = threshold * 32768
    for i, x in enumerate(samples):
        if abs(x) > limit:
            return i // channels
    return 0


def trim(samples, channels: int, rate: int, pre_roll: float = PRE_ROLL, keep: float = KEEP, fade: float = FADE):
    """Trả về mảng mẫu 16 bit đã cắt đầu/đuôi và mờ dần cuối."""
    start = max(0, find_onset(samples, channels) - round(pre_roll * rate))
    end = min(len(samples) // channels, start + round((pre_roll + keep) * rate))
    out = array.array('h', samples[start * channels:end * channels])
    frames = len(out) // channels
    fade_frames = min(round(fade * rate), frames)
    for f in range(frames - fade_frames, frames):
        gain = 0.5 * (1.0 + math.cos(math.pi * (f - (frames - fade_frames)) / fade_frames))   # 1 -> 0, nửa cosine
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
