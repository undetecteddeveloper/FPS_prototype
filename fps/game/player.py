"""Người chơi: bộ điều khiển tự viết (FirstPersonController của Ursina không có đủ trạng thái).

`state` (MoveState) là nguồn duy nhất cho tốc độ, spread (G3) và sway (G4).
Phím: WASD đi, Shift chạy nước rút (giữ), Ctrl hoặc C ngồi (giữ), Space nhảy, chuột phải ngắm (giữ), chuột nhìn.
Recoil camera (G3) đi vào qua `kick_view`. ADS và tư thế chạy là hai tiến độ 0..1 (`ads_amount`, `sprint_amount`);
đường cong êm (smoothstep) chỉ áp khi dùng, còn tiến độ thô để spread và sprint-to-fire dùng.
"""
import math

from ursina import Entity, camera, held_keys, mouse, time

from fps.core.movement import (MoveState, aim_direction, apply_look, clamp_to_bounds, resolve_state, smoothstep,
                      step_horizontal_velocity, step_toward, step_vertical, target_speed, wants_sprint, wish_direction)
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import SwayInput
from fps.weapon_data import GunData, PlayerParams

MAX_DT = 0.05   # sau một cú giật (nạp, cửa sổ kéo) không để vật lý nhảy một bước quá lớn


