"""Tổng hợp âm thanh foley bằng code thuần (không tải tài nguyên ngoài, không numpy): kim loại khi nạp đạn/rút súng và bước chân trên gạch.

Ra `sounds\\foley\\<tên>_<số>.wav`, 48 000 Hz, 2 kênh, 16 bit (đúng định dạng `sounds\\m4_shot.wav`; hai kênh giống nhau, vị trí trái-phải do game đặt).
Mỗi tiếng dựng từ seed cố định (crc32 của "tên:số"), nên chạy lại ra đúng byte cũ và tiếng nào cũng có vài biến thể khác nhau.

Cách dựng (mô hình vật lý đơn giản):
  - kim loại va đập = xung nhiễu rất ngắn ở đầu (tiếng "tách") + thân trầm tắt nhanh + vài sóng sin tắt dần có tần số KHÔNG điều hoà (1-9 kHz)
  - ma sát kim loại   = nhiễu lọc dải, biên độ nhấp nhô kiểu dính-trượt (stick-slip) 80-140 Hz
  - bước chân trên gạch = gót gõ (sin trầm tụt tần nhanh + nhiễu thấp) + "tick" cộng hưởng của viên gạch 1,7-3,6 kHz + tiếng cọ của đế + mũi giày chạm xuống
Mọi tiếng có mở đầu từ 0 (0,4 ms) và mờ cuối (10 ms) để không có tiếng "bụp"; chuẩn hoá đỉnh theo bảng SOUNDS (âm lượng khi phát do game chỉnh).

Chạy:   .venv\\Scripts\\python.exe -X utf8 tools\\prep_foley.py            dựng lại toàn bộ
        .venv\\Scripts\\python.exe -X utf8 tools\\prep_foley.py --check    dựng xong in số đo từng file (đỉnh, RMS, thời gian tắt, trọng tâm phổ...)
        .venv\\Scripts\\python.exe -X utf8 tools\\prep_foley.py --out thu_muc_khac
"""
import array
import math
import random
import sys
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RATE = 48000
CHANNELS = 2
FADE_IN = 0.0004      # s: mở đầu từ 0
FADE_OUT = 0.010      # s: mờ cuối
TAIL_CUT = 0.002      # cắt đuôi khi biên độ dưới 0,2% đỉnh (-54 dB)


# --- khối dựng cơ bản (mọi tín hiệu là list float, mono) ---
def n_of(seconds: float) -> int:
    return int(round(seconds * RATE))


def white(rng: random.Random, n: int) -> list:
    return [rng.uniform(-1.0, 1.0) for _ in range(n)]


def biquad(x: list, kind: str, f0: float, q: float = 0.707) -> list:
    """Bộ lọc RBJ: 'lp' thông thấp, 'hp' thông cao, 'bp' thông dải (đỉnh 0 dB)."""
    f0 = min(f0, RATE * 0.45)
    w0 = 2.0 * math.pi * f0 / RATE
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    if kind == 'lp':
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    elif kind == 'hp':
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    elif kind == 'bp':
        b0, b1, b2 = alpha, 0.0, -alpha
    else:
        raise ValueError(kind)
    a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        out = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[i] = out
        x2, x1 = x1, v
        y2, y1 = y1, out
    return y


def tone(freq: float, tau: float, amp: float = 1.0, phase: float = 0.0, glide_from: float = None,
         glide_tau: float = 0.01, mod_hz: float = 0.0, mod_depth: float = 0.0) -> list:
    """Sóng sin tắt dần theo exp(-t/tau). `glide_from`: tần số bắt đầu, tụt về `freq` với hằng số `glide_tau` (gót giày, thân trầm).
    `mod_hz`/`mod_depth`: rung biên độ (lò xo). Dừng khi biên độ dưới -80 dB."""
    n = n_of(tau * 9.2)
    out = [0.0] * n
    two_pi = 2.0 * math.pi
    ph = phase
    dec = math.exp(-1.0 / (tau * RATE))
    a = amp
    for i in range(n):
        if glide_from is None:
            ph_inc = two_pi * freq / RATE
        else:
            f = freq + (glide_from - freq) * math.exp(-i / (glide_tau * RATE))
            ph_inc = two_pi * f / RATE
        ph += ph_inc
        v = a * math.sin(ph)
        if mod_depth:
            v *= 1.0 + mod_depth * math.sin(two_pi * mod_hz * i / RATE)
        out[i] = v
        a *= dec
    return out


