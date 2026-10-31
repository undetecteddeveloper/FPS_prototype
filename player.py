"""Người chơi: bộ điều khiển tự viết (FirstPersonController của Ursina không có đủ trạng thái).

`state` (MoveState) là nguồn duy nhất cho tốc độ; spread (G3) và sway (G4) cũng đọc từ đây.
Phím: WASD đi, Shift chạy nước rút (giữ), Ctrl hoặc C ngồi (giữ), Space nhảy, chuột nhìn.
"""
import math

from ursina import Entity, camera, held_keys, mouse, time

from movement import (MoveState, aim_direction, apply_look, clamp_to_bounds, resolve_state,
                      step_horizontal_velocity, step_toward, step_vertical, target_speed, wants_sprint, wish_direction)
from weapon_data import PlayerParams

MAX_DT = 0.05   # sau một cú giật (nạp, cửa sổ kéo) không để vật lý nhảy một bước quá lớn


class Player(Entity):
    def __init__(self, params: PlayerParams, walk_bounds: tuple):
        super().__init__(position=(0, 0, 0))
        self.p = params
        self.walk_bounds = walk_bounds

        self.yaw = 0.0
        self.pitch = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.crouching = False
        self.sprinting = False
        self.ads = False                      # G4 sẽ gán; ở đây luôn False
        self.eye_height = params.eye_height_stand
        self.state = MoveState.IDLE

        self.camera_pivot = Entity(parent=self, y=self.eye_height)
        camera.parent = self.camera_pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        camera.fov = params.fov
        mouse.locked = True

    # --- đọc phím ---
    def read_keys(self) -> dict:
        return dict(
            forward=held_keys['w'] - held_keys['s'],
            strafe=held_keys['d'] - held_keys['a'],
            sprint=bool(held_keys['shift']),
            crouch=bool(held_keys['control'] or held_keys['c']),
            jump=bool(held_keys['space']),
        )

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vz)

    def aim_ray(self) -> tuple:
        """(gốc, hướng) của tia ngắm: từ mắt, theo hướng nhìn. G3 sẽ cộng recoil và độ tản vào đây."""
        return (self.x, self.y + self.eye_height, self.z), aim_direction(self.yaw, self.pitch)

    # --- vòng lặp (Game.update gọi, để thứ tự cập nhật rõ ràng: người chơi -> bắn -> súng -> HUD) ---
    def tick(self):
        if mouse.locked:
            self.look(mouse.velocity[0], mouse.velocity[1])
        self.step(min(time.dt, MAX_DT), **self.read_keys())

    def look(self, dx: float, dy: float):
        self.yaw, self.pitch = apply_look(self.yaw, self.pitch, dx, dy, self.p.mouse_sensitivity, self.p.pitch_limit)
        self.rotation_y = self.yaw
        self.camera_pivot.rotation_x = self.pitch

    def step(self, dt: float, forward: float, strafe: float, sprint: bool, crouch: bool, jump: bool):
        p = self.p
        has_input = forward != 0 or strafe != 0

        if self.on_ground:
            self.sprinting = wants_sprint(sprint, forward, self.ads)
            self.crouching = crouch and not self.sprinting
            if jump:
                self.vy = p.jump_speed
                self.on_ground = False
        # trên không: giữ nguyên tư thế, chỉ lái nhẹ

        intent = resolve_state(self.on_ground, self.crouching, self.sprinting, has_input)
        wish = wish_direction(forward, strafe, self.yaw)
        accel = p.accel_ground if self.on_ground else p.accel_air
        speed = target_speed(intent, p, self.ads) if has_input else 0.0
        if self.on_ground or has_input:       # trên không mà không bấm phím thì giữ nguyên đà
            self.vx, self.vz = step_horizontal_velocity(self.vx, self.vz, wish, speed, accel, dt)

        if not self.on_ground:
            self.y, self.vy, self.on_ground = step_vertical(self.y, self.vy, p.gravity, dt)
        x, z = clamp_to_bounds(self.x + self.vx * dt, self.z + self.vz * dt, self.walk_bounds)
        if x != self.x + self.vx * dt:
            self.vx = 0.0
        if z != self.z + self.vz * dt:
            self.vz = 0.0
        self.x, self.z = x, z

        self.state = resolve_state(self.on_ground, self.crouching, self.sprinting, self.speed > p.moving_speed_threshold)

        target_eye = p.eye_height_crouch if self.crouching else p.eye_height_stand
        self.eye_height = step_toward(self.eye_height, target_eye, p.eye_height_change_speed, dt)
        self.camera_pivot.y = self.eye_height