class Player(Entity):
    def __init__(self, params: PlayerParams, walk_bounds: tuple, gun: GunData):
        super().__init__(position=(0, 0, 0))
        self.p = params
        self.gun = gun
        self.walk_bounds = walk_bounds

        self.yaw = 0.0
        self.pitch = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.crouching = False
        self.sprinting = False
        self.ads = False                      # đang giữ nút ngắm
        self.ui_open = False                  # bảng debug F1 mở: chuột trái / phải không còn là bắn / ngắm
        self.ads_blocked = False              # đang nạp / rút súng: nút ngắm không có tác dụng (animation tay không khớp tư thế ngắm)
        self.ads_amount = 0.0                 # 0 hông .. 1 ngắm hẳn; spread (spread.py) nội suy theo số này
        self.sprint_amount = 0.0              # 0 .. 1 tiến độ hạ súng vào tư thế chạy; về 0 mới bắn được
        self.landed = 0.0                     # tốc độ chạm đất (m/s) nếu khung này vừa chạm đất
        self.eye_dy = 0.0                     # camera đi lên/xuống bao nhiêu mét trong khung này (cho quán tính súng)
        self.eye_height = params.eye_height_stand
        self.state = MoveState.IDLE
        self._look = [0.0, 0.0]               # chuột đã quay (yaw phải, pitch lên) độ, từ lần lấy gần nhất
        self._dip = Spring(1, params.land_dip_omega, params.land_dip_zeta)   # camera nhún khi chạm đất

        self.camera_pivot = Entity(parent=self, y=self.eye_height)
        camera.parent = self.camera_pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = params.fov
        mouse.locked = True

    # --- đọc phím ---
    def read_keys(self) -> dict:
        free = not self.ui_open        # bảng debug (F1) đang mở: bấm chuột là để rê thanh trượt, không ngắm cũng không bắn
        return dict(
            forward=held_keys['w'] - held_keys['s'],
            strafe=held_keys['d'] - held_keys['a'],
            sprint=bool(held_keys['shift']),
            crouch=bool(held_keys['control'] or held_keys['c']),
            jump=bool(held_keys['space']),
            ads=bool(held_keys['right mouse']) and not self.ads_blocked and free,
            fire=bool(held_keys['left mouse']) and free,
        )

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vz)

    @property
    def can_fire(self) -> bool:
        """Sprint-to-fire: bóp cò khi đang chạy thì súng phải hạ lên lại (sprint_out_time) rồi mới bắn được."""
        return not self.p.sprint_blocks_fire or self.sprint_amount <= 0.0

    def aim_ray(self) -> tuple:
        """(gốc, hướng) của tia ngắm: từ mắt (đã gồm cú nhún chạm đất), theo hướng nhìn (đã gồm recoil camera).
        Độ tản cộng thêm ở Combat."""
        return (self.x, self.y + self.camera_pivot.y, self.z), aim_direction(self.yaw, self.pitch)

    def sway_input(self) -> SwayInput:
        """Chuyển động của khung hình này cho Sway. Lấy chuột xong thì xoá, nên mỗi khung chỉ gọi một lần."""
        look = (self._look[0], self._look[1])
        self._look = [0.0, 0.0]
        return SwayInput(self.state, self.speed, self.ads_amount, self.sprint_amount, look, self.eye_dy, self.landed)

    # --- vòng lặp (Game.update gọi, để thứ tự cập nhật rõ ràng: người chơi -> bắn -> sway -> súng -> HUD) ---
    def tick(self):
        if mouse.locked:
            self.look(mouse.velocity[0], mouse.velocity[1])
        self.step(min(time.dt, MAX_DT), **self.read_keys())

    def look(self, dx: float, dy: float):
        sens = self.p.mouse_sensitivity * (1.0 + (self.p.ads_look_multiplier - 1.0) * smoothstep(self.ads_amount))
        self.yaw, self.pitch = apply_look(self.yaw, self.pitch, dx, dy, sens, self.p.pitch_limit)
        self._look[0] += dx * sens
        self._look[1] += dy * sens
        self._apply_view()

    def kick_view(self, up: float, right: float):
        """Recoil camera: lệch góc nhìn (độ). Cộng thẳng vào yaw/pitch nên người chơi phải kéo chuột bù."""
        self.yaw = (self.yaw + right) % 360.0
        self.pitch = min(max(self.pitch - up, -self.p.pitch_limit), self.p.pitch_limit)
        self._apply_view()

    def _apply_view(self):
        self.rotation_y = self.yaw
        self.camera_pivot.rotation_x = self.pitch

    def step(self, dt: float, forward: float, strafe: float, sprint: bool, crouch: bool, jump: bool,
             ads: bool = False, fire: bool = False):
        p = self.p
        has_input = forward != 0 or strafe != 0
        eye_y0 = self.y + self.eye_height
        self.ads = ads
        self.landed = 0.0

        if self.on_ground:
            self.sprinting = wants_sprint(sprint, forward, ads) and not (fire and p.sprint_blocks_fire)
            self.crouching = crouch and not self.sprinting
            if jump:
                self.vy = p.jump_speed
                self.on_ground = False
        # trên không: giữ nguyên tư thế, chỉ lái nhẹ

        self.ads_amount = step_toward(self.ads_amount, 1.0 if ads else 0.0, 1.0 / self.gun.ads_time, dt)
        sprint_active = self.sprinting and has_input
        sprint_time = self.gun.sprint_in_time if sprint_active else self.gun.sprint_out_time
        self.sprint_amount = step_toward(self.sprint_amount, 1.0 if sprint_active else 0.0, 1.0 / sprint_time, dt)

        intent = resolve_state(self.on_ground, self.crouching, self.sprinting, has_input)
        wish = wish_direction(forward, strafe, self.yaw)
        accel = p.accel_ground if self.on_ground else p.accel_air
        speed = target_speed(intent, p, smoothstep(self.ads_amount)) if has_input else 0.0
        if self.on_ground or has_input:       # trên không mà không bấm phím thì giữ nguyên đà
            self.vx, self.vz = step_horizontal_velocity(self.vx, self.vz, wish, speed, accel, dt)

        if not self.on_ground:
            vy_before = self.vy
            self.y, self.vy, self.on_ground = step_vertical(self.y, self.vy, p.gravity, dt)
            if self.on_ground:
                self.landed = max(0.0, p.gravity * dt - vy_before)     # tốc độ rơi ngay trước khi chạm
        x, z = clamp_to_bounds(self.x + self.vx * dt, self.z + self.vz * dt, self.walk_bounds)
        if x != self.x + self.vx * dt:
            self.vx = 0.0
        if z != self.z + self.vz * dt:
            self.vz = 0.0
        self.x, self.z = x, z

        self.state = resolve_state(self.on_ground, self.crouching, self.sprinting, self.speed > p.moving_speed_threshold)

        target_eye = p.eye_height_crouch if self.crouching else p.eye_height_stand
        self.eye_height = step_toward(self.eye_height, target_eye, p.eye_height_change_speed, dt)
        self.eye_dy = (self.y + self.eye_height) - eye_y0

        self._dip.omega, self._dip.zeta = p.land_dip_omega, p.land_dip_zeta
        if self.landed > 0:
            self._dip.kick([-p.land_dip_per_speed * self.landed * impulse_gain(p.land_dip_omega, p.land_dip_zeta)])
        self._dip.step(dt)
        self.camera_pivot.y = self.eye_height + self._dip.x[0]

        fov = p.fov + (self.gun.ads_fov - p.fov) * smoothstep(self.ads_amount)
        if abs(camera.fov - fov) > 1e-4:
            camera.fov = fov
