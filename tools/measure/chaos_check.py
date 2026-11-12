r"""Chaos check (G16): drive the REAL game with random input and abuse for a while and check it never breaks (docs/sessions/G16.md, skill game-stability-qa).

What it does, with a fixed random seed (a failure can be replayed):
- presses / releases keys and mouse buttons through Ursina's own input path (WASD, Shift, Ctrl, C, Space, R, B, 1, 2, Esc, F1, F2, left / right mouse),
  turns the view, switches guns in the middle of reloads, opens and closes the panels;
- every ~20 s freezes one frame for 0.3-2 s (a hitch: window drag, antivirus, a slow disk);
- every ~25 s minimises the window for real (WinAPI) and brings it back (Alt+Tab / minimise, G16 D1).
Checks every frame: no exception; player and camera finite and inside the room; rounds within the magazine; the gun never hidden > 4 s outside a switch;
hands never busy > 10 s; while in the background: no key held, sound muted, mouse free; back in front: sound and mouse capture restored.
Samples every 5 s: private memory of the process, Panda node count, Ursina entity count (growth over a long run = a leak, E1 / E2).

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\chaos_check.py [--seconds 60] [--seed 1] [--gun m4|glock]
     long run: --seconds 600 (memory growth is judged only from 300 s up). Exit code 1 on any failure.
"""
import argparse
import ctypes
import math
import random
import sys
import time as pytime
import traceback
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

import fps.app as app_mod  # noqa: E402
from main import create_game  # noqa: E402
from ursina import application, camera, held_keys, mouse, scene  # noqa: E402
from ursina import time as utime  # noqa: E402

from fps.weapon_data import MapData  # noqa: E402

HOLD_KEYS = ('w', 'a', 's', 'd', 'shift', 'control', 'c', 'mouse1', 'mouse3')
TAP_KEYS = ('space', 'r', 'b', '1', '2')
RAW = set('1234567890qwertyuiopasdfghjklzxcvbnm')


