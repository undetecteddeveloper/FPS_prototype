"""Player: a self-written controller (Ursina's FirstPersonController does not have the states we need).

`state` (MoveState) is the single source for speed, spread (G3) and sway (G4).
Keys: WASD move, Shift sprint (hold), Ctrl or C crouch (hold), Space jump, right mouse aim (hold), mouse look.
The camera-kick part enters through `kick_view`. ADS and the sprint pose are two 0..1 progress values (`ads_amount`, `sprint_amount`);
a smooth curve (smoothstep) is applied only where it is used; the raw progress is what spread and sprint-to-fire use.
"""
import math

from ursina import Entity, camera, held_keys, mouse, time

from fps.core.lens import overscan_fov
from fps.core.movement import (MoveState, aim_direction, apply_look, clamp_to_bounds, resolve_state, smoothstep,
                      step_horizontal_velocity, step_toward, step_vertical, target_speed, wants_sprint, wish_direction)
from fps.core.freeaim import FreeLook
from fps.core.splash import water_depth, water_speed_factor
from fps.core.spring import Spring, impulse_gain
from fps.core.sway import SwayInput
from fps.core.terrain import resolve_move
from fps.weapon_data import GunData, PlayerParams

MAX_DT = 0.05   # after a hitch (reload, window drag) do not let the physics take one oversized step


