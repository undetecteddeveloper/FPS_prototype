"""Texture của biển khoảng cách: chữ vẽ bằng PIL (Segoe UI Semilight có sẵn trong Windows: mảnh, sắc, đủ dấu), gộp mọi biển vào
MỘT atlas để cả dãy biển vẽ bằng một mesh / một lần vẽ. Bố cục hình học ở fps/core/signs.py; mesh dựng trong shooting_range.build_range.

Mỗi ô (cell) là một biển: nền xanh đen, viền mảnh, số lớn + chữ "m" nhỏ, một vạch cam mảnh ở mép trên. Các ô cách nhau một dải nền tối (gutter)
để mipmap ở xa không trộn chữ của biển bên cạnh vào. Một mảnh nền phẳng ở cuối atlas dành cho mặt sau / cạnh biển.
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from panda3d.core import SamplerState
from ursina import Texture

FONT_FILE = 'segoeuisl.ttf'                 # Segoe UI Semilight, cùng font với HUD (hud.setup_fonts)
CELL_W, CELL_H = 1024, 344                  # tỉ lệ 3 : 1 như SignLayout.aspect
GUTTER = 32
PATCH_H = 16                                # mảnh nền phẳng cuối atlas

BG = (14, 19, 26)
FRAME = (120, 132, 146)
ACCENT = (226, 142, 36)
TEXT = (246, 242, 232)
UNIT = (186, 194, 204)
BACK = (36, 40, 46)                         # mặt sau, cạnh


def _font(size: int):
    path = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / FONT_FILE
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:                         # máy không có font: dùng font mặc định của PIL (xấu hơn nhưng game vẫn chạy)
        return ImageFont.load_default(size)


def draw_cell(distance: int, bold: int = 0) -> Image.Image:
    """Một biển. `bold` > 0: nét dày thêm bấy nhiêu điểm ảnh (biển xa, nét mảnh quá thì mất ở khoảng cách)."""
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
    y_mid = CELL_H // 2 + 8                                       # nhích xuống một chút để bù vạch cam ở trên
    ny = y_mid - (nb[1] + nb[3]) // 2
    d.text((x0 - nb[0], ny), number, font=big, fill=TEXT, stroke_width=bold, stroke_fill=TEXT)
    ux = x0 + (nb[2] - nb[0]) + gap
    base = ny + nb[3]                                              # chữ "m" cùng đường chân chữ với số
    uy = base - ub[3]
    d.text((ux - ub[0], uy), unit, font=small, fill=UNIT, stroke_width=bold // 2, stroke_fill=UNIT)
    return img


def build_atlas(distances, bold_from: float = 100) -> tuple:
    """(Texture, {khoảng cách: (u0, u1, v0, v1)}, (u, v) của mảnh nền phẳng). v hướng LÊN (v0 là mép dưới ô)."""
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
    tex.pil_image = img                                            # cho selftest đọc lại (so chữ / đo tương phản)
    return tex, rects, patch