def burst(rng: random.Random, tau: float, amp: float = 1.0, lo: float = None, hi: float = None) -> list:
    """Xung nhiễu ngắn, tắt exp(-t/tau); `hi` = thông cao (lấy phần chói), `lo` = thông thấp (phần đục)."""
    n = n_of(tau * 7.0)
    x = white(rng, n)
    if hi:
        x = biquad(x, 'hp', hi, 0.707)
    if lo:
        x = biquad(x, 'lp', lo, 0.707)
    dec = math.exp(-1.0 / (tau * RATE))
    a = amp
    for i in range(n):
        x[i] *= a
        a *= dec
    return x


def mix(dst: list, src: list, at: float = 0.0, gain: float = 1.0):
    """Cộng `src` vào `dst` từ giây `at` (mở rộng dst nếu cần)."""
    start = n_of(at)
    need = start + len(src)
    if need > len(dst):
        dst.extend([0.0] * (need - len(dst)))
    for i, v in enumerate(src):
        dst[start + i] += v * gain


def metal_ring(rng: random.Random, f0: float, amps: tuple, taus: tuple, spread: float = 0.03) -> list:
    """Chùm sóng sin tắt dần với tỉ số tần số KHÔNG điều hoà (kiểu thanh/ống kim loại, mỗi lần jitter nhẹ): nghe là kim loại, không phải đàn."""
    ratios = (1.0, 2.32, 3.87, 5.51, 7.20)
    out = []
    for k, (a, tau) in enumerate(zip(amps, taus)):
        r = ratios[k] * (1.0 + rng.uniform(-spread, spread))
        mix(out, tone(f0 * r, tau, a, rng.uniform(0, 2 * math.pi)))
    return out


def metal_hit(rng: random.Random, f0: float, body_hz: float, body_tau: float, ring_amps: tuple, ring_taus: tuple,
              noise_tau: float = 0.0012, noise_amp: float = 0.8, body_amp: float = 0.8) -> list:
    """Một cú va kim loại: xung nhiễu chói + thân trầm + chùm cộng hưởng."""
    out = []
    mix(out, burst(rng, noise_tau, noise_amp, hi=2500.0))
    mix(out, tone(body_hz, body_tau, body_amp, glide_from=body_hz * 1.5, glide_tau=body_tau * 0.5))
    mix(out, metal_ring(rng, f0, ring_amps, ring_taus))
    return out


def friction(rng: random.Random, dur: float, cf0: float, cf1: float, q: float = 1.0, depth: float = 0.5, mod_hz: float = 110.0,
             amp: float = 1.0, shape: str = 'bell') -> list:
    """Ma sát kim loại trượt: nhiễu thông dải đổi dần từ `cf0` sang `cf1`, biên độ dính-trượt ở `mod_hz`, bao dạng chuông / dốc lên / dốc xuống."""
    n = n_of(dur)
    noise = white(rng, n)
    a = biquad(noise, 'bp', cf0, q)
    b = biquad(noise, 'bp', cf1, q)
    ph = rng.uniform(0, 2 * math.pi)
    # biên độ nhấp nhô chậm: nhiễu thông thấp 25 Hz
    wob = biquad(white(rng, n), 'lp', 25.0, 0.7)
    peak = max(1e-9, max(abs(v) for v in wob))
    out = [0.0] * n
    for i in range(n):
        u = i / n
        s = u                                                    # trộn dần dải 0 -> dải 1
        v = (1 - s) * a[i] + s * b[i]
        if shape == 'bell':
            e = math.sin(math.pi * u) ** 2
        elif shape == 'rise':
            e = u ** 1.3
        else:
            e = (1 - u) ** 1.3
        stick = 1.0 - depth * (0.5 + 0.5 * math.sin(2 * math.pi * mod_hz * i / RATE + ph))
        out[i] = v * e * stick * (1.0 + 0.35 * wob[i] / peak) * amp
    return out


