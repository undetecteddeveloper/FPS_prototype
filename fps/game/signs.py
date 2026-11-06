"""Texture for the distance signs: text drawn with PIL (Segoe UI Semilight ships with Windows: thin, sharp, full diacritics), all signs merged into
ONE atlas so the whole row of signs is drawn with one mesh / one draw call. The geometry layout is in fps/core/signs.py; the mesh is built in shooting_range.build_range.

Each cell is one sign: dark blue-black background, thin border, large number + small unit "m", a thin orange bar on the top edge. Cells are separated by a dark strip (gutter)
so that distant mipmaps do not blend the text of the neighbouring sign in. A flat background patch at the end of the atlas is reserved for the back / edge of a sign.
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from panda3d.core import SamplerState
from ursina import Texture

FONT_FILE = 'segoeuisl.ttf'                 # Segoe UI Semilight, same font as the HUD (hud.setup_fonts)
CELL_W, CELL_H = 1024, 344                  # 3 : 1 ratio, as SignLayout.aspect
GUTTER = 32
PATCH_H = 16                                # flat background patch at the end of the atlas

BG = (14, 19, 26)
FRAME = (120, 132, 146)
ACCENT = (226, 142, 36)
TEXT = (246, 242, 232)
UNIT = (186, 194, 204)
BACK = (36, 40, 46)                         # back face, edge


def _font(size: int):
    path = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / FONT_FILE
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:                         # no such font on this machine: use PIL's default font (uglier, but the game still runs)
        return ImageFont.load_default(size)


def draw_cell(distance: int, bold: int = 0) -> Image.Image:
    """One sign. `bold` > 0: strokes thickened by that many pixels (distant signs; thin strokes would vanish with distance)."""
    img = Image.new('RGB', (CELL_W, CELL_H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([14, 14, CELL_W - 15, CELL_H - 15], outline=FRAME, width=3)
    d.rectangle([14, 14, CELL_W - 15, 14 + 9], fill=ACCENT)
    number, unit = str(distance), 'm'
    big = _font(int(CELL_H * 0.80))
    small = _font(int(CELL_H * 0.40))
    nb = d.textbbox((0, 0), number, font=big, stroke_width=bold)
    ub = d.textbbox((0, 0), unit, font=small, stroke_width=bold // 2)
    gap = int(CELL_H * 0.06)
    total = (nb[2] - nb[0]) + gap + (ub[2] - ub[0])
    x0 = (CELL_W - total) // 2
    y_mid = CELL_H // 2 + 8                                       # nudged down slightly to balance the orange bar at the top
    ny = y_mid - (nb[1] + nb[3]) // 2
    d.text((x0 - nb[0], ny), number, font=big, fill=TEXT, stroke_width=bold, stroke_fill=TEXT)
    ux = x0 + (nb[2] - nb[0]) + gap
    base = ny + nb[3]                                              # the unit (m) sits on the same baseline as the number
    uy = base - ub[3]
    d.text((ux - ub[0], uy), unit, font=small, fill=UNIT, stroke_width=bold // 2, stroke_fill=UNIT)
    return img


def build_atlas(distances, bold_from: float = 100) -> tuple:
    """(Texture, {distance: (u0, u1, v0, v1)}, (u, v) of the flat patch). v points UP (v0 is the bottom edge of the cell)."""
    n = len(distances)
    height = n * (CELL_H + GUTTER) + PATCH_H
    img = Image.new('RGB', (CELL_W, height), BG)
    rects = {}
    for i, dist in enumerate(distances):
        y = i * (CELL_H + GUTTER) + GUTTER // 2
        img.paste(draw_cell(int(dist), bold=4 if dist >= bold_from else 0), (0, y))
        rects[dist] = (0.0, 1.0, 1.0 - (y + CELL_H) / height, 1.0 - y / height)
    ImageDraw.Draw(img).rectangle([0, height - PATCH_H, CELL_W, height], fill=BACK)
    patch = (0.5, 1.0 - (height - PATCH_H / 2) / height)
    tex = Texture(img, filtering='mipmap')
    tex._texture.set_anisotropic_degree(8)
    tex._texture.set_wrap_u(SamplerState.WM_clamp)
    tex._texture.set_wrap_v(SamplerState.WM_clamp)
    tex.pil_image = img                                            # for the selftest to read back (check the text / measure contrast)
    return tex, rects, patch
