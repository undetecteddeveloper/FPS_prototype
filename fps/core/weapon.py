"""Điều khiển bắn thuần (không import ursina): nhịp bắn theo RPM, đếm đạn, chế độ tự động / bắn đơn.

`update` trả về, cho mỗi phát bắn xảy ra trong khung hình, số giây đã trôi qua kể từ khoảnh khắc
phát đó nổ (tính tới CUỐI khung hình). Viên đạn sinh ra rồi được đẩy tiếp đúng khoảng đó, nên vị
trí đạn không bị lượng tử hoá theo khung hình và nhịp bắn trung bình đúng bằng RPM ở mọi FPS.
"""
from collections import deque

from fps.weapon_data import GunData


class Weapon:
    def __init__(self, gun: GunData):
        self.gun = gun
        self._rpm = gun.rpm
        self.interval = 60.0 / gun.rpm       # đọc lại từ gun.rpm mỗi khung (bảng debug đổi rpm lúc đang chạy)
        self.mag_size = gun.magazine
        self.mag = gun.magazine
        self.reserve = gun.reserve
        self.auto = gun.full_auto
        self.cooldown = 0.0                  # còn bao lâu nữa mới được bắn phát kế (tại cuối khung hình)
        self.clock = 0.0
        self.shot_times = deque(maxlen=2048)  # thời điểm từng phát (cho kiểm tra RPM)

    def toggle_mode(self):
        self.auto = not self.auto

    @property
    def can_reload(self) -> bool:
        return self.mag < self.mag_size and self.reserve > 0

    @property
    def out_of_ammo(self) -> bool:
        return self.mag == 0 and self.reserve == 0

    def load_magazine(self) -> int:
        """Đổ đạn từ dự trữ vào băng cho đầy (đúng lúc băng mới vào chỗ). Trả về số viên nạp.
        Đạn là một kho chung: băng cũ còn bao nhiêu viên thì vẫn tính (tổng mag + reserve không đổi)."""
        take = min(self.mag_size - self.mag, self.reserve)
        self.mag += take
        self.reserve -= take
        return take

    def update(self, dt: float, trigger_held: bool, trigger_pressed: bool) -> list:
        self.clock += dt
        if self.gun.rpm != self._rpm and self.gun.rpm > 0:
            self._rpm = self.gun.rpm
            self.interval = 60.0 / self._rpm
        # đang nghỉ (cooldown <= 0) thì phát đầu nổ đúng "bây giờ" (age 0), không bị tính như nổ từ đầu khung
        self.cooldown = self.cooldown - dt if self.cooldown > 0 else 0.0
        wants = trigger_held if self.auto else trigger_pressed
        if not wants and self.cooldown < 0:
            self.cooldown = 0.0              # không dồn "tín dụng" nhịp bắn khi nhả cò
        ages = []
        while wants and self.cooldown <= 0 and self.mag > 0:
            age = -self.cooldown
            ages.append(age)
            self.shot_times.append(self.clock - age)
            self.mag -= 1
            self.cooldown += self.interval
            if not self.auto:
                break                        # bắn đơn: mỗi lần bóp cò một phát
        return ages
