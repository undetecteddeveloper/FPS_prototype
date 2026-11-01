"""Kiểm tra đường âm thanh bằng game thật, BẬT tiếng (các selftest khác tắt tiếng). Không nghe được loa, nên đo gián tiếp:
  - Panda có trình phát âm thanh thật (OpenAL) hay chỉ là "âm câm" (không lỗi nhưng không có tiếng)
  - file nạp được, độ dài đúng, mỗi phát bắn kích hoạt đúng một lần phát, và các bản phát thật sự ở trạng thái PLAYING
  - Foley (nạp đạn, bước chân, nhảy, chạm đất): bước chân phát theo nhịp bob của sway (hai tiếng mỗi chu kỳ bob, đo bằng pha sway thật), không chồng lên nhau, dừng thì hết tiếng, trên không im, nạp thường / nạp cạn / rút súng ra đúng
    số tiếng, đúng thứ tự và đúng thời điểm (cả khi đổi tốc độ clip), huỷ nạp thì bỏ các tiếng chưa tới mốc, tiếng vừa phát ở trạng thái PLAYING
Cuối cùng vẫn cần tai người: chạy run.bat, bắn thử, đi bộ, nạp đạn.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\audio_selftest.py        (thoát mã 1 nếu có mục trượt)
"""
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import AudioSound  # noqa: E402
from ursina import Entity, application, held_keys, mouse, time  # noqa: E402

game = create_game(vsync=False, sound=True, draw=False)
combat, audio, foley, player = game.combat, game.audio, game.foley, game.player
handling, gun = combat.handling, game.params.gun
base = application.base
mouse.locked = False
combat.require_locked_mouse = False
results = []


