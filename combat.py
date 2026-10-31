"""Ghép việc bắn lại: cò súng -> phát bắn -> viên đạn bay -> dò va chạm -> phản hồi (hit marker, nháy bia, lỗ đạn).

Đạn xuất phát từ vị trí mắt, theo hướng nhìn (G3 sẽ cộng độ tản vào hướng này).
Mỗi khung hình mỗi viên đạn đi một đoạn rồi dò va chạm trên cả đoạn (swept), không phụ thuộc FPS.
"""
from dataclasses import dataclass

from ursina import color, held_keys, mouse

from ballistics import advance, distance_between, first_hit
from targets import HoleDecals, Target
from weapon import Weapon
from weapon_data import GameParams

DUST_TINT = color.rgba(1.0, 0.92, 0.8, 0.85)


class Bullet:
    __slots__ = ('origin', 'pos', 'vel', 'age')

    def __init__(self, origin, vel):
        self.origin = origin
        self.pos = origin
        self.vel = vel
        self.age = 0.0


@dataclass
class Impact:
    """Lần va chạm gần nhất (để HUD và kiểm tra đọc)."""
    point: tuple
    normal: tuple
    distance: float         # độ dài đường đạn từ mắt tới điểm trúng
    owner: object           # Target, GROUND, hoặc Entity của bờ đất
    origin: tuple


class Combat:
    def __init__(self, params: GameParams, player, targets: list, static_boxes: list):
        self.gun = params.gun
        self.fb = params.feedback
        self.player = player
        self.targets = targets
        self.static_boxes = static_boxes           # [(lo, hi, owner)]
        self.weapon = Weapon(self.gun)
        self.decals = HoleDecals(self.fb)
        self.bullets = []
        self.pressed = False                       # vừa bóp cò (sự kiện nhấn chuột, dùng cho bắn đơn)
        self.require_locked_mouse = True           # không bắn khi người chơi đã nhả chuột bằng Esc
        self.hit_marker_left = 0.0
        self.last_hit_distance = None
        self.last_hit_left = 0.0
        self.last_impact = None
        self.shots_fired = 0
        self.target_hits = 0

    # --- mỗi khung hình ---
    def update(self, dt: float):
        for t in self.targets:
            t.update(dt)
        self.hit_marker_left = max(0.0, self.hit_marker_left - dt)
        self.last_hit_left = max(0.0, self.last_hit_left - dt)

        self._step_bullets(dt)           # đạn cũ đi trước, đạn mới sinh ra sau (đã tự đẩy tới cuối khung)

        can_shoot = mouse.locked or not self.require_locked_mouse
        held = bool(held_keys['left mouse']) and can_shoot
        pressed = self.pressed and can_shoot
        self.pressed = False
        ages = self.weapon.update(dt, held, pressed)
        if ages:
            origin, direction = self.player.aim_ray()
            for age in ages:
                self._fire(origin, direction, age)

    def _boxes(self) -> list:
        return [(*t.aabb(), t) for t in self.targets] + self.static_boxes

    def _fire(self, origin, direction, age: float):
        speed = self.gun.muzzle_velocity
        bullet = Bullet(origin, tuple(c * speed for c in direction))
        self.shots_fired += 1
        if self._advance(bullet, age, self._boxes()):
            self.bullets.append(bullet)

    def _step_bullets(self, dt: float):
        if not self.bullets:
            return
        boxes = self._boxes()
        self.bullets = [b for b in self.bullets if self._advance(b, dt, boxes)]

    def _advance(self, bullet: Bullet, dt: float, boxes: list) -> bool:
        """Đẩy đạn đi dt giây. Trả về False nếu đạn hết (trúng gì đó hoặc quá hạn)."""
        new_pos, new_vel = advance(bullet.pos, bullet.vel, self.gun.bullet_gravity, dt)
        hit = first_hit(bullet.pos, new_pos, boxes)
        if hit:
            self._on_hit(bullet, hit)
            return False
        bullet.pos, bullet.vel = new_pos, new_vel
        bullet.age += dt
        return bullet.age < self.gun.bullet_lifetime

    # --- phản hồi ---
    def _on_hit(self, bullet: Bullet, hit):
        distance = distance_between(bullet.origin, hit.point)
        self.last_impact = Impact(hit.point, hit.normal, distance, hit.owner, bullet.origin)
        if isinstance(hit.owner, Target):
            self.target_hits += 1
            hit.owner.flash()
            self.hit_marker_left = self.fb.hit_marker_duration
            self.last_hit_distance = distance
            self.last_hit_left = self.fb.last_hit_display_time
            self.decals.add(hit.point, hit.normal, distance, parent=hit.owner.root)
        else:
            self.decals.add(hit.point, hit.normal, distance, tint=DUST_TINT)

    # --- trạng thái cho HUD ---
    @property
    def hit_marker_alpha(self) -> float:
        return self.hit_marker_left / self.fb.hit_marker_duration if self.fb.hit_marker_duration else 0.0
