"""Lịch phát tiếng theo khung của clip (thuần, không import ursina, nên test được không cần cửa sổ).

Mỗi clip nạp / rút súng có bảng `SoundCue` (khung tuyệt đối trong file glb, 30 fps). Khi clip bắt đầu với tốc độ `speed`, mỗi mốc
được đổi sang giây THẬT = (frame - clip.start) / 30 / speed (tốc độ nhân lên thì mốc đến sớm hơn). Đồng hồ của lịch cộng cùng `dt`
mà `Handling.update` cộng, nên hai bên khớp nhau tới một khung hình. Lệnh nạp / rút súng được xử lý SAU `Handling.update` của khung đó (clip mới ở t = 0),
nên `update` đầu tiên sau `start` không cộng `dt` (không thì tiếng đến sớm một khung).

Sự kiện của Handling (xem core/handling.py):
  start(key, speed) lập lịch · done() phát nốt những tiếng còn lại (khung cuối có thể bỏ sót) · cancel() bỏ tiếng chưa tới mốc,
  tiếng đã phát thì để vang nốt; nếu đã phát ít nhất một tiếng thì hẹn thêm một tiếng 'tay trượt về' sau `cancel_delay`.
"""
from fps.weapon_data import AudioData, Clip

FPS = 30.0


class CueSchedule:
    def __init__(self):
        self._pending = []          # [(giây thật kể từ lúc start, tên, âm lượng)] sắp theo thời gian
        self._t = 0.0
        self.fired = 0              # số tiếng đã phát của lần chạy hiện tại (để biết huỷ nạp có nên thêm tiếng 'tay trượt về')
        self.running = False
        self._fresh = False         # vừa start trong khung này: khung này chưa tính thời gian

    def start(self, cues, clip: Clip, speed: float):
        """Lập lịch cho clip `clip` chạy với tốc độ `speed`. Mốc nằm trước đầu clip thì phát ngay."""
        speed = max(speed, 1e-3)
        self._pending = sorted(((max(0.0, (c.frame - clip.start) / FPS / speed), c.sound, c.volume) for c in cues), key=lambda e: e[0])
        self._t, self.fired, self.running = 0.0, 0, True
        self._fresh = True

    def update(self, dt: float) -> list:
        """Đồng hồ đi thêm `dt` giây: trả về [(tên, âm lượng)] của các mốc vừa tới (theo thứ tự thời gian)."""
        if not self._pending:
            return []
        if self._fresh:
            self._fresh = False
        else:
            self._t += dt
        out = []
        while self._pending and self._pending[0][0] <= self._t:
            _, name, volume = self._pending.pop(0)
            out.append((name, volume))
        self.fired += len(out)
        return out

    def flush(self) -> list:
        """Clip chạy hết: phát nốt mọi mốc còn lại."""
        out = [(name, volume) for _, name, volume in self._pending]
        self._pending = []
        self.fired += len(out)
        self.running = False
        return out

    def cancel(self, audio: AudioData):
        """Huỷ: bỏ mọi mốc chưa tới. Đã phát ít nhất một tiếng thì hẹn tiếng 'tay trượt về' (clip nạp ở đầu thì tay chưa làm gì nên im)."""
        had_sound = self.fired > 0
        self._pending = []
        self.running = False
        if had_sound and audio.cancel_sound:
            self._pending = [(self._t + audio.cancel_delay, audio.cancel_sound, audio.cancel_volume)]

    @property
    def pending_names(self) -> list:
        return [name for _, name, _ in self._pending]
