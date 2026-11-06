r"""Cắt hai file âm thanh do người dùng cung cấp thành các tiếng riêng cho game (stdlib thuần, không numpy).

Nguồn (giữ nguyên, nằm trong assets\sounds\source):
  reload_user_original.wav          1,0 s: 3 cú va kim loại (chốt băng, băng vào chỗ, bolt) + tiếng băng trượt rất nhỏ giữa chúng
  footstep_wood_user_original.wav   3,0 s: 4 bước chân trên sàn gỗ cách nhau ~0,7 s (mỗi bước là gót rồi mũi chân)
Ra assets\sounds\foley\user_<tên>_<số>.wav, cùng định dạng với các tiếng khác (48 000 Hz, 2 kênh, 16 bit).

Điểm cắt đo bằng đường bao 5 ms (xem SLICES). `onset` là lúc cú va bắt đầu TÍNH TỪ ĐẦU lát cắt: lát cắt được cắt sát (cách mốc 10-15 ms)
để mốc khung của SoundCue trong weapon_data đặt thẳng vào lúc va, không phải bù. Mỗi lát: mở đầu mờ vào (FADE_IN), mờ cuối (fade_out), nhân âm lượng theo `peak`
(đỉnh sau chuẩn hoá từng lát; bước chân gốc to nhỏ chênh tới 7 dB nên chuẩn hoá về cùng đỉnh cho đều).

Chạy:  .venv\Scripts\python.exe -X utf8 tools\build\prep_user_audio.py
Game nối chúng qua AudioData.sound_files (tên logic -> nhóm file), nên đổi file chỉ cần chạy lại công cụ này.
"""
import array
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'assets' / 'sounds' / 'source'
OUT = ROOT / 'assets' / 'sounds' / 'foley'
FADE_IN = 0.002      # s

# (nhóm, file nguồn, [(bắt đầu s, kết thúc s, mờ cuối s)], đỉnh đích sau chuẩn hoá)
SLICES = {
    # reload: chốt băng (onset 0,070), băng trượt vào (nhỏ, 0,245..0,358), băng vào chỗ (onset 0,363), bolt (onset 0,605; còn một cú nhẹ ở 0,65)
    'user_mag_release': ('reload_user_original.wav', [(0.058, 0.200, 0.020)], 0.60),
    'user_mag_in':      ('reload_user_original.wav', [(0.245, 0.358, 0.006)], 0.25),
    'user_mag_seat':    ('reload_user_original.wav', [(0.353, 0.560, 0.030)], 0.80),
    'user_bolt':        ('reload_user_original.wav', [(0.590, 0.780, 0.040)], 0.85),
    # bước chân gỗ: 4 bước, onset 0,530 / 1,240 / 1,970 / 2,640; mỗi lát từ 12 ms trước onset tới 0,30 s sau
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
    """{tên file: (kênh, tần số, mẫu float interleaved)} cho mọi lát cắt (chưa ghi)."""
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