def finish(x: list, peak: float) -> list:
    """Bỏ thành phần một chiều, mở đầu từ 0, mờ cuối, chuẩn hoá đỉnh về `peak` (0..1 thang đầy)."""
    x = biquad(x, 'hp', 35.0, 0.707)
    top = max(abs(v) for v in x)
    last = max((i for i, v in enumerate(x) if abs(v) > top * TAIL_CUT), default=len(x) - 1)     # bỏ đuôi im (sin tắt dần dài)
    x = x[:min(len(x), last + 1 + n_of(0.004))]
    n = len(x)
    fi, fo = min(n_of(FADE_IN), n), min(n_of(FADE_OUT), n)
    for i in range(fi):
        x[i] *= i / fi
    for i in range(fo):
        x[n - 1 - i] *= 0.5 * (1.0 - math.cos(math.pi * i / fo)) if fo > 1 else 0.0
    x[-1] = 0.0
    top = max(abs(v) for v in x)
    k = peak / top if top > 0 else 0.0
    return [v * k for v in x]


# --- công thức từng loại tiếng (mỗi hàm nhận rng, trả mono chưa chuẩn hoá) ---
def mag_release(rng):
    """Bấm chốt băng: tách kim loại + lò xo chốt bật lại."""
    out = metal_hit(rng, rng.uniform(3400, 4300), rng.uniform(380, 520), 0.005, (0.9, 0.5, 0.3), (0.008, 0.006, 0.004))
    mix(out, metal_hit(rng, rng.uniform(2400, 3000), 600, 0.004, (0.5, 0.3), (0.006, 0.004), noise_amp=0.4), rng.uniform(0.008, 0.012), 0.55)
    return out


def mag_out(rng):
    """Băng đạn trượt ra khỏi cổng băng + lò xo trong băng lạch cạch."""
    out = friction(rng, rng.uniform(0.13, 0.16), rng.uniform(2800, 3400), rng.uniform(3600, 4400), 1.1, 0.55, rng.uniform(85, 125), 0.75, 'bell')
    end = 0.15
    mix(out, metal_hit(rng, rng.uniform(2000, 2500), 310, 0.010, (0.55, 0.3, 0.2), (0.030, 0.02, 0.014), body_amp=0.5), end, 0.8)
    for _ in range(rng.randint(3, 4)):                                   # lò xo: vài tiếng ting nhỏ
        mix(out, tone(rng.uniform(4800, 7200), rng.uniform(0.006, 0.010), rng.uniform(0.12, 0.22)), end + rng.uniform(0.01, 0.12))
    return out


def mag_in(rng):
    """Băng đạn trượt vào cổng băng (nhẹ hơn lúc rút) rồi chạm đáy."""
    out = friction(rng, rng.uniform(0.11, 0.14), rng.uniform(2300, 2800), rng.uniform(3200, 3900), 1.1, 0.5, rng.uniform(95, 140), 0.55, 'rise')
    mix(out, metal_hit(rng, rng.uniform(2600, 3200), 380, 0.007, (0.5, 0.3), (0.015, 0.010), body_amp=0.45, noise_amp=0.5), n_of(0.12) / RATE - 0.01, 0.7)
    return out


def mag_seat(rng):
    """Băng đạn vào chỗ: cú 'cạch' nặng + chốt băng ăn khớp."""
    out = metal_hit(rng, rng.uniform(1500, 1900), rng.uniform(230, 290), 0.014, (0.85, 0.62, 0.42, 0.26), (0.034, 0.026, 0.018, 0.012), 0.0018, 1.0, 0.9)
    mix(out, tone(rng.uniform(480, 560), 0.014, 0.55, glide_from=700, glide_tau=0.006))
    mix(out, metal_hit(rng, rng.uniform(3300, 3900), 700, 0.005, (0.7, 0.4, 0.25), (0.010, 0.007, 0.005), noise_amp=0.5), rng.uniform(0.020, 0.026), 0.55)
    return out


def mag_tap(rng):
    """Vỗ băng cho chắc: cạch nhỏ."""
    return metal_hit(rng, rng.uniform(2200, 2700), rng.uniform(300, 360), 0.008, (0.5, 0.32, 0.2), (0.025, 0.018, 0.012), 0.001, 0.7, 0.6)


