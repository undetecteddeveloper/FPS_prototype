"""Per-frame sound schedule for a clip (pure, no ursina import, so it can be tested without a window).

Each reload / draw clip has a `SoundCue` table (absolute frames in the glb file, 30 fps). When the clip starts at speed `speed`, each mark
is converted to REAL seconds = (frame - clip.start) / 30 / speed (a faster clip brings the marks earlier). The schedule's clock adds the same `dt`
that `Handling.update` adds, so the two agree to within one frame. Reload / draw commands are processed AFTER that frame's `Handling.update` (the new clip starts at t = 0),
so the first `update` after `start` does not add `dt` (otherwise the sound would come one frame early).

Handling events (see core/handling.py):
  start(key, speed) schedules · done() plays the remaining sounds (the last frame may miss some) · cancel() drops marks not yet reached,
  sounds already played are left to ring out; if at least one sound has played, one more 'hand slides back' sound is scheduled after `cancel_delay`.
"""
from fps.weapon_data import AudioData, Clip

FPS = 30.0


class CueSchedule:
    def __init__(self):
        self._pending = []          # [(real seconds since start, name, volume)] sorted by time
        self._t = 0.0
        self.fired = 0              # sounds played in the current run (to decide whether a cancel adds the 'hand slides back' sound)
        self.running = False
        self._fresh = False         # just started this frame: this frame does not count time

    def start(self, cues, clip: Clip, speed: float):
        """Schedule clip `clip` to run at speed `speed`. Marks before the start of the clip play immediately."""
        speed = max(speed, 1e-3)
        self._pending = sorted(((max(0.0, (c.frame - clip.start) / FPS / speed), c.sound, c.volume) for c in cues), key=lambda e: e[0])
        self._t, self.fired, self.running = 0.0, 0, True
        self._fresh = True

    def update(self, dt: float) -> list:
        """Advance the clock by `dt` seconds: returns [(name, volume)] of the marks just reached, in time order."""
        if not self._pending:
            return []
        if self._fresh:
            self._fresh = False
        else:
            self._t += dt
        out = []
        while self._pending and self._pending[0][0] <= self._t:
            _, name, volume = self._pending.pop(0)
            out.append((name, volume))
        self.fired += len(out)
        return out

    def flush(self) -> list:
        """Clip finished: play all remaining marks."""
        out = [(name, volume) for _, name, volume in self._pending]
        self._pending = []
        self.fired += len(out)
        self.running = False
        return out

    def cancel(self, audio: AudioData):
        """Cancel: drop all marks not yet reached. If at least one sound has played, schedule a 'hand slides back' sound (a clip cancelled at its start has no hand movement yet, so it stays silent)."""
        had_sound = self.fired > 0
        self._pending = []
        self.running = False
        if had_sound and audio.cancel_sound:
            self._pending = [(self._t + audio.cancel_delay, audio.cancel_sound, audio.cancel_volume)]

    @property
    def pending_names(self) -> list:
        return [name for _, name, _ in self._pending]


def impact_sound(audio, distance: float, on_target: bool) -> tuple:
    """Impact sound as heard by the shooter: (delay in seconds, volume). Sound travels from the impact point to the ear, so it arrives late and gets quieter with distance."""
    distance = max(distance, 0.0)
    base = audio.hit_target_volume if on_target else audio.hit_hard_volume
    return distance / max(audio.speed_of_sound, 1.0), base / (1.0 + distance / max(audio.hit_reference_distance, 1e-3))

