"""Ghép việc bắn lại: cò súng -> phát bắn -> viên đạn bay -> dò va chạm -> phản hồi (hit marker, nháy bia, lỗ đạn).

Đạn xuất phát từ vị trí mắt, theo hướng nhìn (đã gồm recoil camera) cộng một độ lệch ngẫu nhiên trong hình nón tản.
Mỗi phát bắn: lấy độ tản HIỆN TẠI (trước khi phát này cộng bloom) -> bắn -> cộng bloom, recoil camera, kick súng.
Mỗi khung hình mỗi viên đạn đi một đoạn rồi dò va chạm trên cả đoạn (swept), không phụ thuộc FPS.
"""
import random
from dataclasses import dataclass

from ursina import color, held_keys, mouse

from fps.core.ballistics import advance, distance_between, first_hit
from fps.core.movement import MoveState
from fps.core.recoil import CameraRecoil, GunKick
from fps.core.spread import Accuracy, random_in_cone
from fps.game.targets import HoleDecals, Target
from fps.core.weapon import Weapon
from fps.weapon_data import GameParams

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


@dataclass
class ShotInfo:
    """Phát bắn gần nhất (để HUD và kiểm tra đọc)."""
    view_dir: tuple         # hướng nhìn lúc bắn (tâm hình nón)
    direction: tuple        # hướng viên đạn thật sự đi
    spread: float           # nửa góc hình nón (độ) đã dùng
    state: MoveState


class Combat:
    def __init__(self, params: GameParams, player, targets: list, static_boxes: list, rng: random.Random = None,
                 audio=None):
        self.gun = params.gun
        self.fb = params.feedback
        self.player = player
        self.targets = targets
        self.static_boxes = static_boxes           # [(lo, hi, owner)]
        self.rng = rng or random.Random()
        self.audio = audio                         # GunAudio hoặc None (tắt tiếng)
        self.weapon = Weapon(self.gun)
        self.accuracy = Accuracy(self.gun.accuracy)
        self.recoil = CameraRecoil(self.gun.recoil, self.rng)
        self.gun_kick = GunKick(self.gun.kick, self.rng)
        self.spread_now = self.accuracy.angle(player.state, player.ads_amount)   # cho tâm ngắm động
        self.last_shot = None
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

        mouse_ok = mouse.locked or not self.require_locked_mouse
        trigger = bool(held_keys['left mouse']) and mouse_ok
        ready = mouse_ok and self.player.can_fire      # đang hạ súng sau khi chạy (sprint-to-fire) thì chưa bắn được
        held = trigger and ready
        pressed = self.pressed and ready
        if ready or not trigger:
            self.pressed = False                       # còn giữ cò mà súng chưa sẵn sàng: nhớ cú bóp để bắn khi sẵn sàng
        self.accuracy.update(dt)
        ages = self.weapon.update(dt, held, pressed)
        if ages:
            origin, view_dir = self.player.aim_ray()
            for age in ages:
                state, ads = self.player.state, self.player.ads_amount
                spread = self.accuracy.angle(state, ads)
                direction = random_in_cone(view_dir, spread, self.rng)
                self.last_shot = ShotInfo(view_dir, direction, spread, state)
                self._fire(origin, direction, age)
                self.accuracy.on_shot()
                self.recoil.on_shot()
                self.gun_kick.on_shot()
                if self.audio:
                    self.audio.play_shot()
        up, right = self.recoil.step(dt)
        if up or right:
            self.player.kick_view(up, right)       # sau khi bắn: phát này đã đi theo hướng nhìn trước cú giật
        self.gun_kick.update(dt)
        self.spread_now = self.accuracy.angle(self.player.state, self.player.ads_amount)

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