def bolt_release(rng):
    """Nhả khoá nòng: bolt đập về trước 'CẠCH' lớn + lò xo hồi vị rung + nảy lại."""
    out = metal_hit(rng, rng.uniform(1050, 1300), rng.uniform(190, 230), 0.022, (0.85, 0.65, 0.45, 0.30), (0.050, 0.038, 0.028, 0.020), 0.0030, 1.0, 0.9)
    mix(out, tone(rng.uniform(560, 700), 0.020, 0.7, glide_from=900, glide_tau=0.008))
    for f, a in ((rng.uniform(780, 860), 0.30), (rng.uniform(1280, 1420), 0.22), (rng.uniform(2150, 2350), 0.14)):     # lò xo hồi vị: rung biên độ ~40 Hz
        mix(out, tone(f, 0.07, a, mod_hz=rng.uniform(34, 44), mod_depth=0.6), 0.004)
    mix(out, metal_hit(rng, rng.uniform(2200, 2800), 420, 0.007, (0.5, 0.3, 0.2), (0.025, 0.018, 0.012), noise_amp=0.4), rng.uniform(0.034, 0.042), 0.5)
    return out


def bolt_tick(rng):
    """Gạt chốt / nhấn bolt: cạch nhẹ, hai nhịp sát nhau."""
    out = metal_hit(rng, rng.uniform(1800, 2300), rng.uniform(240, 290), 0.010, (0.6, 0.4, 0.25), (0.040, 0.030, 0.020), 0.0012, 0.8, 0.6)
    mix(out, metal_hit(rng, rng.uniform(3000, 3800), 500, 0.004, (0.6, 0.3), (0.008, 0.005), noise_amp=0.4), rng.uniform(0.012, 0.018), 0.5)
    return out


def draw_a(rng):
    """Rút súng, tay chạm: dây đeo / kim loại cọ nhẹ."""
    out = friction(rng, rng.uniform(0.18, 0.24), rng.uniform(1900, 2400), rng.uniform(2600, 3300), 0.9, 0.6, rng.uniform(70, 100), 0.55, 'bell')
    mix(out, tone(rng.uniform(1700, 2000), 0.020, 0.30), 0.0)
    mix(out, tone(rng.uniform(3900, 4600), 0.012, 0.16), rng.uniform(0.02, 0.05))
    return out


def draw_b(rng):
    """Súng vào vị trí: cạch nhẹ."""
    return metal_hit(rng, rng.uniform(1900, 2300), rng.uniform(260, 320), 0.008, (0.55, 0.35, 0.2), (0.022, 0.016, 0.010), 0.0010, 0.5, 0.5)


def settle(rng):
    """Huỷ nạp: tay đẩy súng về, kim loại lạch cạch nhẹ."""
    out = metal_hit(rng, rng.uniform(2800, 3400), 420, 0.006, (0.7, 0.4), (0.010, 0.007), noise_amp=0.5, body_amp=0.5)
    mix(out, friction(rng, 0.08, 2200, 3000, 1.0, 0.5, 100.0, 0.45, 'bell'), 0.015)
    mix(out, metal_hit(rng, rng.uniform(2200, 2700), 320, 0.008, (0.5, 0.3, 0.2), (0.020, 0.014, 0.010), noise_amp=0.5, body_amp=0.5), rng.uniform(0.085, 0.105), 0.7)
    return out


def _tile_tick(rng, amp: float, f_lo: float = 1700.0, f_hi: float = 3600.0, tau_lo: float = 0.005, tau_hi: float = 0.011) -> list:
    """'Tách' nhỏ của viên gạch: hai thành phần cộng hưởng cao."""
    f1 = rng.uniform(f_lo, f_hi)
    out = []
    mix(out, tone(f1, rng.uniform(tau_lo, tau_hi), amp, rng.uniform(0, 6.28)))
    mix(out, tone(f1 * rng.uniform(1.45, 1.75), rng.uniform(tau_lo, tau_hi) * 0.8, amp * 0.55, rng.uniform(0, 6.28)), rng.uniform(0.0, 0.0008))
    return out


