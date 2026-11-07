r"""G8: FPS of a gun in the real game (vsync off, 1366x768): standing, aimed, firing, reloading (G12: + under the water, looking up, half under). Prints average / worst FPS of each scene (threshold 55).

Run: .venv\Scripts\python.exe -X utf8 tools\measure\g8_perf.py [--gun glock|m4]
"""
import argparse
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, held_keys, mouse, time  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='glock')
ap.add_argument('--map', default='pool', choices=('pool', 'flat'), help='pool = phòng hồ bơi (G9); flat = nền phẳng cũ để so')
ap.add_argument('--level', type=int, default=-1, help='mức đồ hoạ 0 Thấp / 1 Vừa / 2 Cao (mặc định: như game)')
ap.add_argument('--trace', action='store_true', help='in thời gian từng khung của giây đầu (tìm chỗ giật lúc mở game)')
ap.add_argument('--size', default='1366x768')
ap.add_argument('--weak', action='store_true', help='đo riêng ms GPU (bộ đếm OpenGL) và ms CPU, quy đổi ra máy yếu (UHD 620): GPU x4, CPU x2; đạt khi trung bình >= 60 và 1%% thấp >= 50')
ap.add_argument('--passes', action='store_true', help='cùng --weak: in ms GPU của từng lượt vẽ (buffer#vùng)')
ap.add_argument('--vsync', action='store_true', help='bật vsync như game thật (số FPS bị chặn 60; dùng để xem giật thật, và với --weak: GPU không bị dồn hàng)')
ap.add_argument('--borderless', action='store_true', help='cửa sổ không viền như run.bat (nên dùng cùng --size bằng cỡ màn hình)')
ap.add_argument('--json', default='', help='cùng --weak: ghi số GPU / CPU từng cảnh ra file (tools/measure/weak_pc.py đọc)')
ap.add_argument('--gpu-factor', type=float, default=4.0)
ap.add_argument('--cpu-factor', type=float, default=2.0)
ap.add_argument('--at', default='', help='x,z,yaw: đứng chỗ khác chỗ xuất phát (vd 3,5,75 = giữa vệt nắng nhìn về mặt trời)')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
game = create_game(vsync=args.vsync, borderless=args.borderless, size=(W, H), sound=False, draw=False, gun=args.gun, map_name=args.map)
if args.level >= 0:
    game.set_graphics(args.level, announce=False)
if args.at:                                                   # e.g. --at 3,5,75: inside the sun beams looking at the sun (shafts + dust + water: the heaviest view)
    ax, az, ayaw = (float(v) for v in args.at.split(','))
    game.player.x, game.player.z, game.player.yaw = ax, az, ayaw
    game.player._apply_view()
print(f'mức đồ hoạ: {game.graphics_level}, cửa sổ {W}x{H}' + (f', đứng ở {args.at}' if args.at else ''))
mouse.locked = False
game.combat.require_locked_mouse = False
timer = None
if args.weak or args.passes:
    from tools.measure.gpu_timer import GpuTimer
    from ursina import application
    timer = GpuTimer()
    timer.hook(application.base.graphicsEngine)


def pct(v, q):
    v = sorted(v)
    return v[min(int(len(v) * q), len(v) - 1)] if v else 0.0


results = {}


