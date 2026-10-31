"""Toán thuần của hiệu ứng bắn (không import ursina, nên test được không cần cửa sổ): tia lửa đầu nòng và tracer.

Tracer là một vệt sáng dài `length` bám sau đầu viên đạn thật. Vì đạn xuất phát từ MẮT mà vệt phải thấy bay ra từ MIỆNG NÒNG,
vệt mang độ lệch `offset` (miệng nòng - mắt) lúc bắn, độ lệch này tắt dần theo quãng đường đi được (`convergence`):
đầu vệt luôn nằm trên đường đạn thật khi đã đi xa, còn lúc mới bắn thì nằm ở nòng.
"""
import math

from fps.core.movement import smoothstep


def flash_envelope(age: float, life: float) -> float:
    """Cường độ tia lửa 1 -> 0 theo tuổi (s): sáng ngay lúc nổ, tắt nhanh về cuối."""
    if life <= 0 or age < 0 or age >= life:
        return 0.0
    return (1.0 - age / life) ** 1.5


def convergence(distance: float, blend_distance: float) -> float:
    """1 ở nòng (đi 0 m) -> 0 khi đã đi `blend_distance` m: phần độ lệch nòng-mắt còn lại của vệt tracer."""
    if blend_distance <= 0:
        return 0.0
    return 1.0 - smoothstep(distance / blend_distance)


def is_traced(shot_number: int, every: int) -> bool:
    """Phát thứ `shot_number` (đếm từ 1) có tracer không: phát đầu rồi cứ `every` phát một lần."""
    return every > 0 and (shot_number - 1) % every == 0


def ribbon_width(distance: float, base_width: float, min_pixels: float, fov_deg: float, screen_width_px: float) -> float:
    """Bề rộng (m) của vệt ở `distance` m: không mảnh hơn `min_pixels` điểm ảnh, vì dưới 1 điểm ảnh vệt nhấp nháy."""
    one_pixel = distance * math.radians(fov_deg) / screen_width_px
    return max(base_width, min_pixels * one_pixel)


def lens_ratio(world_fov_deg: float, view_fov_deg: float) -> float:
    """Hệ số nhân lên độ lệch ngang/dọc của miệng nòng (đo trong cảnh súng, FOV riêng) để vệt ở thế giới (FOV khác)
    nằm đúng chỗ trên màn hình mà miệng nòng đang nằm."""
    return math.tan(math.radians(world_fov_deg) / 2) / math.tan(math.radians(view_fov_deg) / 2)


class Tracer:
    """Trạng thái một vệt. Mỗi khung: viên đạn còn bay thì `follow`, trúng/hết hạn thì `end` (một lần), rồi `advance`."""

    def __init__(self, offset: tuple, length: float, blend_distance: float, speed: float):
        self.offset = offset
        self.length = length
        self.blend = blend_distance
        self.speed = speed                     # m/s: đuôi vệt đuổi theo đầu khi đạn đã trúng
        self.head = (0.0, 0.0, 0.0)
        self.direction = (0.0, 0.0, 1.0)
        self.head_s = 0.0                      # quãng đường đầu vệt đã đi từ mắt
        self.tail_s = 0.0
        self.ended = False
        self.done = False

    def follow(self, head: tuple, direction: tuple, travelled: float):
        self.head, self.direction, self.head_s = head, direction, travelled
        self.tail_s = max(0.0, travelled - self.length)

    def end(self, end_pos: tuple, direction: tuple, travelled: float):
        """Viên đạn đã hết (trúng hoặc quá hạn): đầu vệt đứng yên ở điểm cuối, đuôi chạy tới."""
        self.follow(end_pos, direction, travelled)
        self.ended = True

    def advance(self, dt: float):
        if self.ended:
            self.tail_s += self.speed * dt
            if self.tail_s >= self.head_s:
                self.done = True

    def endpoints(self) -> tuple:
        """(đuôi, đầu) trong toạ độ thế giới, đã cộng độ lệch nòng-mắt còn lại ở từng đầu."""
        d = self.direction
        back = self.head_s - self.tail_s
        tail = [self.head[i] - d[i] * back + self.offset[i] * convergence(self.tail_s, self.blend) for i in range(3)]
        head = [self.head[i] + self.offset[i] * convergence(self.head_s, self.blend) for i in range(3)]
        return tuple(tail), tuple(head)
