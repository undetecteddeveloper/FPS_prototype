"""Foley: tiếng kim loại khi nạp / rút súng (theo khung animation) và bước chân, nhảy, chạm đất trên gạch.

Toán nằm ở core: `core.cues.CueSchedule` (khi nào tới mốc nào, huỷ thì bỏ mốc chưa tới) và `core.footsteps.Footsteps` (nhịp bước theo quãng đường).
Ở đây chỉ ghép với Panda: nạp file `assets/sounds/foley/<tên>_<số>.wav` (dựng bằng tools/build/prep_foley.py), phát từ vòng luân phiên (mỗi file `AudioData.pool` bản,
tiếng sau không cắt đuôi tiếng trước), đổi cao độ / âm lượng / lệch kênh theo sự kiện. Không có thiết bị âm thanh thì Panda phát âm câm, không lỗi.

Móc vào `Game.update` (không có update riêng): `on_handling_event(event)` cho từng sự kiện của Handling, rồi `update(dt)` một lần mỗi khung.
Tắt tiếng (`--mute`, `create_game(sound=False)`) thì Game không tạo đối tượng này.
"""
import math
import random
from collections import Counter, deque
from pathlib import Path

from panda3d.core import Filename
from ursina import application

from fps.core.breath import Breathing
from fps.core.cues import CueSchedule, impact_sound
from fps.core.footsteps import FootEvent, Footsteps, pick_variant
from fps.weapon_data import AudioData, GunData

STEP_NAMES = ('step_walk', 'step_run', 'land', 'jump')
TELEPORT_DISTANCE = 3.0       # m: bước nhảy vị trí trong một khung lớn hơn mức này là dịch chuyển, không tính là đi


class _Bank:
    """Mọi biến thể của một nhóm tiếng; mỗi biến thể có `pool` bản phát luân phiên."""

    def __init__(self, voices: list):
        self.voices = voices                       # [[AudioSound, ...], ...]
        self.cursor = [0] * len(voices)
        self.last = None

    def next_sound(self, rng: random.Random):
        v = pick_variant(rng, len(self.voices), self.last)
        self.last = v
        sounds = self.voices[v]
        sound = sounds[self.cursor[v]]
        self.cursor[v] = (self.cursor[v] + 1) % len(sounds)
        return v, sound


