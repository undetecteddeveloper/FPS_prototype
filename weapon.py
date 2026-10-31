"""Điều khiển bắn thuần (không import ursina): nhịp bắn theo RPM, đếm đạn, chế độ tự động / bắn đơn.

`update` trả về, cho mỗi phát bắn xảy ra trong khung hình, số giây đã trôi qua kể từ khoảnh khắc
phát đó nổ (tính tới CUỐI khung hình). Viên đạn sinh ra rồi được đẩy tiếp đúng khoảng đó, nên vị
trí đạn không bị lượng tử hoá theo khung hình và nhịp bắn trung bình đúng bằng RPM ở mọi FPS.
"""
from collections import deque

from weapon_data import GunData


class Weapon:
    def __init__(self, gun: GunData):
        self.interval = 60.0 / gun.rpm
        self.mag_size = gun.magazine
        self.mag = gun.magazine
        self.reserve = gun.reserve
        self.auto = gun.full_auto
        self.cooldown = 0.0                  # còn bao lâu nữa mới được bắn phát kế (tại cuối khung hình)
        self.clock = 0.0
        self.shot_times = deque(maxlen=2048)  # thời điểm từng phát (cho kiểm tra RPM)

    def toggle_mode(self):
        self.auto = not self.auto

    def refill(self):
        """TẠM THỜI tới G5 (reload có animation): nạp đầy băng từ số đạn dự trữ."""
        take = min(self.mag_size - self.mag, self.reserve)
        self.mag += take
        self.reserve -= take
        return take

    def update(self, dt: float, trigger_held: bool, trigger_pressed: bool) -> list:
        self.clock += dt
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
