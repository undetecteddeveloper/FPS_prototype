"""Graphics settings (pure Python; tests/test_graphics.py). The graphics panel (Esc, game/graphics_panel.py) edits a GraphicsSettings; `resolve` turns it into the GraphicsLevel every
effect reads. The three presets are weapon_data.GRAPHICS_LEVELS (Thấp / Vừa / Cao); anti-aliasing and the FPS counter are independent of the preset.
Switching changes uniforms and buffers only (no shader recompiles); anti-aliasing rebuilds the lens buffer (a few ms, only when it changes)."""
import json
from dataclasses import asdict, dataclass, fields

from fps.weapon_data import GRAPHICS_LEVELS, GraphicsLevel

SIM_SIZES = ((0, 0), (128, 256), (256, 512))      # wave simulation: off / mid / high
CAUSTIC_SIZES = ((0, 0, 0), (256, 512, 1024), (384, 768, 2048))   # caustics: off / mid / high = (light mesh cols, rows, texels on the long side)
SHAFT_SAMPLES = (0, 1, 3)                         # sun shafts: off / mid / high (dust noise samples per lit piece)
SPLASH_SHARE = (0.0, 0.6, 1.0)                    # droplets: off / few / all
AA_SAMPLES = (0, 2, 4)                            # MSAA samples of the scene buffer
RENDER_SCALES = (1.0, 0.75, 0.5)                  # G13: share of the window size the 3D image is drawn at


@dataclass
class GraphicsSettings:
    sim: int = 2              # index into SIM_SIZES
    refraction: bool = True   # clear water (see the bottom)
    caustics: int = 2         # index into CAUSTIC_SIZES
    glint: bool = True
    shafts: int = 2           # index into SHAFT_SAMPLES
    splash: int = 2           # index into SPLASH_SHARE
    wet: bool = True
    gun_env: bool = True
    dust: bool = True
    under: int = 1            # G12 under the water: 0 simple, 1 full
    scale: int = 0           # G13: index into RENDER_SCALES
    smoke: bool = True        # G13: gun smoke shaded fully (False = per corner, cheaper)
    surface: int = 2          # 8/11/2026: surface detail of the tiles and bullet holes: 0 flat, 1 normal map, 2 parallax
    aa: int = 0              # MSAA samples (0 / 2 / 4)
    show_fps: bool = False


PRESET_FIELDS = ('sim', 'refraction', 'caustics', 'glint', 'shafts', 'splash', 'wet', 'gun_env', 'dust', 'under', 'scale', 'smoke', 'surface')
G13_FIELDS = ('scale', 'smoke', 'surface')     # rows added after G12: a file saved before them keeps its preset whole (`from_json`)

# (field, label, [(value, text)]) for the graphics panel (Esc; G20: English, upper case, label <= 38 and value <= 8 characters so the panel columns never move);
# 'preset' is the row that applies a whole level. The saved file keeps the values (not the texts): translating a text never breaks user_graphics.json.
OPTIONS = (
    ('preset', 'GRAPHICS PRESET', [(0, 'LOW'), (1, 'MED'), (2, 'HIGH')]),
    ('aa', 'ANTI-ALIASING (MSAA)', [(0, 'OFF'), (2, '2X'), (4, '4X')]),
    ('scale', 'RENDER RESOLUTION', [(0, '100%'), (1, '75%'), (2, '50%')]),
    ('sim', 'WATER WAVE SIMULATION', [(0, 'OFF'), (1, 'MED'), (2, 'HIGH')]),
    ('refraction', 'WATER REFRACTION (SEE BOTTOM)', [(False, 'OFF'), (True, 'ON')]),
    ('caustics', 'POOL FLOOR CAUSTICS', [(0, 'OFF'), (1, 'MED'), (2, 'HIGH')]),
    ('glint', 'WATER SUN GLINT', [(False, 'OFF'), (True, 'ON')]),
    ('shafts', 'VOLUMETRIC SUN SHAFTS', [(0, 'OFF'), (1, 'MED'), (2, 'HIGH')]),
    ('dust', 'AIRBORNE DUST', [(False, 'OFF'), (True, 'ON')]),
    ('splash', 'WATER SPLASH DROPLETS', [(0, 'OFF'), (1, 'FEW'), (2, 'MANY')]),
    ('wet', 'WET DECK / FOOTPRINTS', [(False, 'OFF'), (True, 'ON')]),
    ('gun_env', 'WEAPON ROOM REFLECTION', [(False, 'OFF'), (True, 'ON')]),
    ('under', 'UNDERWATER EFFECTS', [(0, 'SIMPLE'), (1, 'FULL')]),
    ('smoke', 'GUN SMOKE', [(False, 'SIMPLE'), (True, 'FULL')]),
    ('surface', 'SURFACE DETAIL (TILES, IMPACTS)', [(0, 'FLAT'), (1, 'MED'), (2, 'HIGH')]),
    ('show_fps', 'FPS COUNTER', [(False, 'OFF'), (True, 'ON')]),
)
CUSTOM_TEXT = 'CUSTOM'                  # the preset row when the settings match no preset


def clamp_level(i: int) -> int:
    return min(max(int(i), 0), len(GRAPHICS_LEVELS) - 1)


def next_level(i: int) -> int:
    """Thấp -> Vừa -> Cao -> Thấp."""
    return (clamp_level(i) + 1) % len(GRAPHICS_LEVELS)


def level(i: int) -> GraphicsLevel:
    return GRAPHICS_LEVELS[clamp_level(i)]