def _step(rng, running: bool) -> list:
    """Một bước giày đế cứng trên gạch: gót chạm -> đế cọ -> mũi giày hạ xuống (gót gõ chắc + tách nhỏ + cọ nhẹ)."""
    heel = rng.uniform(165, 240)       # loa laptop gần như không phát dưới ~150 Hz nên thân gót đặt cao hơn một chút
    gain = 1.0 if not running else 1.2
    out = []
    mix(out, tone(heel, 0.020, 0.85 * gain, glide_from=heel * 1.8, glide_tau=0.008))              # gót: thân trầm tụt tần nhanh
    knock = biquad(white(rng, n_of(0.05)), 'bp', rng.uniform(650, 950), 1.0)                       # tiếng gõ chắc của gót cứng (dải giữa)
    mix(out, [v * math.exp(-i / (0.0065 * RATE)) * 1.6 * gain for i, v in enumerate(knock)])
    mix(out, burst(rng, 0.0012, 0.55, hi=3000.0))                                                  # đế cứng chạm: xung chói rất ngắn
    mix(out, tone(rng.uniform(380, 520), 0.045, 0.16 * gain, rng.uniform(0, 6.28)), 0.0008)       # gạch rỗng nhẹ cộng hưởng
    mix(out, _tile_tick(rng, 0.65 * gain), 0.0)
    scuff = friction(rng, rng.uniform(0.07, 0.10), rng.uniform(2400, 3200), rng.uniform(3600, 4800), 0.7, 0.35, rng.uniform(110, 160),
                     0.26 if not running else 0.38, 'bell')
    mix(out, scuff, 0.018)
    toe = rng.uniform(0.075, 0.100) if not running else rng.uniform(0.050, 0.068)                 # mũi giày hạ xuống
    mix(out, tone(heel * 1.5, 0.012, 0.36 * gain, glide_from=heel * 2.4, glide_tau=0.005), toe)
    mix(out, burst(rng, 0.004, 0.30 * gain, lo=2200.0), toe)
    mix(out, _tile_tick(rng, 0.20 * gain, 2000.0, 3800.0, 0.004, 0.008), toe + 0.0005)
    return out


def step_walk(rng):
    return _step(rng, False)


def step_run(rng):
    return _step(rng, True)


def land(rng):
    """Chạm đất sau khi nhảy: hai chân gần như cùng lúc, bịch nặng + gạch dội + cọ."""
    base = rng.uniform(105, 140)
    out = []
    mix(out, tone(base, 0.045, 1.0, glide_from=base * 2.0, glide_tau=0.014))
    mix(out, tone(base * 1.15, 0.040, 0.8, glide_from=base * 2.2, glide_tau=0.012), rng.uniform(0.014, 0.022))
    mix(out, burst(rng, 0.010, 0.9, lo=1100.0))
    mix(out, burst(rng, 0.0015, 0.6, hi=3000.0))
    mix(out, tone(rng.uniform(240, 300), 0.090, 0.28, rng.uniform(0, 6.28)), 0.001)
    mix(out, _tile_tick(rng, 0.65), 0.0)
    mix(out, _tile_tick(rng, 0.45), rng.uniform(0.014, 0.022))
    mix(out, friction(rng, 0.11, 2500, 3600, 0.7, 0.35, 130.0, 0.30, 'bell'), 0.03)
    mix(out, burst(rng, 0.080, 0.28, lo=280.0), 0.004)                          # đuôi trầm
    return out


def jump(rng):
    """Nhảy lên: đế đẩy khỏi sàn, cọ ngắn và một tiếng gõ nhỏ."""
    out = friction(rng, rng.uniform(0.06, 0.08), rng.uniform(2200, 2800), rng.uniform(3200, 4000), 0.8, 0.4, 120.0, 0.55, 'bell')
    h = rng.uniform(130, 170)
    mix(out, tone(h, 0.012, 0.50, glide_from=h * 1.7, glide_tau=0.005), 0.004)
    mix(out, burst(rng, 0.004, 0.35, lo=1800.0), 0.004)
    mix(out, _tile_tick(rng, 0.25), 0.005)
    return out


# tên -> (số biến thể, công thức, đỉnh sau chuẩn hoá). Tên file: <tên>_<số>.wav
SOUNDS = {
    'mag_release': (2, mag_release, 0.80),
    'mag_out': (2, mag_out, 0.85),
    'mag_in': (2, mag_in, 0.80),
    'mag_seat': (2, mag_seat, 0.90),
    'mag_tap': (2, mag_tap, 0.75),
    'bolt_release': (2, bolt_release, 0.95),
    'bolt_tick': (2, bolt_tick, 0.80),
    'draw_a': (2, draw_a, 0.70),
    'draw_b': (2, draw_b, 0.70),
    'settle': (2, settle, 0.75),
    'step_walk': (5, step_walk, 0.85),
    'step_run': (5, step_run, 0.90),
    'land': (4, land, 0.95),
    'jump': (3, jump, 0.80),
}


def seed_of(name: str, index: int) -> int:
    return zlib.crc32(f'{name}:{index}'.encode('utf-8'))


def render(name: str, index: int) -> list:
    """Mono float, đã chuẩn hoá: cùng (name, index) thì luôn ra cùng kết quả."""
    variants, recipe, peak = SOUNDS[name]
    rng = random.Random(seed_of(name, index))
    return finish(recipe(rng), peak)


