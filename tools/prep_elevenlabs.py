"""Dựng tiếng từ các file MP3 tạo bằng ElevenLabs (sounds/source/elevenlabs/<tên>_<số>.mp3) thành WAV cho game (sounds/foley/el_<tên>_<số>.wav, tiếng súng: sounds/el_shot_<số>.wav).

Mỗi file: giải mã qua ffmpeg sang 44,1 kHz (tiếng súng giữ stereo, còn lại mono), cắt khoảng lặng đầu để cú va nằm ngay đầu file (mốc âm trong game đặt thẳng vào lúc va), cắt đuôi khi đã tắt,
mờ dần cuối file, đưa đỉnh về cùng mức. Cần ffmpeg trong PATH lúc dựng; game chỉ đọc WAV.
In bảng số đo (dài, đỉnh, RMS, số cú va) để phát hiện file có hai tiếng thay vì một.

Chạy: .venv\\Scripts\\python.exe -X utf8 tools\\prep_elevenlabs.py [--check]        --check: chỉ kiểm WAV đã có khớp nguồn, không ghi gì
"""
import argparse
import array
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'sounds' / 'source' / 'elevenlabs'
FOLEY = ROOT / 'sounds' / 'foley'
RATE = 44100
HEAD_THRESHOLD = 0.04          # phần của đỉnh: từ đây coi là bắt đầu tiếng
TAIL_THRESHOLD = 0.012         # phần của đỉnh: dưới mức này (RMS 10 ms) coi là đã tắt
HEAD_KEEP = 0.002              # s giữ lại trước cú va, cho khỏi cụt
# Tiếng súng chỉ có MỘT file nguồn (shot_0.mp3: người dùng chọn); hai biến thể kia là chính nó đổi cao độ (hệ số tốc độ phát) để liên thanh không nghe như máy lặp
SHOT_PITCHES = (1.0, 0.94, 1.07)
PEAK = {'shot': 0.95, 'breath': 0.7, 'step': 0.85, 'hit_target': 0.85, 'hit_hard': 0.85}      # còn lại DEFAULT_PEAK
DEFAULT_PEAK = 0.8
TAIL_FADE = {'shot': 0.10, 'breath': 0.06}     # s mờ dần cuối file; còn lại DEFAULT_FADE
DEFAULT_FADE = 0.03
# Tiếng súng phải tách được từng phát ở 750 phát/phút (80 ms một phát): đuôi vang dày của clip gốc che mất phát sau (đã gặp: bắn 3 viên chỉ nghe 1 tiếng, vì chỉ 1 trong 3 biến thể nổi hơn nền).
# Cú nổ giữ nguyên SHOT_HOLD rồi tắt theo hai đường: nhanh (thân tiếng), chậm (vang phòng). Mọi biến thể cùng độ mạnh ở SHOT_PUNCH_WINDOW đầu; vượt 1 thì bão hoà mềm (micro camera cũng vỡ tiếng như vậy).
SHOT_HOLD = 0.008              # s
SHOT_FAST = (0.80, 0.030)      # (phần, hằng số thời gian s)
SHOT_ROOM = (0.20, 0.200)      # vang như mái tôn (người dùng muốn vang, chói); lớn hơn nữa thì phát sau bị đuôi phát trước che (đo: 0,25 / 0,22 chỉ còn 8,6 dB)
SHOT_PUNCH_WINDOW = 0.025      # s
SHOT_PUNCH_RMS = 0.50          # RMS của cú nổ, -6 dB
MAX_SECONDS = {'breath': 4.0, 'shot': 0.55, 'step': 0.32, 'hit_target': 0.40, 'hit_hard': 0.50, 'dry': 0.20}


def group_of(stem: str) -> str:
    return stem.rsplit('_', 1)[0]


def decode(path: Path, channels: int, speed: float = 1.0) -> list:
    """Danh sách các mẫu xen kẽ, -1..1. `speed` != 1: phát nhanh / chậm như đĩa quay (đổi cả cao độ lẫn độ dài)."""
    af = [] if speed == 1.0 else ['-af', f'asetrate={RATE * speed:.1f},aresample={RATE}']
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'd.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-ac', str(channels), '-ar', str(RATE), *af, '-sample_fmt', 's16', str(out)], check=True)
        with wave.open(str(out), 'rb') as w:
            data = array.array('h', w.readframes(w.getnframes()))
    return [s / 32768.0 for s in data]


def process(samples: list, channels: int, group: str) -> list:
    if group == 'shot':
        samples = shape_shot(samples, channels)
    n = len(samples) // channels
    frame_peak = [max(abs(samples[i * channels + c]) for c in range(channels)) for i in range(n)]
    peak = max(frame_peak) or 1.0
    start, end = 0, n
    if group != 'breath':                          # tiếng thở giữ nguyên cả nhịp (hít vào bắt đầu từ rất khẽ; độ dài phải khớp một chu kỳ thở của sway)
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
    gain = 1.0 if group == 'shot' else PEAK.get(group, DEFAULT_PEAK) / peak      # tiếng súng đã cân bằng theo độ mạnh ở shape_shot
    for i in range(count):
        k = gain * (min(1.0, (count - i) / fade) if fade else 1.0)
        for c in range(channels):
            out[i * channels + c] *= k
    return out


def shape_shot(samples: list, channels: int) -> list:
    """Đưa đỉnh về sát đầu file, định hình cho súng tự động, cân bằng độ mạnh giữa các biến thể."""
    n = len(samples) // channels
    frame_peak = [max(abs(samples[i * channels + c]) for c in range(channels)) for i in range(n)]
    top = max(frame_peak) or 1.0
    # cú nổ đầu tiên đủ mạnh, không phải tiếng lách cách trước nó
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
    # bão hoà làm RMS tụt: bù một lượt rồi chặn đỉnh
    rms2 = math.sqrt(sum(v * v for v in drive[:w]) / max(min(w, len(drive)), 1)) or 1.0
    k = SHOT_PUNCH_RMS / rms2
    return [min(0.97, max(-0.97, math.tanh(v * gain * k))) for v in x]


def onsets(samples: list, channels: int) -> int:
    """Số cú va tách biệt: năng lượng 5 ms vượt 35% đỉnh sau khi đã tụt xuống dưới 10% ít nhất 40 ms."""
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
    """[(tên đầu ra, file nguồn mp3, hệ số tốc độ)]. Tiếng súng: mọi biến thể dựng từ shot_0.mp3."""
    out = []
    for f in sorted(SOURCE.glob('*.mp3')):
        if group_of(f.stem) == 'shot':
            if f.stem == 'shot_0':
                out += [(f'shot_{i}', f, k) for i, k in enumerate(SHOT_PITCHES)]
        else:
            out.append((f.stem, f, 1.0))
    return out


def target_for(stem: str) -> Path:
    return ROOT / 'sounds' / f'el_{stem}.wav' if group_of(stem) == 'shot' else FOLEY / f'el_{stem}.wav'


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
        channels = 2 if group == 'shot' else 1
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
