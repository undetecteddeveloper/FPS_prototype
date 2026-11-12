"""Foley: metal sounds when reloading / drawing the gun (following the animation frames), and footsteps, jumps and landings on tiles.

The maths lives in core: `core.cues.CueSchedule` (when each cue fires; cancelling drops cues not yet reached) and `core.footsteps.Footsteps` (step timing by distance walked).
Here it is only wired to Panda: loads `assets/sounds/foley/<name>_<n>.wav` files (built by the tools/build/prep_*.py scripts), plays them from a round-robin pool (`AudioData.pool` copies each,
so a later sound does not cut off the previous one), and changes pitch / volume / stereo pan per event. With no audio device, Panda plays silence, with no error.

Hooked into `Game.update` (no separate update): `on_handling_event(event)` for each Handling event, then `update(dt)` once per frame.
Muted (`--mute`, `create_game(sound=False)`) means Game does not create this object.
"""
import math
import random
from collections import Counter, deque
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.core.cues import CueSchedule, impact_sound
from fps.core.footsteps import FootEvent, Footsteps, pick_variant
from fps.weapon_data import AudioData, GunData

STEP_NAMES = ('step_walk', 'step_run', 'land', 'jump')
WATER_NAMES = {'wade': 3, 'water_land': 2}     # G10, optional groups (AudioData water sounds) -> playback copies; wading steps come ~0.3 s apart and the splash rings longer, so 3 copies
TELEPORT_DISTANCE = 3.0       # m: a position jump larger than this within one frame is a teleport, not walking


class _Bank:
    """Every variant of one sound group; each variant has `pool` copies that play in rotation. `voices_under` = the same files muffled (G12, tools/build/prep_underwater.py), or None."""

    def __init__(self, voices: list, voices_under: list = None):
        self.voices = voices                       # [[AudioSound, ...], ...]
        self.voices_under = voices_under
        self.cursor = [0] * len(voices)
        self.cursor_under = [0] * len(voices)
        self.last = None

    def next_sound(self, rng: random.Random, under: bool = False):
        v = pick_variant(rng, len(self.voices), self.last)
        self.last = v
        if under and self.voices_under is not None:
            sounds, cursor = self.voices_under[v], self.cursor_under
        else:
            sounds, cursor = self.voices[v], self.cursor
        sound = sounds[cursor[v]]
        cursor[v] = (cursor[v] + 1) % len(sounds)
        return v, sound