def weak_report(name, frames):
    frames = frames[3:]
    # Windows' GPU scheduler: a GPU that is queued up (vsync off, faster than the display) is sometimes held off ~10.5 ms inside a pass
    # (gpu_timer.py docstring). Such frames are counted and left out; a GPU-bound weak machine at its own pace is not measured by them.
    if frames:                                         # frames measured before a new output got its callbacks (the lens rebuilds on a level change) miss passes: drop them
        full = max(len(f['passes']) for f in frames)
        frames = [f for f in frames if len(f['passes']) == full]
        med = sorted(f['busy_ms'] for f in frames)[len(frames) // 2]
        held = [f for f in frames if f['busy_ms'] > med + 8.0]
        frames = [f for f in frames if f['busy_ms'] <= med + 8.0]
    if not frames:
        print(f'{name:14s} (không có số GPU)')
        return
    g = [f['gpu_ms'] for f in frames]
    cp = [f['cpu_ms'] for f in frames]
    est = [max(args.gpu_factor * a, args.cpu_factor * b) for a, b in zip(g, cp)]
    results[name] = {'gpu_avg': sum(g) / len(g), 'gpu_p99': pct(g, 0.99), 'cpu_avg': sum(cp) / len(cp), 'cpu_p99': pct(cp, 0.99),
                     'held': len(held), 'frames': len(frames), 'passes': {k: sum(f['passes'].get(k, 0.0) for f in frames) / len(frames) for k in frames[0]['passes']}}
    avg = 1000.0 / (sum(est) / len(est))
    low = 1000.0 / pct(est, 0.99)
    ok = avg >= 60.0 and low >= 50.0
    sp = [f['span_ms'] for f in frames]
    print(f'{name:14s} GPU {sum(g) / len(g):5.2f} ms (99% {pct(g, 0.99):5.2f}, span 99% {pct(sp, 0.99):5.2f}) | CPU {sum(cp) / len(cp):5.2f} ms (99% {pct(cp, 0.99):5.2f})'
          f' | máy yếu ~ {avg:5.1f} FPS, 1% thấp {low:5.1f}  {"ĐẠT" if ok else "TRƯỢT"}  (bỏ {len(held)} khung GPU bị giữ, hở {frames[0]["gap_ms"]:.2f} ms)')
    if args.passes:
        per = {}
        for f in frames:
            for k, v in f['passes'].items():
                per.setdefault(k, []).append(v)
        for k, v in sorted(per.items(), key=lambda kv: -sum(kv[1])):
            if sum(v) / len(frames) >= 0.02:
                print(f'      {k:28s} {sum(v) / len(frames):6.2f} ms (99% {pct(v, 0.99):6.2f})')
c = game.combat
dts = []


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        dts.append(time.dt)
        try:
            next(self.gen)
        except StopIteration:
            if args.json:
                import json
                Path(args.json).write_text(json.dumps({'size': [W, H], 'level': game.graphics_level, 'scenes': results}, ensure_ascii=False, indent=1), encoding='utf-8')
            sys.exit(0)

    def scene(self, name, seconds, setup=None):
        if setup:
            setup()
        dts.clear()
        if timer:
            timer.take()
        t0 = pytime.time()
        while pytime.time() - t0 < seconds:
            yield
        if args.trace and name == 'khởi động':
            print('   từng khung (ms):', [round(x * 1000) for x in dts])
        d = sorted(dts[5:])
        avg = len(d) / max(sum(d), 1e-9)
        worst = 1.0 / max(d) if d else 0
        low1 = 1.0 / d[int(len(d) * 0.99)] if d else 0
        if timer:
            weak_report(name, timer.take())
        print(f'{name:14s} trung bình {avg:6.1f} FPS | 1% thấp {low1:6.1f} | tệ nhất {worst:6.1f}  {"ĐẠT" if avg >= 55 else "TRƯỢT"}')

    def run(self):
        yield from self.scene('khởi động', 1.0)
        yield from self.scene('đứng yên', 3.0)
        yield from self.scene('ngắm', 3.0, lambda: held_keys.__setitem__('right mouse', 1))
        held_keys['right mouse'] = 0

        def fire():
            c.weapon.auto = True
            c.weapon.mag = c.weapon.mag_size
            held_keys['left mouse'] = 1
        yield from self.scene('bắn liên tục', 3.0, fire)
        held_keys['left mouse'] = 0
        yield from self.scene('nạp đạn', 2.6, lambda: (setattr(c.weapon, 'mag', 3), c.request_reload()))
        yield from self.scene('chạy nước rút', 3.0, lambda: (held_keys.__setitem__('w', 1), held_keys.__setitem__('shift', 1)))
        held_keys['w'] = held_keys['shift'] = 0
        if game.pool:                                         # G12: on the deep floor, head under the water (basin mesh + underwater fog), then the split frame at the surface
            pl = game.player

            def put(x, y, z, yaw, pitch=0.0):
                def go():
                    pl.x, pl.y, pl.z, pl.yaw, pl.pitch = x, y, z, yaw, pitch
                    pl.vx = pl.vz = pl.vy = 0.0
                    pl._apply_view()
                return go
            yield from self.scene('dưới nước', 3.0, put(0.0, -2.12, 10.0, 180.0))
            yield from self.scene('nhìn lên mặt nước', 3.0, put(0.0, -2.12, 9.0, 160.0, -55.0))
            yield from self.scene('nửa chìm', 3.0, put(0.0, -1.80, 3.87, 0.0))


Script()
game.app.run()