class Foley:
    def __init__(self, audio: AudioData, gun: GunData, player, project_root: Path, rng: random.Random = None):
        self.audio = audio
        self.gun = gun
        self.player = player
        self.rng = rng or random.Random()
        self.schedule = CueSchedule()
        self.steps = Footsteps(audio, self.rng)
        self.breathing = Breathing(audio, gun.sway)
        self._px, self._pz = player.x, player.z

        names = set(STEP_NAMES) | {audio.cancel_sound, 'dry', 'hit_target', 'hit_hard', 'breath'}
        for cues in audio.cues.values():
            names.update(c.sound for c in cues)
        names.discard(None)
        self.banks = {name: self._load_bank(name, project_root) for name in sorted(names)}

        self.clock = 0.0                           # giây đã chạy (cộng dt), để kiểm thời điểm phát
        self.counts = Counter()                    # số lần phát theo tên nhóm (cho kiểm tra)
        self.log = deque(maxlen=512)               # (clock, tên, âm lượng, biến thể) các tiếng gần nhất
        self.last_sound = None
        self.pending = []                          # (đồng hồ lúc phát, tên, âm lượng, cao độ): tiếng đạn trúng đang trên đường về tai người bắn

    def _load_bank(self, name: str, project_root: Path) -> _Bank:
        folder = project_root / self.audio.folder
        group = self.audio.sound_files.get(name, name)             # tên logic -> nhóm file (tiếng người dùng cung cấp hoặc tổng hợp)
        files = sorted(folder.glob(f'{group}_*.wav'))
        if not files:
            raise FileNotFoundError(f'thiếu {folder}\\{group}_*.wav: chạy tools\\build\\prep_foley.py (tiếng user_*: tools\\build\\prep_user_audio.py; el_*: tools\\build\\prep_elevenlabs.py)')
        loader = application.base.loader
        return _Bank([[loader.load_sfx(Filename.from_os_specific(str(f))) for _ in range(max(1, self.audio.pool))] for f in files])

    # --- phát ---
    def play(self, name: str, volume: float, pitch: float = 1.0, pan: float = 0.0, fit_hz: float = 0.0):
        """`fit_hz` > 0: kéo giãn tiếng cho vừa một chu kỳ 1 / fit_hz giây (chỉ trong khoảng 0,85-1,2 lần)."""
        variant, sound = self.banks[name].next_sound(self.rng)
        if fit_hz > 0.0 and sound.length() > 0.0:
            pitch *= min(max(sound.length() * fit_hz, 0.85), 1.2)
        sound.set_volume(min(max(volume, 0.0), 1.0))
        sound.set_play_rate(pitch * self.audio.pitch_scale.get(name, 1.0))
        sound.set_balance(min(max(pan, -1.0), 1.0))
        sound.play()                               # phát lại từ đầu nếu bản này còn đang vang (chỉ khi cả vòng đã quay hết)
        self.counts[name] += 1
        self.log.append((self.clock, name, volume, variant))
        self.last_sound = sound

    def _play_cues(self, cues: list):
        for name, volume in cues:
            self.play(name, volume * self.audio.reload_volume)

    def _play_foot(self, ev: FootEvent):
        name = {'step': 'step_run' if ev.run else 'step_walk', 'land': 'land', 'jump': 'jump'}[ev.kind]
        pan = 0.0 if ev.kind == 'land' else (self.audio.foot_pan if ev.foot else -self.audio.foot_pan)
        self.play(name, ev.gain, ev.pitch, pan)

    def on_impact(self, on_target: bool, distance: float):
        """Đạn vừa trúng: tiếng va tới tai sau `distance / tốc độ âm thanh` giây."""
        a = self.audio
        delay, volume = impact_sound(a, distance, on_target)
        pitch = 1.0 + self.rng.uniform(-a.hit_pitch_variation, a.hit_pitch_variation)
        self.pending.append((self.clock + delay, 'hit_target' if on_target else 'hit_hard', volume, pitch))

    def on_dry_fire(self):
        """Bóp cò khi đã hết sạch đạn: game không có HUD nên đây là cách duy nhất biết hết đạn, cùng với khoá nòng."""
        self.play('dry', self.audio.dry_volume)

    # --- móc vào Game.update ---
    def on_handling_event(self, event: tuple):
        """Sự kiện của core.handling.Handling: ('start', key, speed) / ('swap', key) / ('done', key) / ('cancel', key, frame)."""
        kind = event[0]
        if kind == 'start':
            key, speed = event[1], event[2]
            self.schedule.start(self.audio.cues.get(key, ()), self.gun.clips[key], speed)
        elif kind == 'done':
            self._play_cues(self.schedule.flush())
        elif kind == 'cancel':
            self.schedule.cancel(self.audio)

    def update(self, dt: float, bob_phase: float = None, sway=None, ads: float = 0.0):
        """Mỗi khung, SAU khi đã xử lý các sự kiện của Handling (cùng `dt` thật với Handling.update) và SAU `Sway.update` (để pha bob là của khung này).
        `bob_phase` = Sway.phase: bước chân phát đúng lúc súng chạm điểm thấp nhất của bob. `sway` = Sway (đồng hồ thở + bob), `ads` = player.ads_amount: tiếng thở."""
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
        if sway is not None:
            volume = self.breathing.update(sway.clock, sway.bob_amount, ads, p.on_ground)
            if volume is not None and volume > 0.0:
                self.play('breath', volume, fit_hz=self.gun.sway.breath_freq)
