"""G20: the sounds of the boot splash and the graphics panel (assets/sounds/ui, made by tools/build/make_ui_sounds.py). Loaded once; a missing file is skipped (the UI is silent
there, never a crash). Keystroke ticks rotate through three variants and are rate-limited, so a fast typewriter never retriggers one sample into a buzz.
The window going to the background mutes every sound manager (Game._mute), UI sounds included."""
from pathlib import Path

from panda3d.core import Filename
from ursina import application

NAMES = ('boot_degauss', 'boot_hum', 'key_0', 'key_1', 'key_2', 'blip', 'ok', 'relay', 'rec_start', 'ui_open', 'ui_close', 'ui_move', 'ui_change')
VOLUME = {                           # per-sound level (the files are normalised to ~0.5 of full scale: the UI must stay under the game's own sound)
    'boot_degauss': 0.55, 'boot_hum': 0.22, 'key': 0.30, 'blip': 0.40, 'ok': 0.35, 'relay': 0.50, 'rec_start': 0.50,
    'ui_open': 0.45, 'ui_close': 0.40, 'ui_move': 0.35, 'ui_change': 0.45,
}
KEY_MIN_GAP = 0.035                  # s between two keystroke ticks


class UiAudio:
    def __init__(self, root: Path, enabled: bool = True, master: float = 1.0):
        self.master = master
        self.sounds = {}
        self._key = 0
        self._last_key = -1.0
        base = getattr(application, 'base', None)
        if not enabled or base is None:
            return
        folder = Path(root) / 'assets' / 'sounds' / 'ui'
        for name in NAMES:
            path = folder / f'{name}.wav'
            if not path.exists():
                print(f'[ui] thiếu {path.name}')
                continue
            try:
                self.sounds[name] = base.loader.load_sfx(Filename.from_os_specific(str(path)))
            except Exception as e:                     # a broken file must not stop the game
                print(f'[ui] không nạp được {path.name}: {type(e).__name__}: {e}')

    def play(self, name: str, rate: float = 1.0, volume: float = None):
        s = self.sounds.get(name)
        if s is None:
            return
        s.set_volume(self.master * (VOLUME.get(name, 0.4) if volume is None else volume))
        s.set_play_rate(rate)
        s.play()

    def tick(self, now: float):
        """One keystroke of the typewriter effect (rate-limited, three variants in turn)."""
        if now - self._last_key < KEY_MIN_GAP:
            return
        self._last_key = now
        self._key = (self._key + 1) % 3
        self.play(f'key_{self._key}', rate=1.0, volume=VOLUME['key'])

    def loop(self, name: str, volume: float = None):
        s = self.sounds.get(name)
        if s is not None:
            s.set_loop(True)
            s.set_volume(self.master * (VOLUME.get(name, 0.3) if volume is None else volume))
            s.play()

    def set_volume(self, name: str, volume: float):
        s = self.sounds.get(name)
        if s is not None:
            s.set_volume(self.master * volume)

    def stop(self, name: str):
        s = self.sounds.get(name)
        if s is not None:
            s.stop()
