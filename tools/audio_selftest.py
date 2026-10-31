"""Kiểm tra đường âm thanh bằng game thật, BẬT tiếng (các selftest khác tắt tiếng). Không nghe được loa, nên đo gián tiếp:
  - Panda có trình phát âm thanh thật (OpenAL) hay chỉ là "âm câm" (không lỗi nhưng không có tiếng)
  - file nạp được, độ dài đúng, mỗi phát bắn kích hoạt đúng một lần phát, và các bản phát thật sự ở trạng thái PLAYING
Cuối cùng vẫn cần tai người: chạy run.bat, bắn thử.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\audio_selftest.py        (thoát mã 1 nếu có mục trượt)
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import AudioSound  # noqa: E402
from ursina import Entity, application, held_keys, mouse, time  # noqa: E402

game = create_game(vsync=False, sound=True, draw=False)
combat, audio = game.combat, game.audio
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

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0 if all(r[3] for r in results) else 1)

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

        # hết đạn thì không có tiếng
        combat.weapon.mag = 0
        played0 = audio.played
        held_keys['left mouse'] = 1
        yield from self.wait(0.4)
        held_keys['left mouse'] = 0
        check('hết đạn: không phát tiếng', audio.played - played0, 0, audio.played == played0)


def report():
    print('\n=== KIỂM TRA ÂM THANH ===')
    print(f"{'mục':56s} {'đo được':>26s} {'mong đợi':>14s}  kết quả")
    for name, got, expected, ok in results:
        print(f'{name:56s} {str(got):>26s} {str(expected):>14s}  {"ĐẠT" if ok else "TRƯỢT"}')
    print(f'{sum(r[3] for r in results)}/{len(results)} mục đạt')


Script()
game.app.run()
