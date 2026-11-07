"""Pure draw and reload handling (no ursina import, so it can be tested without a window).

Four-phase state machine: READY (can fire) -> DRAW (drawing the gun when entering the game or after a weapon switch) / RELOAD (reloading) /
HOLSTER (putting the gun away before a weapon switch) -> READY.
Timing follows the glb clip (30 fps frames) times `speed`. The round count changes exactly at the `Clip.swap` frame
(new magazine seated), not at the start of the clip: cancelling before that point keeps the rounds; cancelling after it means the magazine is already loaded.

The visual part (playing the clip, blending the pose on cancel) is in `game/viewmodel.py`, which receives the events through `drain()`:
  ('start', key, speed)   start playing clip `key` (key of GunData.clips)
  ('swap', key)           new magazine seated (rounds updated)
  ('done', key)           clip finished
  ('cancel', key, frame)  cancelled mid-way at frame `frame` of the clip
"""
from enum import Enum

from fps.core.weapon import Weapon
from fps.weapon_data import GunData

FPS = 30.0


class Phase(Enum):
    READY = 'ready'
    DRAW = 'draw'
    RELOAD = 'reload'
    HOLSTER = 'holster'


class Handling:
    def __init__(self, gun: GunData, weapon: Weapon):
        self.gun = gun
        self.weapon = weapon
        self.phase = Phase.READY
        self.key = None             # key of the running clip ('draw', 'reload', 'reload_empty')
        self.t = 0.0                # seconds OF THE CLIP (multiplied by speed) since the clip started
        self.swapped = False
        self.loaded = 0             # rounds loaded at the most recent magazine change
        self.events = []

    # --- read ---
    @property
    def clip(self):
        return self.gun.clips[self.key] if self.key else None

    @property
    def busy(self) -> bool:
        return self.phase is not Phase.READY

    @property
    def can_fire(self) -> bool:
        return self.phase is Phase.READY

    @property
    def speed(self) -> float:
        r = self.gun.reload
        return r.draw_speed if self.phase in (Phase.DRAW, Phase.HOLSTER) else r.speed

    @property
    def progress(self) -> float:
        """0..1 progress of the running clip (0 when idle)."""
        if not self.busy:
            return 0.0
        return min(self.t / self.clip.duration, 1.0)

    @property
    def frame(self) -> float:
        """Current frame (real number) on the file's shared timeline; None when idle."""
        if not self.busy:
            return None
        return min(self.clip.start + self.t * FPS, float(self.clip.end))

    @property
    def remaining(self) -> float:
        """Real seconds remaining until done."""
        if not self.busy:
            return 0.0
        return max(self.clip.duration - self.t, 0.0) / self.speed

    # --- commands ---
    def start_draw(self) -> bool:
        if self.busy:
            return False
        self._start(Phase.DRAW, 'draw')
        return True

    def start_holster(self) -> bool:
        """Put the gun away (first half of a weapon switch). Only from READY; the 'done' event of key 'holster' tells Game to swap the gun."""
        if self.busy:
            return False
        self._start(Phase.HOLSTER, 'holster')
        return True

    def start_reload(self) -> bool:
        """Start reloading if allowed: idle, magazine not full, reserve left. An empty magazine uses the Reload_Empty clip."""
        if self.busy or not self.weapon.can_reload:
            return False
        self._start(Phase.RELOAD, 'reload_empty' if self.weapon.mag == 0 else 'reload')
        return True

    def cancel(self) -> bool:
        """Cancel the running reload (cannot cancel Draw). Rounds already loaded at the magazine-change point are kept."""
        if self.phase is not Phase.RELOAD:
            return False
        self.events.append(('cancel', self.key, self.frame))
        self._finish()
        return True

    def _start(self, phase: Phase, key: str):
        self.phase, self.key, self.t, self.swapped = phase, key, 0.0, False
        self.events.append(('start', key, self.speed))

    def _finish(self):
        self.phase, self.key, self.t = Phase.READY, None, 0.0

    # --- every frame ---
    def update(self, dt: float):
        """`dt` is the real frame time (not capped at 50 ms): visuals run on the Panda clock, so the logic follows it too."""
        if not self.busy:
            return
        self.t += dt * self.speed
        clip = self.clip
        if not self.swapped and clip.swap is not None and self.t >= clip.swap_time:
            self.swapped = True
            self.loaded = self.weapon.load_magazine()
            self.events.append(('swap', self.key))
        if self.t >= clip.duration:
            self.events.append(('done', self.key))
            self._finish()

    def drain(self) -> list:
        out, self.events = self.events, []
        return out
