"""Ghép việc bắn lại: cò súng -> phát bắn -> viên đạn bay -> dò va chạm -> phản hồi (hit marker, nháy bia, lỗ đạn).

Đạn xuất phát từ vị trí mắt, theo hướng NÒNG SÚNG đang chỉ (`aim_source`, xem core/freeaim.py) cộng độ tản cơ khí rất nhỏ.
Mỗi phát bắn: lấy độ tản HIỆN TẠI -> bắn -> cú giật sinh ngẫu nhiên (một phần vào camera, phần còn lại làm súng trôi), kick súng.
Mỗi khung hình mỗi viên đạn đi một đoạn rồi dò va chạm trên cả đoạn (swept), không phụ thuộc FPS.
"""
import math
import random
from dataclasses import dataclass

from ursina import color, held_keys, mouse

from fps.core.ballistics import advance, distance_between, first_hit, moving_hit
from fps.core.freeaim import FreeAim
from fps.core.handling import Handling, Phase
from fps.core.movement import MoveState
from fps.core.recoil import CameraRecoil, GunKick
from fps.core.spread import Accuracy, random_in_cone
from fps.game.decals import HoleDecals
from fps.game.targets import Target, hole_texture
from fps.core.weapon import Weapon
from fps.weapon_data import GameParams

DUST_TINT = color.rgba(1.0, 0.92, 0.8, 0.85)
MAX_BULLET_STEP = 1.0 / 120.0      # s: bước dò va chạm lớn nhất của đạn (sai số dây cung g*dt^2/8 = 0,15 mm)