def check(name, got, expected, ok):
    results.append((name, got, expected, bool(ok)))


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self._seen, self.audited, self.not_playing = 0, 0, 0
        self.m = {}

    def update(self):
        try:
            self.audit()
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0 if all(r[3] for r in results) else 1)

    def audit(self):
        """Mỗi khung: nếu vừa có tiếng foley mới thì bản vừa phát phải đang ở trạng thái PLAYING (phát thật chứ không chỉ đếm)."""
        total = sum(foley.counts.values())
        if total > self._seen:
            self._seen = total
            self.audited += 1
            if foley.last_sound.status() != AudioSound.PLAYING:
                self.not_playing += 1

    def wait(self, seconds):
        t = 0.0
        while t < seconds:
            yield
            t += min(time.dt, 0.05)

    def run(self):
        yield from self.wait(0.3)
        managers = list(base.sfxManagerList)
        mgr = managers[0] if managers else None
        name = type(mgr).__name__ if mgr else 'không có'
        check('có trình phát âm thanh (sfx manager)', name, 'khác trống', mgr is not None)
        check('trình phát hợp lệ (không phải âm câm)', f'{name}, valid={mgr.is_valid() if mgr else None}', 'valid=True',
              mgr is not None and mgr.is_valid() and 'Null' not in name)
        check('âm thanh đang bật (base.sfxActive)', base.sfxActive, True, base.sfxActive)

        check('có đủ bản phát trong vòng (pool)', len(audio.sounds), game.params.gun.shot_pool, len(audio.sounds) == game.params.gun.shot_pool)
        length = audio.sounds[0].length()
        check('file nạp được, dài (s)', round(length, 3), '~0.50', 0.45 <= length <= 0.55)

        # bắn một loạt 0,6 s ở nhịp thật và đếm
        combat.weapon.auto = True
        combat.weapon.mag = 30
        combat.weapon.cooldown = 0.0
        played0, fired0 = audio.played, combat.shots_fired
        held_keys['left mouse'] = 1
        yield from self.wait(0.6)
        playing_now = sum(1 for s in audio.sounds if s.status() == AudioSound.PLAYING)
        held_keys['left mouse'] = 0
        fired = combat.shots_fired - fired0
        check('mỗi phát bắn kích hoạt đúng một lần phát', f'{audio.played - played0} / {fired}', 'bằng nhau', fired > 0 and audio.played - played0 == fired)
        check('đang có nhiều tiếng chồng nhau (PLAYING)', playing_now, '>= 3', playing_now >= 3)
        yield from self.wait(0.7)
        still = sum(1 for s in audio.sounds if s.status() == AudioSound.PLAYING)
        check('0,7 s sau khi ngừng bắn: các tiếng đã tắt hết', still, 0, still == 0)

        # bắn đơn: một lần bóp một tiếng
        combat.weapon.auto = False
        combat.weapon.cooldown = 0.0
        played0 = audio.played
        combat.pressed = True
        yield from self.wait(0.2)
        check('bắn đơn: một lần bóp một tiếng', audio.played - played0, 1, audio.played - played0 == 1)

        # hết đạn thì không có tiếng súng (bóp cò lúc băng cạn tự bắt đầu nạp: tiếng nạp là của foley, kiểm ở dưới)
        combat.weapon.mag = 0
        played0 = audio.played
        held_keys['left mouse'] = 1
        yield from self.wait(0.4)
        held_keys['left mouse'] = 0
        check('hết đạn: không phát tiếng súng', audio.played - played0, 0, audio.played == played0)

        yield from self.foley_checks()

    # ------------------------------------------------------------------ foley
    def wait_idle(self, limit=8.0):
        t = 0.0
        while handling.busy and t < limit:
            yield
            t += min(time.dt, 0.05)

    def names_since(self, t0):
        return [e[1] for e in foley.log if e[0] >= t0]

    def start_reload(self, mag, speed=1.0):
        combat.weapon.mag, combat.weapon.reserve, combat.weapon.cooldown = mag, 150, 0.0
        gun.reload.speed = speed
        t0 = foley.clock
        combat.request_reload()
        return t0

    def move_for(self, seconds, **keys):
        """Giữ phím `seconds` giây (ví dụ w=1, shift=1). Ghi quãng đường, số tiếng bước, số tiếng bước phát lúc đang ở trên không, âm lượng trung bình."""
        player.x, player.z, player.yaw = 0.0, -14.0, 0.0
        player.vx = player.vz = 0.0
        yield from self.wait(0.15)
        t0, c0 = foley.clock, Counter(foley.counts)
        px, pz, dist, air_steps, t = player.x, player.z, 0.0, 0, 0.0
        ph_last, ph_total = game.sway.phase, 0.0                  # pha bob đã đi được (rad): bước chân phải bằng 2 tiếng mỗi 2 pi
        for k, v in keys.items():
            held_keys[k] = v
        while t < seconds:
            before = foley.counts['step_walk'] + foley.counts['step_run']
            yield
            t += min(time.dt, 0.05)
            dist += ((player.x - px) ** 2 + (player.z - pz) ** 2) ** 0.5
            px, pz = player.x, player.z
            ph_total += (game.sway.phase - ph_last) % (2.0 * math.pi)
            ph_last = game.sway.phase
            if foley.counts['step_walk'] + foley.counts['step_run'] > before and not player.on_ground:
                air_steps += 1
        for k in keys:
            held_keys[k] = 0
        c1 = foley.counts
        steps = (c1['step_walk'] - c0['step_walk']) + (c1['step_run'] - c0['step_run'])
        vols = [e[2] for e in foley.log if e[0] >= t0 and e[1] in ('step_walk', 'step_run')]
        times = [e[0] for e in foley.log if e[0] >= t0 and e[1] in ('step_walk', 'step_run')]
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.m = dict(dist=dist, steps=steps, air_steps=air_steps, mean_vol=sum(vols) / len(vols) if vols else 0.0,
                      bob_steps=ph_total / math.pi, min_gap=min(gaps) if gaps else 9.0,
                      run=c1['step_run'] - c0['step_run'], walk=c1['step_walk'] - c0['step_walk'])

    def foley_checks(self):
        yield from self.wait_idle()
        banks = foley.banks
        lengths = [s.length() for b in banks.values() for v in b.voices for s in v]
        want_names = {c.sound for cues in foley.audio.cues.values() for c in cues} | {'step_walk', 'step_run', 'land', 'jump', foley.audio.cancel_sound}
        check('foley: số nhóm tiếng đã nạp (mọi tên trong bảng mốc + bước chân)', len(banks), len(want_names), set(banks) == want_names)
        check('foley: file nào cũng nạp được và có độ dài (s)', f'{min(lengths):.3f}..{max(lengths):.3f}', '0.04..0.7', 0.04 < min(lengths) and max(lengths) < 0.7)
        check('foley: bước chân có 4+ biến thể mỗi loại', f"{len(banks['step_walk'].voices)}/{len(banks['step_run'].voices)}", '>= 4',
              len(banks['step_walk'].voices) >= 4 and len(banks['step_run'].voices) >= 4)
        a = game.params.audio

        # --- bước chân ---
        yield from self.move_for(5.0, w=1)
        m = self.m
        check('đi bộ: số tiếng bước = 2 mỗi chu kỳ bob của sway', f"{m['steps']} / {m['bob_steps']:.1f}", '+-1.5',
              abs(m['steps'] - m['bob_steps']) <= 1.5 and m['steps'] >= 4)
        check('đi bộ: hai tiếng bước không chồng nhau (cách tối thiểu, s)', f"{m['min_gap']:.2f}", '> 0.4', m['min_gap'] > 0.4)
        check('đi bộ: dùng nhóm step_walk, không dùng step_run', f"{m['walk']} / {m['run']}", 'x / 0', m['run'] == 0 and m['walk'] == m['steps'])
        check('đi bộ: không có tiếng bước lúc ở trên không', m['air_steps'], 0, m['air_steps'] == 0)
        walk_vol = m['mean_vol']
        yield from self.wait(0.4)
        c_stop = sum(foley.counts.values())
        yield from self.wait(1.0)
        check('dừng hẳn: không phát thêm tiếng nào', sum(foley.counts.values()) - c_stop, 0, sum(foley.counts.values()) == c_stop)

        yield from self.move_for(4.0, w=1, shift=1)
        m = self.m
        check('chạy nước rút: số tiếng bước = 2 mỗi chu kỳ bob của sway', f"{m['steps']} / {m['bob_steps']:.1f}", '+-1.5',
              abs(m['steps'] - m['bob_steps']) <= 1.5 and m['steps'] >= 4)
        check('chạy nước rút: hai tiếng bước không chồng nhau (cách tối thiểu, s)', f"{m['min_gap']:.2f}", '> 0.4', m['min_gap'] > 0.4)
        check('chạy nước rút: dùng nhóm step_run', f"{m['run']} / {m['walk']}", 'x / <=1', m['run'] >= m['steps'] - 1)
        check('chạy nước rút: tiếng to hơn đi bộ', f"{m['mean_vol']:.3f} > {walk_vol:.3f}", '>', m['mean_vol'] > walk_vol)

        yield from self.move_for(6.0, w=1, control=1)
        m = self.m
        check('ngồi đi: số tiếng bước = 2 mỗi chu kỳ bob của sway', f"{m['steps']} / {m['bob_steps']:.1f}", '+-1.5',
              abs(m['steps'] - m['bob_steps']) <= 1.5 and m['steps'] >= 3)
        check('ngồi đi: âm lượng ~35% đi bộ', f"{m['mean_vol'] / walk_vol:.2f}", '0.25..0.45', 0.25 <= m['mean_vol'] / walk_vol <= 0.45)
        yield from self.wait(0.6)

        # nhảy tại chỗ: một tiếng nhảy, một tiếng chạm đất, không có tiếng bước
        player.x, player.z = 0.0, -14.0
        player.vx = player.vz = 0.0
        yield from self.wait(0.5)
        c0, t0 = Counter(foley.counts), foley.clock
        held_keys['space'] = 1
        yield from self.wait(0.1)
        held_keys['space'] = 0
        yield from self.wait(1.4)
        d = {k: foley.counts[k] - c0[k] for k in ('jump', 'land', 'step_walk', 'step_run')}
        check('nhảy tại chỗ: 1 tiếng nhảy, 1 tiếng chạm đất, 0 tiếng bước', str(d), 'jump 1, land 1',
              d['jump'] == 1 and d['land'] == 1 and d['step_walk'] + d['step_run'] == 0)
        land_vol = next((e[2] for e in foley.log if e[0] >= t0 and e[1] == 'land'), 0.0)
        check('chạm đất: to hơn bước chân đi bộ', f'{land_vol:.3f} > {walk_vol:.3f}', 'x1,3 trở lên', land_vol > walk_vol * 1.3)
        check('chạm đất: nhỏ hơn tiếng súng', f'{land_vol:.3f} < {gun.shot_volume}', '<', land_vol < gun.shot_volume * 0.8)

        # --- nạp đạn: nạp thường ---
        want = [c.sound for c in a.cues['reload']]
        t0 = self.start_reload(10)
        yield from self.wait(0.1)
        yield from self.wait_idle()
        got = self.names_since(t0)
        check('nạp thường: đúng số tiếng và thứ tự', f'{len(got)}/{len(want)}', 'bằng nhau', got == want)
        seat = next((e[0] - t0 for e in foley.log if e[0] >= t0 and e[1] == 'mag_seat'), -9)
        want_t = (gun.clips['reload'].swap - gun.clips['reload'].start) / 30.0
        check('nạp thường: tiếng băng vào chỗ đúng khung 61 (s)', f'{seat:.2f}', f'{want_t:.2f}+-0.12', abs(seat - want_t) <= 0.12)
        check('nạp thường: chỉ hai cú va đầu, không có bolt', str(got), "['mag_release', 'mag_in', 'mag_seat']",
              got == ['mag_release', 'mag_in', 'mag_seat'] and 'bolt_release' not in got and 'bolt_tick' not in got)
        check('nạp thường: đạn được nạp đầy', combat.weapon.mag, gun.magazine, combat.weapon.mag == gun.magazine)

        # --- nạp cạn ---
        want = [c.sound for c in a.cues['reload_empty']]
        t0 = self.start_reload(0)
        yield from self.wait(0.1)
        yield from self.wait_idle()
        got = self.names_since(t0)
        check('nạp cạn: đúng số tiếng và thứ tự', f'{len(got)}/{len(want)}', 'bằng nhau', got == want)
        check('nạp cạn: đủ ba cú va, có bolt ở cuối', str(got), "[..., 'mag_seat', 'bolt_release']", got[-2:] == ['mag_seat', 'bolt_release'])
        clip = gun.clips['reload_empty']
        bolt_t = (190 - clip.start) / 30.0
        bolt = next((e[0] - t0 for e in foley.log if e[0] >= t0 and e[1] == 'bolt_release'), -9)
        check('nạp cạn: tiếng bolt nhả đúng khung 190 (s)', f'{bolt:.2f}', f'{bolt_t:.2f}+-0.12', abs(bolt - bolt_t) <= 0.12)

        # --- đổi tốc độ clip: mốc đến sớm hơn tương ứng ---
        t0 = self.start_reload(10, speed=2.0)
        yield from self.wait(0.1)
        yield from self.wait_idle()
        seat2 = next((e[0] - t0 for e in foley.log if e[0] >= t0 and e[1] == 'mag_seat'), -9)
        check('tốc độ clip x2: tiếng băng vào chỗ đến lúc 1,0 s', f'{seat2:.2f}', '1.00+-0.12', abs(seat2 - want_t / 2) <= 0.12)
        n2 = len(self.names_since(t0))
        check('tốc độ clip x2: vẫn đủ tiếng', n2, len(a.cues['reload']), n2 == len(a.cues['reload']))
        gun.reload.speed = 1.0

        # --- huỷ nạp giữa chừng: tiếng chưa tới mốc bị bỏ, thêm một tiếng tay trượt về ---
        t0 = self.start_reload(10)
        yield from self.wait(1.3)
        before = self.names_since(t0)
        mag_before = combat.weapon.mag
        handling.cancel()
        yield from self.wait(3.5)
        after = self.names_since(t0)
        check('huỷ nạp giữa chừng: trước lúc huỷ mới có tiếng chốt băng', str(before), "['mag_release']", before == ['mag_release'])
        check('huỷ nạp giữa chừng: sau đó chỉ còn tiếng tay trượt về', str(after[len(before):]), "['settle']", after[len(before):] == [a.cancel_sound])
        check('huỷ nạp giữa chừng: không có mag_in / mag_seat', 'mag_seat' in after or 'mag_in' in after, False, not ('mag_seat' in after or 'mag_in' in after))
        check('huỷ nạp giữa chừng: đạn y nguyên', combat.weapon.mag, mag_before, combat.weapon.mag == mag_before == 10)

        # --- huỷ nạp ngay đầu (tay chưa làm gì): im ---
        t0 = self.start_reload(10)
        yield from self.wait(0.3)
        handling.cancel()
        yield from self.wait(1.5)
        check('huỷ nạp ngay đầu: không có tiếng nào', str(self.names_since(t0)), '[]', self.names_since(t0) == [])
        yield from self.wait_idle()

        # --- rút súng ---
        t0 = foley.clock
        handling.start_draw()
        yield from self.wait(0.1)
        yield from self.wait_idle()
        yield from self.wait(0.2)
        got = self.names_since(t0)
        check('rút súng: hai tiếng nhẹ', str(got), "['draw_a', 'draw_b']", got == ['draw_a', 'draw_b'])

        yield from self.wait(0.3)
        check('mỗi tiếng foley vừa phát đều ở trạng thái PLAYING', f'{self.audited - self.not_playing}/{self.audited}', 'tất cả',
              self.audited > 20 and self.not_playing == 0)


def report():
    print('\n=== KIỂM TRA ÂM THANH ===')
    print(f"{'mục':64s} {'đo được':>26s} {'mong đợi':>16s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:64s} {str(got):>26s} {str(expected):>16s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