def to_pcm(x: list) -> array.array:
    """Float (-1..1) -> 16 bit, 2 kênh giống nhau xen kẽ."""
    out = array.array('h')
    for v in x:
        s = max(-32767, min(32767, int(round(v * 32767))))
        out.append(s)
        out.append(s)
    return out


def write_wav(path: Path, x: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(to_pcm(x).tobytes())


def build_all(out_dir: Path) -> list:
    paths = []
    for name, (variants, _, _) in SOUNDS.items():
        for i in range(variants):
            p = out_dir / f'{name}_{i}.wav'
            write_wav(p, render(name, i))
            paths.append(p)
    return paths


# --- đo gián tiếp (không nghe được loa) ---
BANDS = (100, 200, 400, 800, 1600, 3200, 6400, 12800)      # tâm các dải đo năng lượng (Hz)


def read_mono(path: Path) -> tuple:
    with wave.open(str(path), 'rb') as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = array.array('h')
        raw.frombytes(w.readframes(n))
    return [raw[i * ch] / 32768.0 for i in range(n)], dict(channels=ch, width=width, rate=rate, frames=n)


def band_energy(x: list, freq: float) -> float:
    """Năng lượng qua bộ lọc thông dải một quãng tám (Q=1,4) quanh `freq`: so được tiếng ngắn (tách) với tiếng dài (sin tắt chậm)."""
    return sum(v * v for v in biquad(x, 'bp', freq, 1.4))


def analyze(path: Path) -> dict:
    """Số đo: độ dài, đỉnh, RMS, mẫu đầu/cuối, DC, số mẫu chạm trần, thời gian lên đỉnh, thời gian tắt xuống -40 dB so với đỉnh, trọng tâm phổ."""
    x, fmt = read_mono(path)
    n = len(x)
    peak = max(abs(v) for v in x)
    rms = math.sqrt(sum(v * v for v in x) / n)
    win = n_of(0.005)
    levels = []
    for i in range(0, n - win + 1, win):
        seg = x[i:i + win]
        levels.append(math.sqrt(sum(v * v for v in seg) / win))
    top = max(levels)
    peak_win = levels.index(top)
    last_loud = max((i for i, v in enumerate(levels) if v > top * 0.01), default=peak_win)
    attack = next((i for i, v in enumerate(levels) if v >= 0.9 * top), 0)
    band_power = [band_energy(x, f) for f in BANDS]
    total = sum(band_power) or 1.0
    centroid = sum(f * p for f, p in zip(BANDS, band_power)) / total
    return dict(fmt=fmt, seconds=n / RATE, peak=peak, rms=rms, first=abs(x[0]), last=abs(x[-1]), dc=sum(x) / n,
                clipped=sum(1 for v in x if abs(v) >= 32767 / 32768.0), attack_ms=attack * 5.0 + 2.5,
                t40_ms=(last_loud + 1) * 5.0 - 5.0 * peak_win, centroid=centroid,
                bands=[10 * math.log10(p / total + 1e-12) for p in band_power])


def report(paths: list):
    print(f"{'file':20s} {'dài s':>6s} {'đỉnh':>6s} {'RMS dB':>7s} {'đầu':>7s} {'cuối':>7s} {'lên ms':>6s} {'tắt-40dB ms':>11s} {'trọng tâm Hz':>12s}  năng lượng dải (dB) " + ' '.join(f'{b:>5d}' for b in BANDS))
    for p in paths:
        a = analyze(p)
        print(f"{p.name:20s} {a['seconds']:6.3f} {a['peak']:6.3f} {20 * math.log10(a['rms'] + 1e-9):7.1f} {a['first']:7.4f} {a['last']:7.4f} "
              f"{a['attack_ms']:6.1f} {a['t40_ms']:11.0f} {a['centroid']:12.0f}  {' ' * 19}" + ' '.join(f'{b:5.0f}' for b in a['bands']))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    out_dir = ROOT / 'sounds' / 'foley'
    if '--out' in args:
        out_dir = Path(args[args.index('--out') + 1])
    paths = build_all(out_dir)
    total = sum(p.stat().st_size for p in paths)
    print(f'đã dựng {len(paths)} file vào {out_dir} ({total / 1024:.0f} KB)')
    if '--check' in args:
        report(paths)
