"""Pure shot control (no ursina import): fire rate from RPM, round count, automatic / semi-auto mode.

`update` returns, for every shot fired during the frame, the number of seconds elapsed since the moment
that shot fired (counted to the END of the frame). The bullet is born then pushed forward by exactly that time, so the bullet's position
is not quantised to frames, and the average fire rate equals the RPM exactly at any FPS.
"""
from collections import deque

from fps.weapon_data import GunData


class Weapon:
    def __init__(self, gun: GunData):
        self.gun = gun
        self._rpm = gun.rpm
        self.interval = 60.0 / gun.rpm       # re-read from gun.rpm every frame (the debug panel can change rpm while running)
        self.mag_size = gun.magazine
        self.mag = gun.magazine
        self.reserve = gun.reserve
        self.auto = gun.full_auto
        self.cooldown = 0.0                  # time left until the next shot may fire (at the end of the frame)
        self.clock = 0.0
        self.shot_times = deque(maxlen=2048)  # time of each shot (for the RPM check)

    def toggle_mode(self):
        """Key B: auto <-> semi. A gun without `selective_fire` (the M1014) keeps its mode."""
        if self.gun.selective_fire:
            self.auto = not self.auto

    @property
    def can_reload(self) -> bool:
        return self.mag < self.mag_size and self.reserve > 0

    @property
    def out_of_ammo(self) -> bool:
        return self.mag == 0 and self.reserve == 0

    def load_magazine(self) -> int:
        """Fill the magazine from reserve to full (at the moment the new magazine seats). Returns the number loaded.
        Rounds are one shared pool: rounds still in the old magazine still count (total mag + reserve unchanged)."""
        take = min(self.mag_size - self.mag, self.reserve)
        self.mag += take
        self.reserve -= take
        return take

    def load_shell(self) -> int:
        """Tube magazine: ONE round goes in from the reserve (when the shell is pushed into the loading port). Returns the number loaded: 1, or 0 if the gun is full / the reserve is empty."""
        if self.mag >= self.mag_size or self.reserve <= 0:
            return 0
        self.mag += 1
        self.reserve -= 1
        return 1

    def update(self, dt: float, trigger_held: bool, trigger_pressed: bool) -> list:
        self.clock += dt
        if self.gun.rpm != self._rpm and self.gun.rpm > 0:
            self._rpm = self.gun.rpm
            self.interval = 60.0 / self._rpm
        # resting (cooldown <= 0): the first shot fires exactly 'now' (age 0), not counted as fired from the start of the frame
        self.cooldown = self.cooldown - dt if self.cooldown > 0 else 0.0
        wants = trigger_held if self.auto else trigger_pressed
        if not wants and self.cooldown < 0:
            self.cooldown = 0.0              # no build-up of fire-rate 'credit' when the trigger is released
        ages = []
        while wants and self.cooldown <= 0 and self.mag > 0:
            age = -self.cooldown
            ages.append(age)
            self.shot_times.append(self.clock - age)
            self.mag -= 1
            self.cooldown += self.interval
            if not self.auto:
                break                        # semi-auto: one shot per trigger pull
        return ages
