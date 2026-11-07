r"""Estimated FPS on a weak laptop (Intel UHD 620 + 8th-gen i5, the user's target 2026-11-07) from two real runs of the game on THIS machine.

1) GPU: g8_perf.py --weak at the full screen size (1920x1080 borderless, vsync off): GPU ms of every scene from OpenGL timestamps (gpu_timer.py).
2) CPU: the same scenes in a tiny 640x360 window, where the GPU is idle enough that the driver never makes the CPU wait: CPU ms of Python + cull + draw submission
   (at full size the draw submission blocks on a queued-up GPU and the CPU number becomes GPU time again).
Weak machine frame = max(GPU x 4, CPU x 2): the UHD 620 is 2.5-3.5x slower than this Iris Xe 96 EU (Time Spy 361 vs 1282, G3D 1040 vs 2593), an
i5-8250U about half of a Core 7 150U per thread; Panda overlaps CPU and GPU, hence max. Pass: average >= 60 FPS and 1% low (99th percentile) >= 50 FPS in every scene.

Run (plugged in, nothing else heavy running; one game at a time):
  .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\weak_pc.py [--level 0] [--gun glock]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')

ap = argparse.ArgumentParser()
ap.add_argument('--level', type=int, default=0)
ap.add_argument('--gun', default='glock')
ap.add_argument('--size', default='', help='cỡ cho lượt đo GPU (mặc định: cỡ màn hình)')
ap.add_argument('--gpu-factor', type=float, default=4.0)
ap.add_argument('--cpu-factor', type=float, default=2.0)
ap.add_argument('--passes', action='store_true', help='in ms GPU của từng lượt vẽ')
args = ap.parse_args()


def screen():
    sys.path.insert(0, str(ROOT))
    from screeninfo import get_monitors
    m = next((m for m in get_monitors() if m.is_primary), get_monitors()[0])
    return f'{m.width}x{m.height}'


def run(size, borderless, out):
    cmd = [sys.executable, '-X', 'utf8', str(ROOT / 'tools' / 'measure' / 'g8_perf.py'), '--weak', '--level', str(args.level), '--gun', args.gun,
           '--size', size, '--json', str(out)] + (['--borderless'] if borderless else [])
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 or not out.exists():
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(f'g8_perf.py lỗi ({size})')
    return json.loads(out.read_text(encoding='utf-8'))


size = args.size or screen()
tmp = Path(tempfile.mkdtemp())
print(f'lượt 1/2: GPU ở {size} (không viền), mức {args.level}')
gpu = run(size, True, tmp / 'gpu.json')
print('lượt 2/2: CPU ở 640x360')
cpu = run('640x360', False, tmp / 'cpu.json')
gf, cf = args.gpu_factor, args.cpu_factor
print(f'\nmáy yếu = max(GPU x {gf:g}, CPU x {cf:g}); đạt khi trung bình >= 60 và 1% thấp >= 50')
all_ok = True
for name, g in gpu['scenes'].items():
    c = cpu['scenes'].get(name)
    if c is None:
        continue
    avg = 1000.0 / max(gf * g['gpu_avg'], cf * c['cpu_avg'])
    low = 1000.0 / max(gf * g['gpu_p99'], cf * c['cpu_p99'])
    ok = avg >= 60.0 and low >= 50.0
    all_ok &= ok
    print(f'{name:18s} GPU {g["gpu_avg"]:5.2f} ms (99% {g["gpu_p99"]:5.2f}) | CPU {c["cpu_avg"]:5.2f} ms (99% {c["cpu_p99"]:5.2f})'
          f' -> ~{avg:5.1f} FPS, 1% thấp {low:5.1f}  {"ĐẠT" if ok else "TRƯỢT"}' + (f'  ({g["held"]} khung GPU bị Windows giữ, bỏ)' if g['held'] else ''))
    if args.passes:
        for k, v in sorted(g['passes'].items(), key=lambda kv: -kv[1]):
            if v >= 0.02:
                print(f'      {k:30s} {v:6.2f} ms')
print('\nKẾT QUẢ:', 'ĐẠT mọi cảnh' if all_ok else 'TRƯỢT')
sys.exit(0 if all_ok else 1)