def settings_for(i: int, keep: GraphicsSettings = None) -> GraphicsSettings:
    """The settings of preset `i`; anti-aliasing and the FPS counter are taken from `keep` (they are not part of a preset)."""
    g = level(i)
    s = GraphicsSettings(sim=SIM_SIZES.index((g.sim_cols, g.sim_rows)), refraction=g.refraction, caustics=g.caustics, glint=g.glint,
                         shafts=SHAFT_SAMPLES.index(g.shaft_steps), splash=SPLASH_SHARE.index(g.splash), wet=g.wet, gun_env=g.gun_env, dust=g.dust,
                         under=g.under, scale=RENDER_SCALES.index(g.render_scale), smoke=not g.smoke_simple, surface=g.surface)
    if keep is not None:
        s.aa, s.show_fps = keep.aa, keep.show_fps
    return s


def resolve(s: GraphicsSettings) -> GraphicsLevel:
    """The GraphicsLevel the effects read, built from the panel's settings."""
    p = preset_of(s)
    cols, rows = SIM_SIZES[s.sim]
    return GraphicsLevel(GRAPHICS_LEVELS[p].name if p is not None else 'Tuỳ chỉnh', cols, rows, s.refraction, s.caustics, s.glint,
                         SHAFT_SAMPLES[s.shafts], SPLASH_SHARE[s.splash], s.wet, s.gun_env, s.dust, s.under, RENDER_SCALES[s.scale], not s.smoke, s.surface)


def preset_of(s: GraphicsSettings):
    """Index of the preset these settings equal (anti-aliasing / FPS counter ignored), or None (custom)."""
    for i in range(len(GRAPHICS_LEVELS)):
        p = settings_for(i)
        if all(getattr(p, f) == getattr(s, f) for f in PRESET_FIELDS):
            return i
    return None


def water_flags(g: GraphicsLevel) -> tuple:
    """vec4 for water.frag `water_quality`: (wave simulation on, see the bottom, caustics, sun sparkle), each 0 or 1."""
    return (1.0 if g.sim_cols > 0 else 0.0, 1.0 if g.refraction else 0.0, 1.0 if g.caustics > 0 else 0.0, 1.0 if g.glint else 0.0)


def lite_water(g: GraphicsLevel) -> bool:
    """G13: the water quad can use its POOL_LITE build (every feature it reads is off, as on Low): no sim, clear water, caustics, sparkle, shafts, relief; simple underwater."""
    return g.sim_cols == 0 and not g.refraction and g.caustics == 0 and not g.glint and g.shaft_steps == 0 and g.under == 0 and g.surface == 0


def lite_basin(g: GraphicsLevel) -> bool:
    """G13: the basin mesh can use its POOL_LITE build: no caustics, no tile relief, simple underwater."""
    return g.caustics == 0 and g.under == 0 and g.surface == 0


def lite_room(g: GraphicsLevel) -> bool:
    """G13: the room mesh can use its POOL_LITE build: no wet deck, no shafts, no tile relief."""
    return not g.wet and g.shaft_steps == 0 and g.surface == 0


def cycle(s: GraphicsSettings, field: str, step: int) -> GraphicsSettings:
    """The panel's left / right on one row: the next (or previous) choice of `field`; 'preset' applies a whole level."""
    choices = next(c for f, _, c in OPTIONS if f == field)
    values = [v for v, _ in choices]
    if field == 'preset':
        cur = preset_of(s)
        i = (cur + step) % len(values) if cur is not None else (2 if step > 0 else 0)
        return settings_for(i, keep=s)
    cur = getattr(s, field)
    i = (values.index(cur) + step) % len(values) if cur in values else 0
    out = GraphicsSettings(**asdict(s))
    setattr(out, field, values[i])
    return out


def choice_text(s: GraphicsSettings, field: str) -> str:
    choices = next(c for f, _, c in OPTIONS if f == field)
    if field == 'preset':
        p = preset_of(s)
        return choices[p][1] if p is not None else CUSTOM_TEXT
    v = getattr(s, field)
    return next((t for val, t in choices if val == v), str(v))


def to_json(s: GraphicsSettings) -> str:
    return json.dumps({'version': 1, 'graphics': asdict(s)}, ensure_ascii=False, indent=2)


def from_json(text: str) -> GraphicsSettings:
    """Unknown or out-of-range values fall back to the default of that field (an old / hand-edited file never breaks the start).
    Text that is not a JSON object with a "graphics" object (broken, empty, a list...) raises ValueError: the caller keeps its defaults."""
    raw = json.loads(text)                       # json.JSONDecodeError is a ValueError
    data = raw.get('graphics', {}) if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        raise ValueError('không đúng dạng (cần {"graphics": {...}})')
    s = GraphicsSettings()
    for f in fields(GraphicsSettings):
        if f.name not in data:
            continue
        v = data[f.name]
        choices = next((c for name, _, c in OPTIONS if name == f.name), None)
        if choices is not None and v not in [val for val, _ in choices]:
            continue
        if type(v) is type(getattr(s, f.name)):
            setattr(s, f.name, v)
    missing = [f for f in G13_FIELDS if f not in data]
    if missing:                          # a file saved before G13: keep its preset whole (a saved Thấp gets the 75% / simple smoke that Thấp now has)
        for i in range(len(GRAPHICS_LEVELS)):
            p = settings_for(i)
            if all(getattr(p, f) == getattr(s, f) for f in PRESET_FIELDS if f not in missing):
                for f in missing:
                    setattr(s, f, getattr(p, f))
                break
    return s