def private_mb() -> float:
    class PMC(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    gpmi = ctypes.windll.psapi.GetProcessMemoryInfo
    gpmi.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    gpmi(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PrivateUsage / 2 ** 20


class Chaos:
    def __init__(self, game, seconds: float, seed: int):
        self.g, self.seconds, self.rng = game, seconds, random.Random(seed)
        self.app = application.base
        self.t = 0.0
        self.down = set()
        self.failures = []
        self.notes = []
        self.dts = []                     # frame times outside injected hitches (s)
        self.spikes = []                  # (t, dt, recent actions) of frames > 100 ms outside injected hitches
        self.recent = []                  # last few actions, to say what came before a slow frame
        self.skip_until = 0.0             # stats ignore the frames right after an injected hitch / focus change
        self.next_hitch = 20.0
        self.next_focus = 25.0
        self.focus_phase = None           # None / ('down', t) / ('up', t)
        self.restore_volumes = None
        self.lock_before = None
        self.hidden_for = 0.0
        self.busy_for = 0.0
        self.panel_close_at = None
        self.samples = []                 # (t, private MB, nodes, entities)
        self.next_sample = 0.0
        self.counts = dict(keys=0, hitches=0, focus=0, switches=0, reloads=0, panels=0)
        self.room = MapData()
        self.hwnd = self.app.win.get_window_handle().get_int_handle()

    # ---------------------------------------------------------------- input through Ursina's own handlers
    def press(self, k):
        if k.startswith('mouse'):
            self.app.input(k)
        else:
            self.app.input(k, k in RAW)
        self.down.add(k)
        self.counts['keys'] += 1
        self.recent = (self.recent + [f'{self.t:.2f}:{k}'])[-4:]

    def release(self, k):
        if k.startswith('mouse'):
            self.app.input_up(k)
        else:
            self.app.input_up(k, k in RAW)
        self.down.discard(k)

    def tap(self, k):
        self.press(k)
        self.release(k)

    def drive(self, dt):
        r = self.rng
        g = self.g
        panel = g.debug.is_open or g.gfx_panel.is_open
        if panel:
            if self.panel_close_at is not None and self.t >= self.panel_close_at:
                self.tap('f2' if g.gfx_panel.is_open else 'f1')
                self.panel_close_at = None
            return
        for k in HOLD_KEYS:
            p_down = 0.03 if k == 'w' else 0.012
            p_up = 0.01 if k == 'w' else 0.03
            if k not in self.down and r.random() < p_down:
                self.press(k)
            elif k in self.down and r.random() < p_up:
                self.release(k)
        for k in TAP_KEYS:
            if r.random() < 0.006:
                if k in ('1', '2'):
                    self.counts['switches'] += 1
                if k == 'r':
                    self.counts['reloads'] += 1
                self.tap(k)
        if g.combat.handling.busy and r.random() < 0.01:          # switch / reload in the middle of a clip
            self.tap(r.choice(('1', '2', 'r')))
        if r.random() < 0.0015:
            for k in list(self.down):
                self.release(k)
            self.tap(r.choice(('f1', 'f2')))
            self.panel_close_at = self.t + r.uniform(0.3, 2.0)
            self.counts['panels'] += 1
        elif r.random() < 0.001 or (not mouse.locked and r.random() < 0.05):
            self.tap('escape')
        g.player.look(r.gauss(0.0, 0.004), r.gauss(0.0, 0.002))

    # ---------------------------------------------------------------- abuse
    def hitch(self):
        d = self.rng.uniform(0.3, 2.0)
        pytime.sleep(d)
        self.counts['hitches'] += 1
        self.skip_until = self.t + d + 0.5           # the NEXT frame carries the sleep in its dt

    def focus_step(self):
        u32 = ctypes.windll.user32
        g = self.g
        if self.focus_phase is None:
            if not g.focus.focused:           # someone else took the foreground (the machine is in use): keys never reach an unfocused window, skip this round
                self.notes.append(f'{self.t:.1f}s: cửa sổ game đang không có tiêu điểm (máy đang được dùng), bỏ một lượt thu nhỏ')
                return
            for k in list(self.down):
                self.down.discard(k)          # keys stay physically "held" from the game's view: the guard must let go of them
            base = application.base
            mgrs = [m for m in list(base.sfxManagerList) + [base.musicManager] if m is not None]
            self.restore_volumes = [(m, m.get_volume()) for m in mgrs]
            self.lock_before = mouse.locked
            self.press('w')                   # held while the window goes away: must not stay held
            u32.ShowWindow(self.hwnd, 6)      # SW_MINIMIZE
            self.focus_phase = ('down', self.t)
            self.counts['focus'] += 1
        elif self.focus_phase[0] == 'down' and self.t - self.focus_phase[1] > 1.0:
            if g.focus.focused:
                self.failures.append(f'{self.t:.1f}s: thu nhỏ cửa sổ mà game không nhận ra mất tiêu điểm')
            else:
                if any(v for v in held_keys.values()):
                    self.failures.append(f'{self.t:.1f}s: mất tiêu điểm mà còn phím đang giữ: {[k for k, v in held_keys.items() if v]}')
                for m, _ in self.restore_volumes:
                    if m.get_volume() > 1e-6:
                        self.failures.append(f'{self.t:.1f}s: mất tiêu điểm mà âm thanh chưa tắt')
                        break
                if mouse.locked:
                    self.failures.append(f'{self.t:.1f}s: mất tiêu điểm mà chuột vẫn bị giữ')
            self.down.discard('w')
            u32.ShowWindow(self.hwnd, 9)      # SW_RESTORE
            u32.keybd_event(0x12, 0, 0, 0)    # an Alt tap lets this process take the foreground back
            u32.keybd_event(0x12, 0, 2, 0)
            u32.SetForegroundWindow(self.hwnd)
            self.focus_phase = ('up', self.t)
        elif self.focus_phase[0] == 'up':
            if g.focus.focused and self.t - self.focus_phase[1] > 0.6:
                for m, v in self.restore_volumes:
                    if abs(m.get_volume() - v) > 1e-6:
                        self.failures.append(f'{self.t:.1f}s: quay lại mà âm lượng không về {v} (đang {m.get_volume()})')
                        break
                if self.lock_before and not mouse.locked:
                    self.failures.append(f'{self.t:.1f}s: quay lại mà chuột không được giữ lại')
                self.focus_phase = None
                self.skip_until = self.t + 0.5
            elif self.t - self.focus_phase[1] > 5.0:
                self.notes.append(f'{self.t:.1f}s: Windows không trả tiêu điểm cho cửa sổ (giới hạn của công cụ, không phải lỗi game)')
                self.focus_phase = None

    # ---------------------------------------------------------------- checks
    def check(self, dt):
        g, p = self.g, self.g.player
        vals = (p.x, p.y, p.z, p.yaw, p.pitch, p.vx, p.vy, p.vz)
        if not all(math.isfinite(v) for v in vals):
            self.failures.append(f'{self.t:.1f}s: vị trí / hướng nhìn không hữu hạn {vals}')
        from fps.core.poolmap import plan_bounds
        bx0, bx1, bz0, bz1 = plan_bounds(g.pool.pm) if g.pool else (-1e9, 1e9, -1e9, 1e9)       # G18: a Backrooms floor reaches into its stair corridors
        if g.pool and not (bx0 - 0.5 <= p.x <= bx1 + 0.5 and bz0 - 0.5 <= p.z <= bz1 + 0.5 and -4.0 <= p.y <= 4.0):
            self.failures.append(f'{self.t:.1f}s: ra ngoài phòng ({p.x:.2f}, {p.y:.2f}, {p.z:.2f})')
        cp = camera.world_position
        if not all(math.isfinite(v) for v in (cp[0], cp[1], cp[2], camera.fov)) or not 1.0 < camera.fov < 179.0:
            self.failures.append(f'{self.t:.1f}s: camera hỏng {tuple(cp)} fov {camera.fov}')
        w = g.combat.weapon
        if not (0 <= w.mag <= w.mag_size and w.reserve >= 0):
            self.failures.append(f'{self.t:.1f}s: đạn sai {w.mag}/{w.mag_size} dự trữ {w.reserve}')
        switching = g._pending_gun is not None or g._draw_pending
        self.hidden_for = self.hidden_for + dt if (g.viewmodel._hidden and not switching) else 0.0
        if self.hidden_for > 4.0:
            self.failures.append(f'{self.t:.1f}s: súng ẩn > 4 s ngoài lúc đổi súng')
            self.hidden_for = -1e9
        self.busy_for = self.busy_for + dt if g.combat.handling.busy else 0.0
        if self.busy_for > 10.0:
            self.failures.append(f'{self.t:.1f}s: tay bận (nạp / rút / cất) > 10 s')
            self.busy_for = -1e9
        if self.t >= self.next_sample:
            self.next_sample += 5.0
            self.samples.append((self.t, private_mb(), application.base.render.count_num_descendants(), len(scene.entities)))

    # ---------------------------------------------------------------- frame
    def frame(self, dt):
        self.t += dt
        if self.t > self.skip_until and self.focus_phase is None:       # minimised: Windows / Panda draw ~10 frames a second (normal, not a game hitch)
            self.dts.append(dt)
            if dt > 0.1:
                self.spikes.append((self.t, dt, ' '.join(self.recent)))
        if self.focus_phase is not None or self.t >= self.next_focus:
            if self.focus_phase is None:
                self.next_focus = self.t + self.rng.uniform(20.0, 30.0)
            self.focus_step()
        elif self.g.focus.focused:
            self.drive(dt)
        if self.t >= self.next_hitch:
            self.next_hitch = self.t + self.rng.uniform(15.0, 25.0)
            self.hitch()

    def report(self) -> int:
        dts = sorted(self.dts)
        if dts:
            med = dts[len(dts) // 2]
            p99 = dts[min(len(dts) - 1, int(len(dts) * 0.99))]
            spikes = sum(1 for d in dts if d > 0.1)
            print(f'[khung] {len(dts)} khung, trung vị {med * 1000:.1f} ms ({1 / med:.0f} FPS), p99 {p99 * 1000:.1f} ms, khung > 100 ms: {spikes}')
        c = self.counts
        print(f'[tác động] {self.t:.0f} s, {c["keys"]} lần bấm, {c["reloads"]} nạp, {c["switches"]} đổi súng, {c["panels"]} lần mở bảng, '
              f'{c["hitches"]} lần khựng giả, {c["focus"]} lần thu nhỏ cửa sổ (mất tiêu điểm thật: {self.g.focus.lost_count})')
        if self.samples:
            print('[mẫu] t(s)  bộ nhớ riêng(MB)  node  entity')
            for t, mb, nodes, ents in self.samples[:: max(1, len(self.samples) // 12)] + [self.samples[-1]]:
                print(f'       {t:5.0f}  {mb:8.1f}  {nodes:6d}  {ents:5d}')
        if self.t >= 300.0 and len(self.samples) >= 12:
            n = len(self.samples)
            early = sorted(s[1] for s in self.samples[n // 4: n // 4 + 4])[1]
            late = sorted(s[1] for s in self.samples[-4:])[1]
            nodes_early = max(s[2] for s in self.samples[n // 4: n // 4 + 4])
            nodes_late = max(s[2] for s in self.samples[-4:])
            print(f'[rò rỉ] bộ nhớ {early:.0f} -> {late:.0f} MB ({late - early:+.0f}), node {nodes_early} -> {nodes_late}')
            if late - early > 60.0:
                self.failures.append(f'bộ nhớ tăng {late - early:.0f} MB trong phần sau của lượt chạy (ngưỡng 60)')
            if nodes_late > nodes_early * 1.2 + 50:
                self.failures.append(f'số node tăng {nodes_early} -> {nodes_late}')
        for t, dt, what in self.spikes[:40]:
            print(f'[khung chậm] {t:6.2f}s {dt * 1000:5.0f} ms  sau: {what}')
        for n in self.notes:
            print(f'[ghi chú] {n}')
        for f in self.failures[:30]:
            print(f'[LỖI] {f}')
        print('KẾT QUẢ: ' + ('QUA' if not self.failures else f'TRƯỢT ({len(self.failures)} lỗi)'))
        return 0 if not self.failures else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=60.0)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--gun', default='m4')
    ap.add_argument('--map', default='pool', choices=('pool', 'backrooms'), help='G18: backrooms = level 5 tầng (địch đánh, chết, chơi lại)')
    args = ap.parse_args()
    game = create_game(hidden=False, size=(1280, 720), gun=args.gun, map_name=args.map)    # G19: focus / minimise checks need a real window
    chaos = Chaos(game, args.seconds, args.seed)
    orig = app_mod.Game.update
    state = {'done': False}

    def update(self):
        if state['done']:
            return
        dt = utime.dt
        try:
            chaos.frame(dt)
            orig(self)
            chaos.check(dt)
        except SystemExit:
            raise
        except Exception:
            chaos.failures.append('exception:\n' + traceback.format_exc())
            chaos.t = chaos.seconds
        if chaos.t >= chaos.seconds:
            state['done'] = True
            code = chaos.report()
            sys.stdout.flush()
            raise SystemExit(code)

    app_mod.Game.update = update
    print(f'[chaos] {args.seconds:.0f} s, seed {args.seed}, súng {args.gun}')
    game.app.run()


if __name__ == '__main__':
    main()
