"""Layout of the ceiling-hung distance signs (pure math, no ursina import, pytest-able).

Each distance mark has a PAIR of signs (left and right of the lane) facing the shooter (-z), hung just in front of the mark (`z_offset` closer
to the shooter), so they do not cover the ceiling beam at that exact mark. Farther signs are larger (text stays readable), but the ceiling limits them, so the lettering
at 200 m is only ~1.5 m tall. The bottom edge of each sign always stays above the top of the largest target, so signs do not hide targets and moving targets pass under them.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SignLayout:
    bottom: float = 3.0           # m: bottom edge of every sign (largest target, 200 m, 2.86 m tall)
    ceiling: float = 5.5          # m: room ceiling; a sign whose top nearly reaches it is fixed straight to the ceiling, no hanging rod needed
    top_margin: float = 0.05      # m: gap between the sign top and the ceiling when the sign is at its tallest
    height_base: float = 0.70     # m: sign height at 0 m
    height_per_m: float = 0.0070  # m/m: signs grow taller with distance
    aspect: float = 3.0           # width / height
    thickness: float = 0.06
    z_offset: float = 0.40        # m: the sign sits this far in front of the mark (toward the shooter)
    rod_half: float = 0.015       # m: half cross-section of the hanging rod
    # x of the sign CENTRE (absolute value; one sign at +x and one at -x). Seen from the firing line, the 100/150/200 m signs crowd within a few degrees around the lane axis,
    # so x is chosen (searched at random) so that a near sign hides the far signs as little as possible: at most ~8% of the area (test_signs.test_signs_do_not_hide_each_other)
    x: tuple = ((10, 4.3), (25, 4.8), (50, 6.0), (100, 9.0), (150, 8.3), (200, 5.1))

    @property
    def max_height(self) -> float:
        return self.ceiling - self.top_margin - self.bottom


def sign_height(layout: SignLayout, distance: float) -> float:
    return min(layout.height_base + layout.height_per_m * distance, layout.max_height)


def sign_center_x(layout: SignLayout, distance: float) -> float:
    table = dict(layout.x)
    if distance in table:
        return table[distance]
    return table[min(table, key=lambda d: abs(d - distance))]


def sign_rect(layout: SignLayout, distance: float, side: int = 1) -> dict:
    """Box of the sign at distance `distance`, on `side` (+1 right, -1 left): world coordinates.
    Returns a dict: cx, cy, cz, w, h, lo (x, y, z min), hi."""
    h = sign_height(layout, distance)
    w = h * layout.aspect
    cx = side * sign_center_x(layout, distance)
    cy = layout.bottom + h / 2
    cz = distance - layout.z_offset
    t = layout.thickness / 2
    return {'cx': cx, 'cy': cy, 'cz': cz, 'w': w, 'h': h,
            'lo': (cx - w / 2, cy - h / 2, cz - t), 'hi': (cx + w / 2, cy + h / 2, cz + t)}


def rod_xs(rect: dict) -> tuple:
    """x of the two hanging rods of a sign: near the two ends of the sign."""
    return rect['cx'] - rect['w'] * 0.4, rect['cx'] + rect['w'] * 0.4


def angular_rect(rect: dict, eye=(0.0, 1.62, 0.0)) -> tuple:
    """Projection of the sign's front-face corners onto the view screen from `eye` along +z: (x0, x1, y0, y1) as tan of the horizontal / vertical angles."""
    z = rect['cz'] - eye[2]                                              # sign thickness is ignored
    return ((rect['lo'][0] - eye[0]) / z, (rect['hi'][0] - eye[0]) / z, (rect['lo'][1] - eye[1]) / z, (rect['hi'][1] - eye[1]) / z)


def overlap_fraction(near: dict, far: dict, eye=(0.0, 1.62, 0.0)) -> float:
    """Fraction of the area (as seen from `eye`) of the FAR sign that is hidden by the NEAR sign."""
    a, b = angular_rect(near, eye), angular_rect(far, eye)
    ox = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    oy = max(0.0, min(a[3], b[3]) - max(a[2], b[2]))
    area = (b[1] - b[0]) * (b[3] - b[2])
    return ox * oy / area if area > 0 else 0.0
