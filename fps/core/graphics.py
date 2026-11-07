"""Graphics levels switched live with F2 (pure Python; tests/test_graphics.py). The levels themselves are data: weapon_data.GRAPHICS_LEVELS."""
from fps.weapon_data import GRAPHICS_LEVELS, GraphicsLevel


def clamp_level(i: int) -> int:
    return min(max(int(i), 0), len(GRAPHICS_LEVELS) - 1)


def next_level(i: int) -> int:
    """F2: Thấp -> Vừa -> Cao -> Thấp."""
    return (clamp_level(i) + 1) % len(GRAPHICS_LEVELS)


def level(i: int) -> GraphicsLevel:
    return GRAPHICS_LEVELS[clamp_level(i)]


def water_flags(g: GraphicsLevel) -> tuple:
    """vec4 for water.frag `water_quality`: (wave simulation on, see the bottom, caustics, sun sparkle), each 0 or 1."""
    return (1.0 if g.sim_cols > 0 else 0.0, 1.0 if g.refraction else 0.0, 1.0 if g.caustics else 0.0, 1.0 if g.glint else 0.0)
