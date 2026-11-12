"""Pure draw and reload handling (no ursina import, so it can be tested without a window).

Four-phase state machine: READY (can fire) -> DRAW (drawing the gun when entering the game or after a weapon switch) / RELOAD (reloading) /
HOLSTER (putting the gun away before a weapon switch) -> READY.
Timing follows the glb clip (30 fps frames) times `speed`. The round count changes exactly at the `Clip.swap` frame
(new magazine seated), not at the start of the clip: cancelling before that point keeps the rounds; cancelling after it means the magazine is already loaded.

Tube-magazine guns (GunData.shell_reload, the M1014): a reload loads ONE round per clip cycle ('reload' / 'reload_alt': Clip.swap = the frame the shell goes in) and chains the
cycles until the gun is full or the reserve is empty; an empty gun with a full tube's worth of reserve plays the long 'reload_empty' clip instead (Clip.swaps = one frame per round). Each round
is counted at its own frame (`Weapon.load_shell`), so cancelling keeps what went in. `first` / `last` say where the running clip stands in the chain (the head's glance holds across a chain).

The visual part (playing the clip, blending the pose on cancel) is in `game/viewmodel.py`, which receives the events through `drain()`:
  ('start', key, speed)   start playing clip `key` (key of GunData.clips). Tube guns add a 4th item: True when another cycle will follow this one
  ('chain', key)          tube guns: the cycle `key` ended and the next one starts at once (a 'start' follows); no 'ready' / 'done' in between, the gun never counts as ready
  ('swap', key)           new magazine seated / one more shell in (rounds updated)
  ('done', key)           clip finished
  ('ready', key, tail)    the gun can fire / aim / be swapped / reloaded again; the clip's last `tail` real seconds (only the hands settling) still play on the viewmodel.
                          Comes INSTEAD of 'done' for a draw clip at `Clip.settle`, and for a reload clip at `Clip.settle - ReloadData.ready_lead` (never before the new
                          magazine is seated). Without `Clip.settle` the clip runs to its end and ends with 'done'
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
        self._swaps_done = 0        # tube guns: how many of the running clip's rounds are already in
        self.cycle = 0              # tube guns: index of the running cycle in this reload (0 = the first)
        self.first = True           # the running reload clip is the first / last of its chain (always both for a magazine gun)
        self.last = True

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
        self.cycle = 0
        self._start(Phase.RELOAD, self._first_reload_key())
        return True

    def _first_reload_key(self) -> str:
        """Magazine guns: the empty clip when the magazine is empty. Tube guns: the long empty clip (bolt locked open, every round loaded in one go) only when the reserve can fill the gun;
        otherwise the one-round cycle (with a short reserve the long clip would show shells that are not there)."""
        w, clips = self.weapon, self.gun.clips
        if w.mag != 0:
            return 'reload'
        if self.gun.shell_reload and 'reload_empty' in clips:
            return 'reload_empty' if w.reserve >= len(clips['reload_empty'].swap_times) else 'reload'
        return 'reload_empty'

    def _more_after(self, key: str) -> bool:
        """Tube guns: will another cycle follow clip `key` (assuming nobody interrupts)? True while the gun would still not be full and the reserve not empty after this clip's rounds."""
        if not (self.gun.shell_reload and self.phase is Phase.RELOAD):
            return False
        n = len(self.gun.clips[key].swap_times)
        return self.weapon.mag + n < self.weapon.mag_size and self.weapon.reserve > n

    def cancel(self) -> bool:
        """Cancel the running reload (cannot cancel Draw). Rounds already loaded at the magazine-change point are kept."""
        if self.phase is not Phase.RELOAD:
            return False
        self.events.append(('cancel', self.key, self.frame))
        self._finish()
        return True

    def _start(self, phase: Phase, key: str):
        self.phase, self.key, self.t, self.swapped = phase, key, 0.0, False
        self._swaps_done = 0
        if self.gun.shell_reload and phase is Phase.RELOAD:
            more = self._more_after(key)
            self.first, self.last = self.cycle == 0, not more
            self.events.append(('start', key, self.speed, more))
        else:
            self.first = self.last = True
            self.events.append(('start', key, self.speed))

    def _chain(self):
        """Tube guns: the cycle ended with the gun still not full: the next one starts at once (one-round cycles alternate 'reload' / 'reload_alt' when the gun has both)."""
        prev = self.key
        self.events.append(('chain', prev))
        self.cycle += 1
        alt = 'reload_alt' if prev == 'reload' and 'reload_alt' in self.gun.clips else 'reload'
        self._start(Phase.RELOAD, alt)

    def _finish(self):
        self.phase, self.key, self.t = Phase.READY, None, 0.0

    def ready_time(self):
        """Seconds OF THE CLIP (speed already applied) at which the running clip lets the gun act again, or None to wait for the clip's end.
        Draw: `Clip.settle`. Reload: `Clip.settle` minus `ReloadData.ready_lead` (real seconds), but not before the new magazine is seated. Holster: the end."""
        clip = self.clip
        if clip is None or clip.settle is None:
            return None
        if self.phase is Phase.DRAW:
            return clip.settle_time
        if self.phase is Phase.RELOAD:
            t = clip.settle_time - max(self.gun.reload.ready_lead, 0.0) * self.speed
            if clip.swap_time is not None:
                t = max(t, clip.swap_time)
            return min(t, clip.duration)
        return None

    # --- every frame ---
    def update(self, dt: float):
        """`dt` is the real frame time (not capped at 50 ms): visuals run on the Panda clock, so the logic follows it too."""
        if not self.busy:
            return
        self.t += dt * self.speed
        clip = self.clip
        if self.gun.shell_reload and self.phase is Phase.RELOAD:
            times = clip.swap_times
            while self._swaps_done < len(times) and self.t >= times[self._swaps_done]:
                self._swaps_done += 1
                self.loaded = self.weapon.load_shell()
                self.events.append(('swap', self.key))
            self.swapped = self._swaps_done >= len(times)
        elif not self.swapped and clip.swap is not None and self.t >= clip.swap_time:
            self.swapped = True
            self.loaded = self.weapon.load_magazine()
            self.events.append(('swap', self.key))
        ready = self.ready_time()
        end = clip.duration if ready is None else min(ready, clip.duration)
        if self.gun.shell_reload and self.phase is Phase.RELOAD and self.t >= end and self.weapon.can_reload:
            self._chain()
        elif ready is not None and self.t >= ready and self.t < clip.duration:
            self.events.append(('ready', self.key, max(clip.duration - self.t, 0.0) / self.speed))
            self._finish()
        elif self.t >= clip.duration:
            self.events.append(('done', self.key))
            self._finish()

    def drain(self) -> list:
        out, self.events = self.events, []
        return out