class Bullet:
    __slots__ = ('origin', 'pos', 'vel', 'age', 'alive', 'end_pos')

    def __init__(self, origin, vel):
        self.origin = origin
        self.pos = origin
        self.vel = vel
        self.age = 0.0
        self.alive = True                # False khi trúng hoặc quá hạn; `end_pos` là điểm cuối (cho tracer)
        self.end_pos = origin


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
                 audio=None, fx=None, shake=None):
        self.gun = params.gun
        self.fb = params.feedback
        self.player = player
        self.targets = targets
        self.static_boxes = static_boxes           # [(lo, hi, owner)]
        self.rng = rng or random.Random()
        self.audio = audio                         # GunAudio hoặc None (tắt tiếng)
        self.fx = fx                               # Effects (tia lửa đầu nòng, tracer) hoặc None
        self.foley = None                          # Foley (tiếng đạn trúng, cò rỗng) hoặc None; Game gán sau khi dựng
        self.shake = shake                         # core.shake.Shake (rung thuần hình ảnh, không đổi hướng đạn) hoặc None
        self.weapon = Weapon(self.gun)
        self.handling = Handling(self.gun, self.weapon)     # rút súng / nạp đạn
        self.reload_requested = False                       # vừa bấm R
        self.accuracy = Accuracy(self.gun.accuracy)
        self.recoil = CameraRecoil(self.gun.recoil, self.rng)
        self.gun_kick = GunKick(self.gun.kick, self.rng)
        self.free_aim = FreeAim(self.gun.free_aim)
        self.aim_source = None                     # hàm trả về hướng nòng (thế giới); None = ra giữa màn hình
        self.spread_now = self.accuracy.angle(player.state, player.ads_amount)   # cho tâm ngắm động
        self.last_shot = None
        self.decals = HoleDecals(self.fb, hole_texture())
        for t in targets:
            if t.patrol is not None:
                self.decals.prepare_owner(t.root)
        self.bullets = []
        self.pressed = False                       # vừa bóp cò (sự kiện nhấn chuột, dùng cho bắn đơn)
        self.require_locked_mouse = True           # không bắn khi người chơi đã nhả chuột bằng Esc
        self.hit_marker_left = 0.0
        self.last_hit_distance = None
        self.last_hit_left = 0.0
        self.last_impact = None
        self.shots_fired = 0
        self.target_hits = 0
        self.frame_dt = 1.0 / 60.0                 # độ dài khung đang xử lý (bia chạy nội suy vị trí theo khung này)
        self._hit_frac = 1.0                       # phần của khung mà viên đạn vừa trúng nằm ở (cho lỗ đạn trên bia chạy)

    def request_reload(self):
        """Phím R. Có hiệu lực ở khung kế tiếp nếu nạp được (xem `_update_handling`)."""
        self.reload_requested = True

    def _update_handling(self, trigger: bool, mouse_ok: bool, real_dt: float):
        """Nạp đạn: tiến clip, chạy nước rút cắt reload, bắt đầu nạp (phím R, hoặc bóp cò khi băng cạn)."""
        h, r = self.handling, self.gun.reload
        h.update(real_dt)
        if self.shake:
            self.shake.watch_reload(h.key, h.frame, 30.0 * h.speed)    # mốc rung của clip nạp (băng vào chỗ, bolt); huỷ nạp thì các mốc chưa tới bị bỏ
        sprinting = r.sprint_cancels and self.player.sprint_amount > 0
        if h.phase is Phase.RELOAD and sprinting:
            h.cancel()
        wants = self.reload_requested or (mouse_ok and (trigger or self.pressed) and self.weapon.mag == 0)
        self.reload_requested = False
        if wants and not sprinting:                    # đang chạy thì chưa nạp: tư thế chạy chưa hạ hẳn là chưa dứt
            h.start_reload()
        self.player.ads_blocked = h.busy

    # --- mỗi khung hình ---
    def update(self, dt: float, real_dt: float = None):
        """`dt` đã cắt ở 50 ms cho vật lý; `real_dt` là thời gian thật của khung (cho clip nạp đạn chạy theo đồng hồ Panda)."""
        self.frame_dt = dt
        for t in self.targets:             # bia chạy đi trước hết: đạn trong khung này dò va chạm theo vị trí bia từng bước nhỏ
            t.update(dt)
        self.hit_marker_left = max(0.0, self.hit_marker_left - dt)
        self.last_hit_left = max(0.0, self.last_hit_left - dt)

        self._step_bullets(dt)           # đạn cũ đi trước, đạn mới sinh ra sau (đã tự đẩy tới cuối khung)

        mouse_ok = (mouse.locked or not self.require_locked_mouse) and not self.player.ui_open       # bảng debug (F1) mở: chuột là của bảng
        trigger = bool(held_keys['left mouse']) and mouse_ok
        self._update_handling(trigger, mouse_ok, dt if real_dt is None else real_dt)
        # đang hạ súng sau khi chạy (sprint-to-fire) hoặc đang nạp / rút súng thì chưa bắn được
        ready = mouse_ok and self.player.can_fire and self.handling.can_fire
        held = trigger and ready
        pressed = self.pressed and ready
        if pressed and self.foley and self.weapon.out_of_ammo:
            self.foley.on_dry_fire()
        if ready or not trigger or self.handling.busy:
            self.pressed = False                       # còn giữ cò mà súng chưa sẵn sàng vì chạy: nhớ cú bóp để bắn khi sẵn sàng (nạp thì bỏ)
        self.accuracy.update(dt)
        ages = self.weapon.update(dt, held, pressed)
        if ages:
            origin, view_dir = self.player.aim_ray()
            if self.aim_source is not None:
                view_dir = self.aim_source()
            for age in ages:
                state, ads = self.player.state, self.player.ads_amount
                spread = self.accuracy.angle(state, ads)
                direction = random_in_cone(view_dir, spread, self.rng)
                self.last_shot = ShotInfo(view_dir, direction, spread, state)
                self._fire(origin, direction, age)
                self.accuracy.on_shot()
                gun_up, gun_right = self.recoil.on_shot(self.recoil.posture_scale(ads, self.player.crouching))
                self.free_aim.on_shot(gun_up, gun_right)
                self.gun_kick.on_shot(ads, age)
                if self.shake:
                    self.shake.on_shot(age)
                if self.audio:
                    self.audio.play_shot()
        up, right = self.recoil.step(dt)
        if up or right:
            self.player.kick_view(up, right)       # sau khi bắn: phát này đã đi theo hướng nhìn trước cú giật
        self.gun_kick.update(dt)
        self.free_aim.update(dt, self.player.turn_rate(dt))
        if self.shake:
            self.shake.update(dt)          # sau mọi sự kiện rung của khung (phát bắn có tuổi, mốc nạp): xử lý theo đúng thời điểm
        if self.fx:
            self.fx.update(dt)
        self.spread_now = self.accuracy.angle(self.player.state, self.player.ads_amount)

    def _boxes(self) -> list:
        """Hộp đứng yên của khung này: bia đứng yên + tường/cột/đất. Bia đang chạy xử lý riêng theo từng bước (`_advance`)."""
        return [(*t.aabb(), t) for t in self.targets if not t.moving] + self.static_boxes

    def _fire(self, origin, direction, age: float):
        speed = self.gun.muzzle_velocity
        bullet = Bullet(origin, tuple(c * speed for c in direction))
        self.shots_fired += 1
        if self.fx:
            self.fx.on_shot(bullet, self.player.ads_amount)
        # đạn sinh ra ở thời điểm (cuối khung - age) rồi tự đẩy tiếp tới cuối khung
        if self._advance(bullet, age, self._boxes(), self.frame_dt - age):
            self.bullets.append(bullet)

    def _step_bullets(self, dt: float):
        if not self.bullets:
            return
        boxes = self._boxes()
        self.bullets = [b for b in self.bullets if self._advance(b, dt, boxes, 0.0)]

    def _advance(self, bullet: Bullet, dt: float, boxes: list, t_begin: float = 0.0) -> bool:
        """Đẩy đạn đi dt giây. Trả về False nếu đạn hết (trúng gì đó hoặc quá hạn).

        Chia nhỏ khung dài thành các bước <= MAX_BULLET_STEP: điểm trúng dò trên dây cung của từng bước nên lệch tối đa g*dt^2/8 so với
        cung thật; khung treo 40 ms (vd. khung đầu tiên hiện tia lửa) cho lệch 2-3 mm ở 10 m nếu không chia.

        `t_begin` (s kể từ đầu khung) là lúc đạn bắt đầu đoạn này. Bia chạy dịch từ `x_start` tới `x_end` trong khung, nên mỗi bước nhỏ
        dò đạn với hộp bia ở ĐÚNG vị trí đầu bước và để hộp tịnh tiến theo trong bước (`moving_hit`: chính xác với chuyển động đều,
        không lệch `tốc độ bia x dt` như khi lấy vị trí cuối khung)."""
        steps = max(1, math.ceil(dt / MAX_BULLET_STEP - 1e-9))
        step = dt / steps
        movers = [t for t in self.targets if t.moving]
        frame = max(self.frame_dt, 1e-9)
        for i in range(steps):
            new_pos, new_vel = advance(bullet.pos, bullet.vel, self.gun.bullet_gravity, step)
            hit = first_hit(bullet.pos, new_pos, boxes)
            if movers:
                f0 = min(max((t_begin + i * step) / frame, 0.0), 1.0)
                f1 = min(max((t_begin + (i + 1) * step) / frame, 0.0), 1.0)
                for t in movers:
                    x0, x1 = t.x_at(f0), t.x_at(f1)
                    lo, hi = t.aabb_at_x(x0)
                    h = moving_hit(bullet.pos, new_pos, lo, hi, (x1 - x0, 0.0, 0.0), t)
                    if h and (hit is None or h.t < hit.t):
                        hit = h
                        self._hit_frac = f0 + (f1 - f0) * h.t
            if hit:
                bullet.alive, bullet.end_pos = False, hit.point
                self._on_hit(bullet, hit)
                return False
            bullet.pos, bullet.vel = new_pos, new_vel
        bullet.age += dt
        if bullet.age >= self.gun.bullet_lifetime:
            bullet.alive, bullet.end_pos = False, bullet.pos
            return False
        return True

    # --- phản hồi ---
    def _on_hit(self, bullet: Bullet, hit):
        distance = distance_between(bullet.origin, hit.point)
        self.last_impact = Impact(hit.point, hit.normal, distance, hit.owner, bullet.origin)
        if self.foley:
            self.foley.on_impact(isinstance(hit.owner, Target), distance)
        if isinstance(hit.owner, Target):
            self.target_hits += 1
            hit.owner.flash()
            self.hit_marker_left = self.fb.hit_marker_duration
            self.last_hit_distance = distance
            self.last_hit_left = self.fb.last_hit_display_time
            # Lỗ nằm ở chỗ đạn trúng TRÊN bia lúc trúng; bia đã đi tiếp tới cuối khung nên dời lỗ theo, để nó đứng đúng chỗ trên mặt bia
            point = hit.point
            if hit.owner.patrol is not None:
                shift = hit.owner.x_end - hit.owner.x_at(self._hit_frac)
                point = (point[0] + shift, point[1], point[2])
            self.decals.add(point, hit.normal, distance, parent=hit.owner.root)
        else:
            self.decals.add(hit.point, hit.normal, distance, tint=DUST_TINT)

    # --- trạng thái cho HUD ---
    @property
    def hit_marker_alpha(self) -> float:
        return self.hit_marker_left / self.fb.hit_marker_duration if self.fb.hit_marker_duration else 0.0
