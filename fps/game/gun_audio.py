"""Gunshot sound: a pool of sound copies used in rotation, so a later shot does not cut off the tail of the previous one.

At 750 rounds/min (80 ms) with a 0.5 s sound, about 6 sounds ring at once; each shot takes the next copy in the ring.
Each shot changes pitch slightly at random (`shot_pitch_variation`) so it does not sound like a repeated recording. Values live in weapon_data.GunData.
With no audio device, Panda returns silence, with no error.
"""
import random
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.weapon_data import GunData


class GunAudio:
    def __init__(self, gun: GunData, project_root: Path, rng: random.Random = None):
        self.gun = gun
        self.rng = rng or random.Random()
        loader = application.base.loader
        # shot_sound: one path or several variants; the copies in the ring take the variants in turn, so two consecutive shots do not sound identical
        files = (gun.shot_sound,) if isinstance(gun.shot_sound, str) else tuple(gun.shot_sound)
        self.sounds = [loader.load_sfx(Filename.from_os_specific(str(project_root / files[i % len(files)]))) for i in range(max(1, gun.shot_pool))]
        self._next = 0
        self.played = 0                    # number of sounds played (for checks)

    def play_shot(self):
        sound = self.sounds[self._next]
        self._next = (self._next + 1) % len(self.sounds)
        sound.set_volume(self.gun.shot_volume)
        v = self.gun.shot_pitch_variation
        sound.set_play_rate(1.0 + self.rng.uniform(-v, v) if v else 1.0)
        sound.play()                       # restarts from the beginning if this copy is still ringing (only when the whole ring has gone round)
        self.played += 1
