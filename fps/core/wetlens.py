"""Wet lens after the camera comes up out of the water (pure Python; tests/test_wetlens.py). Drawn by assets/shaders/lens.frag (`lens_film`, `lens_drops`).

When the lens port leaves the water, a FILM of water covers what was under: its top edge runs down the frame (gravity: slow at first, then faster) and is gone after
`film_time`. Behind it stay a few DROPS; each one shows up when the film edge passes it, creeps down a little, shrinks and dries within its own life.
Everything is a closed-form function of the time since surfacing (no per-frame accumulation), so 30 and 240 FPS show the same drops at the same moment.
Coordinates: the lens shader's p space, x in [-1, 1] across the width, y in [-1, 1] bottom to top; drop radii in units of half the frame WIDTH (isotropic).
"""
import math
import random

from fps.weapon_data import UnderwaterData

FILM_POWER = 1.7          # the film edge position goes with (age / film_time) ** FILM_POWER: a slow start, then it runs off
MIN_DIP = 0.04            # a dip covering less of the frame than this leaves nothing


def film_front(age: float, top: float, film_time: float) -> float:
    """y of the film's top edge `age` s after surfacing (it starts at `top` and reaches -1 at film_time); below the edge the lens is still covered."""
    if film_time <= 0.0:
        return -1.0
    u = min(max(age / film_time, 0.0), 1.0)
    return top - (top + 1.0) * u ** FILM_POWER


def film_passes(y: float, top: float, film_time: float) -> float:
    """Age at which the film edge reaches height y (inverse of film_front)."""
    if top <= -1.0:
        return 0.0
    k = min(max((top - y) / (top + 1.0), 0.0), 1.0)
    return film_time * k ** (1.0 / FILM_POWER)


class Drop:
    __slots__ = ('x', 'y0', 'r', 'life', 'slide', 'appear')

    def __init__(self, x, y0, r, life, slide, appear):
        self.x, self.y0, self.r, self.life, self.slide, self.appear = x, y0, r, life, slide, appear

    def at(self, age: float):
        """(x, y, radius, alpha) at `age` s after surfacing, or None before it shows / after it dried."""
        a = age - self.appear
        if a < 0.0 or a >= self.life:
            return None
        u = a / self.life
        y = self.y0 - self.slide * a ** 1.3                    # creeps down, a little faster as it goes (gravity beats the sticking)
        r = self.r * math.sqrt(1.0 - u)                         # evaporates: the area goes down about linearly
        alpha = 1.0 if u < 0.7 else (1.0 - u) / 0.3
        return self.x, y, r, alpha


class WetLens:
    def __init__(self, d: UnderwaterData, rng: random.Random = None):
        self.d = d
        self.rng = rng or random.Random()
        self.t = 0.0
        self.t0 = None              # clock when the port last left the water (None: no wet lens)
        self.top = -1.0             # highest y the water reached during the dip
        self.strength = 0.0         # 0..1: how much of the frame was under during the dip
        self.drops = []
        self._dip_top = -1.0
        self._dip_share = 0.0

    def update(self, dt: float, share: float, top: float):
        """`share` = part of the frame under the water now (core/underwater.py wet_share), `top` = highest wet y (wet_top)."""
        self.t += dt
        if share > 0.0:                                         # (still) in the water: nothing drains; remember how far it reached
            self._dip_share = max(self._dip_share, share)
            self._dip_top = max(self._dip_top, top)
            self.t0 = None
            return
        if self._dip_share >= MIN_DIP:                          # just came out: start a film + drops
            self._start(self._dip_share, self._dip_top)
        self._dip_share, self._dip_top = 0.0, -1.0

    def _start(self, share: float, top: float):
        d, rng = self.d, self.rng
        self.t0, self.top, self.strength = self.t, top, min(share * 1.5, 1.0)
        self.drops = []
        n = int(round(d.drops * self.strength))
        for _ in range(n):
            y0 = rng.uniform(-0.9, max(top - 0.05, -0.85))
            r = d.drop_size * rng.uniform(0.5, 1.4)
            self.drops.append(Drop(rng.uniform(-0.92, 0.92), y0, r, d.drop_life * rng.uniform(0.6, 1.3),
                                   d.drop_slide * rng.uniform(0.3, 1.6) * r / max(d.drop_size, 1e-6), film_passes(y0, top, d.film_time)))

    @property
    def age(self):
        return None if self.t0 is None else self.t - self.t0

    def film(self) -> tuple:
        """(edge y, strength): the covered part is below the edge; strength 0 = no film."""
        age = self.age
        if age is None or age >= self.d.film_time:
            return -1.0, 0.0
        return film_front(age, self.top, self.d.film_time), self.strength

    def visible_drops(self) -> list:
        age = self.age
        if age is None:
            return []
        return [s for s in (dr.at(age) for dr in self.drops) if s is not None]

    def active(self) -> bool:
        return self.film()[1] > 0.0 or bool(self.visible_drops())

    def packed(self, slots: int) -> list:
        """[(x, y, r, alpha)] * slots for the shader (unused slots: radius 0)."""
        out = self.visible_drops()[:slots]
        return out + [(0.0, 0.0, 0.0, 0.0)] * (slots - len(out))
