"""Tiếng súng: một nhóm bản phát (pool) luân phiên, để phát sau không cắt đuôi phát trước.

Ở 750 phát/phút (80 ms) mà tiếng dài 0,5 s thì cùng lúc có ~6 tiếng đang vang; mỗi phát lấy bản kế tiếp trong vòng.
Mỗi phát đổi cao độ ngẫu nhiên chút ít (`shot_pitch_variation`) cho đỡ nghe như bản ghi lặp. Số liệu ở weapon_data.GunData.
Không có thiết bị âm thanh thì Panda trả về âm câm, không lỗi.
"""
import random
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.weapon_data import GunData


class GunAudio:
    def __init__(self, gun: GunData, project_root: Path, rng: random.Random = None):
        self.gun = gun
        self.rng = rng or random.Random()
        loader = application.base.loader
        path = Filename.from_os_specific(str(project_root / gun.shot_sound))
        self.sounds = [loader.load_sfx(path) for _ in range(max(1, gun.shot_pool))]
        self._next = 0
        self.played = 0                    # số tiếng đã phát (cho kiểm tra)

    def play_shot(self):
        sound = self.sounds[self._next]
        self._next = (self._next + 1) % len(self.sounds)
        sound.set_volume(self.gun.shot_volume)
        v = self.gun.shot_pitch_variation
        sound.set_play_rate(1.0 + self.rng.uniform(-v, v) if v else 1.0)
        sound.play()                       # phát lại từ đầu nếu bản này còn đang vang (chỉ khi cả vòng đã quay hết)
        self.played += 1
