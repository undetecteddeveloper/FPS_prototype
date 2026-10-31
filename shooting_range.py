"""Trường bắn: một làn thẳng dài 210 m dọc +z, người chơi đứng ở z = 0 nhìn về +z.

Bia (G2/G6) và biển chữ khoảng cách (G6) sẽ đặt thêm vào đây. Hằng số kích thước để ở đầu file.
"""
from PIL import Image, ImageDraw
from ursina import Entity, Sky, Texture, color

LANE_HALF_WIDTH = 8.0
LANE_BACK_Z = -20.0              # đầu làn, sau người chơi
LANE_END_Z = 210.0               # chân bờ chắn đạn
DISTANCE_MARKS = (10, 25, 50, 100, 150, 200)
# (x_min, x_max, z_min, z_max): người chơi đi được trong khoảng này
WALK_BOUNDS = (-LANE_HALF_WIDTH + 0.6, LANE_HALF_WIDTH - 0.6, LANE_BACK_Z + 5.0, LANE_END_Z - 12.0)

STRIPE_MAX_DISTANCE = 50
BERM_HEIGHT = 1.2                # thấp hơn tầm mắt (1,62 m) để còn thấy cỏ và chân trời
BACKSTOP_HEIGHT = 5.0
FAR = 600.0                      # mặt cỏ trải xa tới đây để chân trời không bị hở


def _grid_texture(base: int, line: int, cells: int = 8, size: int = 256) -> Texture:
    """Ô lưới mờ để mắt thấy được chuyển động và khoảng cách; mipmap để xa không bị nhấp nháy."""
    img = Image.new('RGB', (size, size), (base, base, base))
    draw = ImageDraw.Draw(img)
    step = size // cells
    for i in range(cells + 1):
        p = min(i * step, size - 1)
        draw.line([(p, 0), (p, size)], fill=(line, line, line), width=2)
        draw.line([(0, p), (size, p)], fill=(line, line, line), width=2)
    tex = Texture(img, filtering='mipmap')
    tex._texture.set_anisotropic_degree(8)
    return tex


def _ground(x0, x1, z0, z1, tint, tex, tile=4.0) -> Entity:
    w, l = x1 - x0, z1 - z0
    return Entity(model='plane', position=((x0 + x1) / 2, 0, (z0 + z1) / 2), scale=(w, 1, l), color=tint,
                  texture=tex, texture_scale=(w / tile, l / tile))


def _stripe(z: float, width: float, tint) -> Entity:
    """Vạch ngang làn. Nằm sát mặt đất nên phải dùng độ lệch độ sâu thay vì nâng lên (nâng 1 cm sẽ vẫn nhấp nháy ở 200 m)."""
    e = Entity(model='plane', position=(0, 0, z), scale=(2 * LANE_HALF_WIDTH, 1, width), color=tint)
    e.set_depth_offset(1)
    return e


def build_range() -> dict:
    lane_tex = _grid_texture(base=255, line=215)
    grass_tex = _grid_texture(base=255, line=225)
    world = {}

    lane_tint = color.rgb(0.58, 0.58, 0.6)
    grass_tint = color.rgb(0.36, 0.52, 0.3)
    world['lane'] = _ground(-LANE_HALF_WIDTH, LANE_HALF_WIDTH, LANE_BACK_Z, LANE_END_Z, lane_tint, lane_tex, tile=2.0)
    world['grass'] = [
        _ground(-FAR, -LANE_HALF_WIDTH, -100, FAR, grass_tint, grass_tex),
        _ground(LANE_HALF_WIDTH, FAR, -100, FAR, grass_tint, grass_tex),
        _ground(-LANE_HALF_WIDTH, LANE_HALF_WIDTH, LANE_END_Z, FAR, grass_tint, grass_tex),
        _ground(-LANE_HALF_WIDTH, LANE_HALF_WIDTH, -100, LANE_BACK_Z, grass_tint, grass_tex),
    ]

    # vạch bắn và vạch khoảng cách
    # Vạch ở 100 m trở đi mảnh hơn một điểm ảnh nên luôn đứt nét (MSAA trên máy này chỉ còn ~20 FPS),
    # nên chỉ vạch tới STRIPE_MAX_DISTANCE; xa hơn dùng cột cao (và biển chữ ở G6).
    world['stripes'] = [_stripe(0.0, 0.3, color.yellow)]
    for d in DISTANCE_MARKS:
        if d <= STRIPE_MAX_DISTANCE:
            world['stripes'].append(_stripe(float(d), 0.25, color.white))

    # cột đánh dấu hai bên làn: cao dần theo khoảng cách để nhìn thấy từ xa
    world['posts'] = []
    for i, d in enumerate(DISTANCE_MARKS):
        h = 1.6 + d * 0.02
        for side in (-1, 1):
            tint = color.orange if i % 2 == 0 else color.white
            world['posts'].append(Entity(model='cube', color=tint, scale=(0.3, h, 0.3),
                                         position=(side * (LANE_HALF_WIDTH + 0.5), h / 2, float(d))))

    # bờ đất hai bên và bờ chắn đạn cuối làn
    earth = color.rgb(0.42, 0.32, 0.22)
    length = LANE_END_Z - LANE_BACK_Z + 10
    mid_z = (LANE_END_Z + LANE_BACK_Z) / 2
    world['berms'] = [
        Entity(model='cube', color=earth, scale=(5, BERM_HEIGHT, length),
               position=(side * (LANE_HALF_WIDTH + 2.5), BERM_HEIGHT / 2, mid_z))
        for side in (-1, 1)
    ]
    world['berms'].append(Entity(model='cube', color=earth, scale=(2 * LANE_HALF_WIDTH + 10, BACKSTOP_HEIGHT, 6),
                                 position=(0, BACKSTOP_HEIGHT / 2, LANE_END_Z + 3)))

    world['sky'] = Sky()
    return world