class Player(Entity):
    def __init__(self, params: PlayerParams, walk_bounds: tuple, gun: GunData, terrain=None, spawn: tuple = (0.0, 0.0, 0.0)):
        """`terrain` (core.terrain.Terrain) gives a floor with steps and solid boxes; without it the floor is the plane y = 0 inside `walk_bounds` (the flat map, the test tools)."""
        super().__init__(position=spawn)
        self.p = params
        self.gun = gun
        self.walk_bounds = walk_bounds
        self.terrain = terrain
        self.step_offset = 0.0                # camera height catching up after a step (m): negative after stepping up, positive after stepping down

        self.yaw = 0.0
        self.pitch = 0.0
        self.vx = 0.0
        self.vz = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.crouching = False
        self.sprinting = False
        self.ads = False                      # holding the aim button
        self.ui_open = False                  # debug panel F1 open: left / right mouse no longer fire / aim
        self.frozen = False                   # G18: dead in the Backrooms level: no keys, no mouse look
        self.slump = 0.0                       # G18: 0 .. 1 the body sinks to the floor and the head tilts (dead)
        self.wall_amount = 0.0                # G14: how far the gun is raised to High Ready because a wall is close (Game sets it each frame, core/weaponcol.py)
        self.wall_blocked = False             # G14: ... and aiming is locked while it is raised
        self.ads_blocked = False              # reloading / drawing the gun: the aim button has no effect (the hand animation does not match the aim pose)
        self.reloading = False                # a reload clip is running (Combat sets it): narrows the free-aim zone; drawing / holstering does not
        self.ads_amount = 0.0                 # 0 hip .. 1 fully aimed; spread (spread.py) interpolates on this value
        self.sprint_amount = 0.0              # 0 .. 1 progress of lowering the gun into the sprint pose; only back at 0 can it fire
        self.landed = 0.0                     # landing speed (m/s) if the player touched down this frame
        self.jumped = 0.0                     # take-off speed (m/s) if the player jumped this frame
        self.eye_dy = 0.0                     # how many metres the camera moves up/down this frame (for gun inertia)
        self.eye_height = params.eye_height_stand
        self.water = None                     # (x0, x1, z0, z1, surface y, chest depth) of the pool on the pool map (Game sets it); None = no water
        self.splash = None                    # weapon_data.SplashData: how much the water slows the legs (Game sets it with `water`)
        self.state = MoveState.IDLE
        self._look = [0.0, 0.0]               # SCREEN turn (yaw right, pitch up) in degrees since the last read: body and lens react to this number
        self._mouse = [0.0, 0.0]              # MOUSE turn since the last read
        self.free_look = FreeLook(gun.free_aim)   # the mouse moves the gun first, the rest turns the screen
        self._dip = Spring(1, params.land_dip_omega, params.land_dip_zeta)   # camera dips on landing

        self.camera_pivot = Entity(parent=self, y=self.eye_height)
        camera.parent = self.camera_pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        self.overscan = 0.0                   # the lens draws the view this much wider and crops it (Game sets it); camera.fov is the RENDERED fov
        self.view_fov = params.fov            # the SHOWN horizontal fov (before overscan)
        camera.fov = params.fov
        mouse.locked = True

    # --- read keys ---
    def read_keys(self) -> dict:
        if self.frozen:
            return dict(forward=0, strafe=0, sprint=False, crouch=False, jump=False, ads=False, fire=False)
        free = not self.ui_open        # debug panel (F1) open: clicking is for dragging sliders, neither aiming nor firing
        return dict(
            forward=held_keys['w'] - held_keys['s'],
            strafe=held_keys['d'] - held_keys['a'],
            sprint=bool(held_keys['shift']),
            crouch=bool(held_keys['control'] or held_keys['c']),
            jump=bool(held_keys['space']),
            ads=bool(held_keys['right mouse']) and not self.ads_blocked and not self.wall_blocked and free and self.gun.can_ads,
            fire=bool(held_keys['left mouse']) and free,
        )

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vz)

    @property
    def can_fire(self) -> bool:
        """Sprint-to-fire: pulling the trigger while sprinting makes the gun come back up (sprint_out_time) before it can fire."""
        return not self.p.sprint_blocks_fire or self.sprint_amount <= 0.0

    def aim_ray(self) -> tuple:
        """(origin, direction) of the aim ray: from the eye (including the landing dip), along the view direction (including camera recoil).
        The spread is added on top in Combat."""
        return (self.x, self.y + self.camera_pivot.y, self.z), aim_direction(self.yaw, self.pitch)

    def turn_rate(self, dt: float) -> float:
        """Magnitude of the mouse turn speed in this frame (deg/s). Call before `sway_input` (that function clears the accumulated values)."""
        return math.hypot(self._mouse[0], self._mouse[1]) / dt if dt > 0 else 0.0

    def sway_input(self) -> SwayInput:
        """Movement of this frame for Sway. Clears the mouse accumulators after reading, so call it once per frame."""
        look = (self._look[0], self._look[1])
        self._look = [0.0, 0.0]
        self._mouse = [0.0, 0.0]
        return SwayInput(self.state, self.speed, self.ads_amount, self.sprint_amount, look, self.eye_dy, self.landed, self.jumped, self.wall_amount)

    def set_gun(self, gun):
        """Weapon switch: the next gun's aim / sprint times and free-look data apply from now on. The free-look STATE (where the gun points off-centre)
        is kept, so the new gun is drawn exactly where the old one was pointing."""
        self.gun = gun
        fl = self.free_look
        fl.d = gun.free_aim
        fl.spring.omega, fl.spring.zeta = gun.free_aim.hand_omega, gun.free_aim.hand_zeta
        self.ads_blocked = False

    # --- loop (Game.update calls it, so the update order is explicit: player -> shooting -> sway -> gun -> HUD) ---
    def tick(self):
        before = tuple(self.free_look.offset)
        if mouse.locked and not self.frozen:
            self.look(mouse.velocity[0], mouse.velocity[1])
        dt = min(time.dt, MAX_DT)
        self.step(dt, **self.read_keys())
        # zone shrinks / head chases the gun: the screen turns while the gun keeps its direction in the world
        reloading = self.reloading and not self.ads
        cam_yaw, cam_up = self.free_look.step(dt, self.ads_amount, self.sprint_amount, reloading, self.speed > self.p.moving_speed_threshold)
        self._turn_view(cam_yaw, cam_up)
        self.free_look.track(before)

    def look(self, dx: float, dy: float):
        """Mouse turn (units of window height): goes into the gun first, the rest turns the screen (FreeLook)."""
        sens = self.p.mouse_sensitivity * (1.0 + (self.p.ads_look_multiplier - 1.0) * smoothstep(self.ads_amount))
        self._mouse[0] += dx * sens
        self._mouse[1] += dy * sens
        cam_yaw, cam_up = self.free_look.apply(dx * sens, dy * sens)
        self._turn_view(cam_yaw, cam_up)

    def _turn_view(self, yaw: float, up: float):
        """Turn the screen (degrees). `_look` accumulates this for the body, sway and lens."""
        if yaw == 0.0 and up == 0.0:
            return
        self.yaw, self.pitch = apply_look(self.yaw, self.pitch, yaw, up, 1.0, self.p.pitch_limit)
        self._look[0] += yaw
        self._look[1] += up
        self._apply_view()

    def kick_view(self, up: float, right: float):
        """Camera recoil: offsets the view angle (degrees). Added straight to yaw/pitch, so the player has to pull the mouse to compensate."""
        self.yaw = (self.yaw + right) % 360.0
        self.pitch = min(max(self.pitch - up, -self.p.pitch_limit), self.p.pitch_limit)
        self._apply_view()

    def _apply_view(self):
        self.rotation_y = self.yaw
        self.camera_pivot.rotation_x = self.pitch

    @property
    def water_depth(self) -> float:
        """How deep his feet are in the pool (0 out of the water)."""
        w = self.water
        if w is None or not (w[0] <= self.x <= w[1] and w[2] <= self.z <= w[3]):
            return 0.0
        return water_depth(self.y, w[4])

    @property
    def eye_y(self) -> float:
        return self.y + self.camera_pivot.y

    @property
    def head_under(self) -> bool:
        """The eye is under the still water level (G12: slower walking; Game also blocks firing then, using the rippled surface)."""
        w = self.water
        return w is not None and w[0] <= self.x <= w[1] and w[2] <= self.z <= w[3] and self.eye_y < w[4]

    def _ground(self) -> float:
        """Height of the floor he can stand on at his position: the highest surface at most `step_up` above his feet (the plane y = 0 without a terrain)."""
        if self.terrain is None:
            return 0.0
        g = self.terrain.floor_at(self.x, self.z, self.y + self.p.step_up)
        return 0.0 if g is None else g

    def step(self, dt: float, forward: float, strafe: float, sprint: bool, crouch: bool, jump: bool,
             ads: bool = False, fire: bool = False):
        p = self.p
        has_input = forward != 0 or strafe != 0
        eye_y0 = self.y + self.eye_height + self.step_offset
        self.ads = ads
        self.landed = 0.0
        self.jumped = 0.0

        if self.on_ground:
            self.sprinting = wants_sprint(sprint, forward, ads) and not (fire and p.sprint_blocks_fire)
            self.crouching = crouch and not self.sprinting
            if jump:
                self.vy = p.jump_speed
                self.jumped = p.jump_speed
                self.on_ground = False
        # in the air: keep the current pose, steering only

        self.ads_amount = step_toward(self.ads_amount, 1.0 if ads else 0.0, 1.0 / self.gun.ads_time, dt)
        sprint_active = self.sprinting and has_input
        sprint_time = self.gun.sprint_in_time if sprint_active else self.gun.sprint_out_time
        self.sprint_amount = step_toward(self.sprint_amount, 1.0 if sprint_active else 0.0, 1.0 / sprint_time, dt)

        intent = resolve_state(self.on_ground, self.crouching, self.sprinting, has_input)
        wish = wish_direction(forward, strafe, self.yaw)
        accel = p.accel_ground if self.on_ground else p.accel_air
        speed = target_speed(intent, p, smoothstep(self.ads_amount)) if has_input else 0.0
        if self.water is not None and self.on_ground:                 # wading: the deeper the water, the slower the legs (G10); head under: walking on the bottom (G12)
            speed *= water_speed_factor(self.water_depth, self.water[5], self.splash.wade_slow, self.head_under, self.splash.under_slow)
        if self.on_ground or has_input:       # in the air with no key pressed: keep the momentum
            self.vx, self.vz = step_horizontal_velocity(self.vx, self.vz, wish, speed, accel, dt)

        # sideways first, so the floor under the NEW position decides whether he steps, falls or lands
        if self.terrain is None:
            x, z = clamp_to_bounds(self.x + self.vx * dt, self.z + self.vz * dt, self.walk_bounds)
            if x != self.x + self.vx * dt:
                self.vx = 0.0
            if z != self.z + self.vz * dt:
                self.vz = 0.0
        else:
            x, z, self.vx, self.vz = resolve_move(self.terrain, self.x, self.z, self.y, self.vx, self.vz, dt, p.radius, p.step_up, p.body_height)
        self.x, self.z = x, z

        ground = self._ground()
        if self.on_ground:
            if ground > self.y + 1e-6:                                  # a step up: the body jumps, the camera catches up smoothly
                self.step_offset -= ground - self.y
                self.y = ground
            elif ground < self.y - 1e-4:
                if self.y - ground <= p.step_up:                        # a step down: stay on the ground (no fall, no landing thump)
                    self.step_offset += self.y - ground
                    self.y = ground
                else:                                                   # a real drop (the pool edge): fall
                    self.on_ground = False
        if not self.on_ground:
            vy_before = self.vy
            self.y, self.vy, self.on_ground = step_vertical(self.y, self.vy, p.gravity, dt, ground)
            if self.on_ground:
                self.landed = max(0.0, p.gravity * dt - vy_before)     # fall speed just before touchdown
        self.step_offset *= math.exp(-p.step_smooth * dt)

        self.state = resolve_state(self.on_ground, self.crouching, self.sprinting, self.speed > p.moving_speed_threshold)

        target_eye = p.eye_height_crouch if self.crouching else p.eye_height_stand
        self.eye_height = step_toward(self.eye_height, target_eye, p.eye_height_change_speed, dt)
        self.eye_dy = (self.y + self.eye_height + self.step_offset) - eye_y0

        self._dip.omega, self._dip.zeta = p.land_dip_omega, p.land_dip_zeta
        if self.landed > 0:
            self._dip.kick([-p.land_dip_per_speed * self.landed * impulse_gain(p.land_dip_omega, p.land_dip_zeta)])
        self._dip.step(dt)
        self.camera_pivot.y = self.eye_height + self._dip.x[0] + self.step_offset
        if self.slump > 0.0 or self.camera_pivot.rotation_z:                 # G18: dead, slumped on the floor
            k = smoothstep(self.slump)
            self.camera_pivot.y -= 1.2 * k
            self.camera_pivot.rotation_z = 26.0 * k

        fov = p.fov + (self.gun.ads_fov - p.fov) * smoothstep(self.ads_amount)
        self.view_fov = fov
        fov = overscan_fov(fov, self.overscan)
        if abs(camera.fov - fov) > 1e-4:
            camera.fov = fov
