"""Graphics settings (pure Python; tests/test_graphics.py). The F2 panel (game/graphics_panel.py) edits a GraphicsSettings; `resolve` turns it into the GraphicsLevel every
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
    wetlens: bool = True      # G12 wet lens after surfacing
    scale: int = 0            # G13: index into RENDER_SCALES
    smoke: bool = True        # G13: gun smoke shaded fully (False = per corner, cheaper)
    aa: int = 0               # MSAA samples (0 / 2 / 4)
    show_fps: bool = False


PRESET_FIELDS = ('sim', 'refraction', 'caustics', 'glint', 'shafts', 'splash', 'wet', 'gun_env', 'dust', 'under', 'wetlens', 'scale', 'smoke')
G13_FIELDS = ('scale', 'smoke')     # rows added in G13: a file saved before them keeps its preset whole (`from_json`)

# (field, label, [(value, text)]) for the F2 panel; 'preset' is the row that applies a whole level
OPTIONS = (
    ('preset', 'Mức chung', [(0, 'Thấp'), (1, 'Vừa'), (2, 'Cao')]),
    ('aa', 'Khử răng cưa', [(0, 'Tắt'), (2, '2x'), (4, '4x')]),
    ('scale', 'Độ phân giải 3D', [(0, '100%'), (1, '75%'), (2, '50%')]),
    ('sim', 'Sóng nước mô phỏng', [(0, 'Tắt'), (1, 'Vừa'), (2, 'Cao')]),
    ('refraction', 'Nước trong (thấy đáy)', [(False, 'Tắt'), (True, 'Bật')]),
    ('caustics', 'Vệt sáng đáy hồ', [(0, 'Tắt'), (1, 'Vừa'), (2, 'Cao')]),
    ('glint', 'Nắng lấp lánh trên nước', [(False, 'Tắt'), (True, 'Bật')]),
    ('shafts', 'Tia nắng trong không khí', [(0, 'Tắt'), (1, 'Vừa'), (2, 'Cao')]),
    ('dust', 'Bụi trong nắng', [(False, 'Tắt'), (True, 'Bật')]),
    ('splash', 'Giọt nước bắn', [(0, 'Tắt'), (1, 'Ít'), (2, 'Nhiều')]),
    ('wet', 'Sàn ướt, vết chân', [(False, 'Tắt'), (True, 'Bật')]),
    ('gun_env', 'Súng phản chiếu căn phòng', [(False, 'Tắt'), (True, 'Bật')]),
    ('under', 'Dưới nước', [(0, 'Đơn giản'), (1, 'Đầy đủ')]),
    ('wetlens', 'Ống kính ướt khi trồi lên', [(False, 'Tắt'), (True, 'Bật')]),
    ('smoke', 'Khói súng', [(False, 'Đơn giản'), (True, 'Đầy đủ')]),
    ('show_fps', 'Hiện FPS', [(False, 'Tắt'), (True, 'Bật')]),
)


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
                         under=g.under, wetlens=g.wetlens, scale=RENDER_SCALES.index(g.render_scale), smoke=not g.smoke_simple)
    if keep is not None:
        s.aa, s.show_fps = keep.aa, keep.show_fps
    return s


def resolve(s: GraphicsSettings) -> GraphicsLevel:
    """The GraphicsLevel the effects read, built from the panel's settings."""
    p = preset_of(s)
    cols, rows = SIM_SIZES[s.sim]
    return GraphicsLevel(GRAPHICS_LEVELS[p].name if p is not None else 'Tuỳ chỉnh', cols, rows, s.refraction, s.caustics, s.glint,
                         SHAFT_SAMPLES[s.shafts], SPLASH_SHARE[s.splash], s.wet, s.gun_env, s.dust, s.under, s.wetlens, RENDER_SCALES[s.scale], not s.smoke)


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
    """G13: the water quad can use its POOL_LITE build (every feature it reads is off, as on Low): no sim, clear water, caustics, sparkle, shafts; simple underwater."""
    return g.sim_cols == 0 and not g.refraction and g.caustics == 0 and not g.glint and g.shaft_steps == 0 and g.under == 0


def lite_basin(g: GraphicsLevel) -> bool:
    """G13: the basin mesh can use its POOL_LITE build: no caustics, simple underwater."""
    return g.caustics == 0 and g.under == 0


def lite_room(g: GraphicsLevel) -> bool:
    """G13: the room mesh can use its POOL_LITE build: no wet deck, no shafts."""
    return not g.wet and g.shaft_steps == 0


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
        return choices[p][1] if p is not None else 'Tuỳ chỉnh'
    v = getattr(s, field)
    return next((t for val, t in choices if val == v), str(v))


def to_json(s: GraphicsSettings) -> str:
    return json.dumps({'version': 1, 'graphics': asdict(s)}, ensure_ascii=False, indent=2)


def from_json(text: str) -> GraphicsSettings:
    """Unknown or out-of-range values fall back to the default of that field (an old / hand-edited file never breaks the start)."""
    data = json.loads(text).get('graphics', {})
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