class Foley:
    def __init__(self, audio: AudioData, gun: GunData, player, project_root: Path, rng: random.Random = None):
        self.audio = audio
        self.gun = gun
        self.player = player
        self.rng = rng or random.Random()
        self.schedule = CueSchedule()
        self.steps = Footsteps(audio, self.rng)
        self._px, self._pz = player.x, player.z

        names = set(STEP_NAMES) | {audio.cancel_sound, 'dry', 'hit_hard'}
        for cues in audio.cues.values():
            names.update(c.sound for c in cues)
        names.discard(None)
        self.banks = {name: self._load_bank(name, project_root) for name in sorted(names)}
        for name, copies in WATER_NAMES.items():   # G10: optional (a missing group is silent)
            if self._has_files(name, project_root):
                self.banks[name] = self._load_bank(name, project_root, copies)

        self.under = False                         # G12: the eye is under the water: every sound plays from its muffled twin (Game sets it each frame)
        self.clock = 0.0                           # seconds elapsed (dt added), to check when sounds play
        self.counts = Counter()                    # number of plays per group name (for checks)
        self.log = deque(maxlen=512)               # (clock, name, volume, variant) of the most recent sounds
        self.last_sound = None
        self.pending = []                          # (clock at play, name, volume, pitch): hit sound still travelling to the shooter's ear

    def _has_files(self, name: str, project_root: Path) -> bool:
        group = self.audio.sound_files.get(name, name)
        return any((project_root / self.audio.folder).glob(f'{group}_*.wav'))

    def _load_bank(self, name: str, project_root: Path, copies: int = None) -> _Bank:
        folder = project_root / self.audio.folder
        group = self.audio.sound_files.get(name, name)             # logical name -> file group (user-supplied or synthesized sounds)
        files = sorted(folder.glob(f'{group}_*.wav'))
        if not files:
            raise FileNotFoundError(f'thiếu {folder / (group + "_*.wav")} (dựng lại: el_*: tools/build/prep_elevenlabs.py; boot_step: prep_pool_audio.py; '
                                    f'glock_*: prep_glock_audio.py)')      # (was '\b' in a plain string: a backspace character in the message)
        loader = application.base.loader
        n = max(1, copies or self.audio.pool)
        voices = [[loader.load_sfx(Filename.from_os_specific(str(f))) for _ in range(n)] for f in files]
        twins = [project_root / self.audio.folder_under / f.name for f in files]
        under = [[loader.load_sfx(Filename.from_os_specific(str(f))) for _ in range(n)] for f in twins] if all(t.exists() for t in twins) else None
        return _Bank(voices, under)

    def resume(self):
        """Weapon switch: this gun's Foley (kept built while another gun was in hand) takes over again. The player moved meanwhile: that is not a step."""
        self._px, self._pz = self.player.x, self.player.z
        self.pending = []
        self.schedule = CueSchedule()

    # --- playback ---
    def play(self, name: str, volume: float, pitch: float = 1.0, pan: float = 0.0, fit_hz: float = 0.0):
        """`fit_hz` > 0: stretch the sound to fit one period of 1 / fit_hz seconds (only within 0.85-1.2x). A group without files (optional water sounds) is silent."""
        bank = self.banks.get(name)
        if bank is None:
            return
        variant, sound = bank.next_sound(self.rng, self.under)
        if fit_hz > 0.0 and sound.length() > 0.0:
            pitch *= min(max(sound.length() * fit_hz, 0.85), 1.2)
        sound.set_volume(min(max(volume * self.audio.volume_scale.get(name, 1.0), 0.0), 1.0))
        sound.set_play_rate(pitch * self.audio.pitch_scale.get(name, 1.0))
        sound.set_balance(min(max(pan, -1.0), 1.0))
        sound.play()                               # restarts from the beginning if this copy is still ringing (only when the whole ring has gone round)
        self.counts[name] += 1
        self.log.append((self.clock, name, volume, variant))
        self.last_sound = sound

    def _play_cues(self, cues: list):
        for name, volume in cues:
            self.play(name, volume * self.audio.reload_volume)

    def _play_foot(self, ev: FootEvent):
        depth = getattr(self.player, 'water_depth', 0.0)
        if ev.kind in ('step', 'land') and depth > 0.08:                 # feet in the pool: water instead of tiles (G10)
            a = self.audio
            if ev.kind == 'land':
                self.play('water_land', a.water_land_volume * ev.gain / max(a.land_volume, 1e-3))
                return
            # ONE recording for every wading step, calibrated by depth (0 ankle .. 1 chest) and by running (user's choice 7/11/2026)
            k = min(depth / max(a.wade_deep_ref, 0.1), 1.0)
            volume = a.wade_volume * (a.wade_shallow_gain + (1.0 - a.wade_shallow_gain) * k)
            pitch = a.wade_pitch_shallow + (a.wade_pitch_deep - a.wade_pitch_shallow) * k
            if ev.run:
                volume *= a.wade_run_gain
                pitch *= a.wade_run_pitch
            self.play('wade', volume, pitch * ev.pitch, a.foot_pan if ev.foot else -a.foot_pan)
            return
        name = {'step': 'step_run' if ev.run else 'step_walk', 'land': 'land', 'jump': 'jump'}[ev.kind]
        pan = 0.0 if ev.kind == 'land' else (self.audio.foot_pan if ev.foot else -self.audio.foot_pan)
        self.play(name, ev.gain, ev.pitch, pan)

    def on_impact(self, distance: float):
        """A bullet just hit the ground: the impact sound reaches the ear after `distance / speed of sound` seconds."""
        a = self.audio
        delay, volume = impact_sound(a, distance)
        pitch = 1.0 + self.rng.uniform(-a.hit_pitch_variation, a.hit_pitch_variation)
        self.pending.append((self.clock + delay, 'hit_hard', volume, pitch))

    def on_dry_fire(self):
        """Trigger pulled with the magazine empty: the game has no HUD, so this, together with the bolt lock, is the only way to know the gun is out of ammo."""
        self.play('dry', self.audio.dry_volume)

    # --- hooked into Game.update ---
    def on_handling_event(self, event: tuple):
        """Event from core.handling.Handling: ('start', key, speed[, more]) / ('chain', key) / ('swap', key) / ('done', key) / ('cancel', key, frame)."""
        kind = event[0]
        if kind == 'start':
            key, speed = event[1], event[2]
            self.schedule.start(self.audio.cues.get(key, ()), self.gun.clips[key], speed)
        elif kind in ('done', 'ready', 'chain'):          # 'ready': the clip's sounds all lie before it (the tail is only the hands settling); anything left plays now. 'chain': a tube gun's cycle ended, the next starts at once
            self._play_cues(self.schedule.flush())
        elif kind == 'cancel':
            self.schedule.cancel(self.audio)

    def update(self, dt: float, bob_phase: float = None):
        """Every frame, AFTER the Handling events are processed (same real `dt` as Handling.update) and AFTER `Sway.update` (so the bob phase is this frame's).
        `bob_phase` = Sway.phase: footsteps play exactly when the gun reaches the lowest point of the bob."""
        self.clock += dt
        self._play_cues(self.schedule.update(dt))
        if self.pending:
            due = [e for e in self.pending if e[0] <= self.clock]
            if due:
                self.pending = [e for e in self.pending if e[0] > self.clock]
                for _, name, volume, pitch in due:
                    self.play(name, volume, pitch)
        p = self.player
        moved = math.hypot(p.x - self._px, p.z - self._pz)
        self._px, self._pz = p.x, p.z
        if moved > TELEPORT_DISTANCE:
            moved = 0.0
        for ev in self.steps.update(dt, moved, p.on_ground, p.vy, p.landed, p.sprinting, p.crouching, bob_phase):
            self._play_foot(ev)
