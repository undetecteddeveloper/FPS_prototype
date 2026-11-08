"""Loads the procedural surface textures (assets/textures/*.png, built by tools/build/make_surface_textures.py) for the shaders, with safe fallbacks.

A missing or unreadable PNG never stops the game (G16, C3): `read_texture` returns None and the caller binds a placeholder (`flat_relief`, `white`): the tiles then draw as plain
colour with no joints, the bullet holes as simple round marks, and a line is printed once.
"""
from pathlib import Path

from panda3d.core import Filename, SamplerState, Texture as PandaTexture

ASSET_DIR = Path(__file__).resolve().parent.parent.parent / 'assets' / 'textures'


def read_texture(name: str, file_name: str, repeat: bool = False, mipmaps: bool = True, anisotropy: int = 4):
    """The PNG `assets/textures/<file_name>` as a Panda texture (mipmapped, anisotropic), or None when it is missing / unreadable."""
    path = ASSET_DIR / file_name
    tex = PandaTexture(name)
    try:
        if not path.exists() or not tex.read(Filename.from_os_specific(str(path))):
            return None
    except Exception:
        return None
    mode = SamplerState.WM_repeat if repeat else SamplerState.WM_clamp
    tex.set_wrap_u(mode)
    tex.set_wrap_v(mode)
    tex.set_magfilter(SamplerState.FT_linear)
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear if mipmaps else SamplerState.FT_linear)
    tex.set_anisotropic_degree(anisotropy)
    return tex


def _solid(name: str, rgb: tuple, repeat: bool = False) -> PandaTexture:
    tex = PandaTexture(name)
    tex.setup_2d_texture(1, 1, PandaTexture.T_unsigned_byte, PandaTexture.F_rgb)
    tex.set_ram_image_as(bytes(rgb), 'RGB')
    mode = SamplerState.WM_repeat if repeat else SamplerState.WM_clamp
    tex.set_wrap_u(mode)
    tex.set_wrap_v(mode)
    return tex


def flat_relief() -> PandaTexture:
    """Height 1 (the surface) and a flat normal: no relief."""
    return _solid('relief_flat', (255, 128, 128), repeat=True)


def white() -> PandaTexture:
    """Colour multiplier 1 everywhere (the tile has no joints)."""
    return _solid('white', (204, 204, 204), repeat=True)      # 204 / 255 * TILE_GAIN 1.25 = 1.0: the tile shaders multiply by the gain
