"""Two separate recoil layers (pure math, no ursina import):

- `CameraRecoil`: generates a random recoil kick per shot (no fixed pattern). The `camera_share` part shifts the VIEW (added to the player's yaw/pitch, so the player
  must pull the mouse to compensate; after firing stops, a `recovery` part returns on its own); the rest goes to `FreeAim` to drift the gun off centre.
- `GunKick`: the gun's own kick on screen, a damped spring. Its rotation part also changes the barrel direction, so it also changes the bullet direction.

Angles: 'up' and 'right' positive, in degrees. Every number lives in weapon_data.RecoilData / GunKickData.
"""
import math
import random

from fps.core.movement import smoothstep
from fps.core.spring import Spring, impulse_gain
from fps.weapon_data import GunKickData, RecoilData


class CameraRecoil:
    def __init__(self, data: RecoilData, rng: random.Random = None):
        self.d = data
        self.rng = rng or random.Random()
        self.clock = 0.0
        self.last_shot = None             # clock value at the last shot
        self.walk = 0.0                   # horizontal tendency of the current burst; random-walks per shot
        self.pending = [0.0, 0.0]         # (up, right) kick computed but not yet applied to the view
        self.burst = [0.0, 0.0]           # net total of this burst; recovery takes a fraction of this
        self.rec = [0.0, 0.0]             # how much is still to recover
        self.armed = False                # fired but recovery not yet accounted for

    def on_shot(self, scale: float = 1.0) -> tuple:
        """One shot: generate a random kick; the `camera_share` part is queued into the view; returns (up, right) degrees; the rest is for the gun to drift (`FreeAim.on_shot`).
        `scale` = pose factor (aiming, crouching): see `posture_scale`."""
        d = self.d
        if self.last_shot is None or self.clock - self.last_shot > d.burst_reset_time:
            self.walk = 0.0
            self.burst = [0.0, 0.0]
        self.walk = min(max(self.walk + self.rng.uniform(-d.right_walk, d.right_walk), -d.right_walk_max), d.right_walk_max)
        up = (d.up + self.rng.uniform(-d.up_noise, d.up_noise)) * d.up_scale * scale
        right = (d.right_bias + self.walk + self.rng.uniform(-d.right_noise, d.right_noise)) * d.right_scale * scale
        share = min(max(d.camera_share, 0.0), 1.0)
        self.pending[0] += up * share
        self.pending[1] += right * share
        self.burst[0] += up * share
        self.burst[1] += right * share
        self.rec = [0.0, 0.0]             # firing again cancels recovery
        self.armed = True
        self.last_shot = self.clock
        return up * (1.0 - share), right * (1.0 - share)

    def posture_scale(self, ads: float, crouching: bool) -> float:
        """Kick factor by posture: stock pressed to the shoulder when aiming, low centre of gravity when crouching."""
        d = self.d
        k = 1.0 + (d.ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        return k * (d.crouch_scale if crouching else 1.0)

    def step(self, dt: float) -> tuple:
        """Return (up, right) degrees to add to the view this frame; negative = recovering."""
        d = self.d
        k = 1.0 - math.exp(-dt / d.kick_time) if d.kick_time > 0 else 1.0
        applied = [self.pending[0] * k, self.pending[1] * k]
        self.pending[0] -= applied[0]
        self.pending[1] -= applied[1]

        self.clock += dt
        if self.armed and self.clock - self.last_shot >= d.recovery_delay:
            self.armed = False
            self.rec = [self.burst[0] * d.recovery, self.burst[1] * d.recovery]
        kr = 1.0 - math.exp(-dt / d.recovery_time) if d.recovery_time > 0 else 1.0
        back = [self.rec[0] * kr, self.rec[1] * kr]
        for i in (0, 1):
            self.rec[i] -= back[i]
            self.burst[i] -= back[i]
        return applied[0] - back[0], applied[1] - back[1]


class GunKick:
    """6 components: (x right, y up, z forward, pitch up, yaw right, roll right), metres and degrees."""

    def __init__(self, data: GunKickData, rng: random.Random = None):
        self.d = data
        self.rng = rng or random.Random()
        self.spring = Spring(6, data.omega, data.zeta)
        self.back = Spring(2, data.back_omega, data.back_zeta)       # knock-back: [z, x along]; its own spring, slower, so shots pile up
        self._pending = []                                           # (age in the frame, 6-component impulse, knock-back impulse) waiting for `update`

    def on_shot(self, ads: float = 0.0, age: float = None):
        """One shot. `ads` 0 hip .. 1 fully aimed: knock-back multiplied by `back_ads_scale` (smoothstep blend like the other visual effects; < 1 kicks back less than hip, > 1 kicks back more).
        `age` = how long before the end of the frame this shot fired (as `Weapon.update` returns it): the impulse is applied at that moment in `update`, so
        the burst's peak is the same at any FPS. Leave empty = apply now (start of frame)."""
        d = self.d
        gain = impulse_gain(d.omega, d.zeta)
        imp = [(p + self.rng.uniform(-r, r)) * gain for p, r in zip(d.peak, d.random)]
        k = 1.0 + (d.back_ads_scale - 1.0) * smoothstep(min(max(ads, 0.0), 1.0))
        back_z = (d.back_peak + self.rng.uniform(-d.back_random, d.back_random)) * k * impulse_gain(d.back_omega, d.back_zeta)
        back = (back_z, back_z * d.back_x_ratio * (1.0 - smoothstep(min(max(ads, 0.0), 1.0))))     # x only when hip: the gun sits to the right of the eye, so pulling it toward the eye would push it off the edge; when aiming, the sight line must stay on axis
        if age is None:
            self.spring.omega, self.spring.zeta = d.omega, d.zeta
            self.back.omega, self.back.zeta = d.back_omega, d.back_zeta
            self.spring.kick(imp)
            self.back.kick(back)
        else:
            self._pending.append((age, imp, back))

    def _step(self, h: float):
        if h <= 0.0:
            return
        d = self.d
        self.spring.omega, self.spring.zeta = d.omega, d.zeta
        self.spring.step(h)
        self.back.omega, self.back.zeta = d.back_omega, d.back_zeta
        self.back.step(h)

    def update(self, dt: float):
        left = dt
        for age, imp, back in sorted(self._pending, key=lambda e: -e[0]):      # oldest first
            age = min(max(age, 0.0), left)
            self._step(left - age)
            left = age
            self.spring.kick(imp)
            self.back.kick(back)
        self._pending.clear()
        self._step(left)

    @property
    def pose(self) -> tuple:
        x, y, z, pitch, yaw, roll = self.spring.x
        return (x + self.back.x[1], y, z + self.back.x[0], pitch, yaw, roll)
