"""Cube map of the room as ONE 3 x 2 atlas image (pure; tests/test_cubemap.py).

Panda's cube textures use their own coordinate and orientation conventions, which differ from Ursina's left-handed y-up world. To stay in control the six faces are plain 2D renders
packed into one atlas and the water shader picks the face itself from the tables here (sent to it as uniforms), so the capture and the lookup can never disagree.
Face f sits in column f % 3, row f // 3 of the atlas (row 0 = the BOTTOM row in OpenGL texture coordinates). Each face is rendered with a field of view a little over 90 degrees
(`FACE_FOV`), so a lookup bilinear-filters inside its own face and never bleeds into the neighbour.
"""
import math

FACE_FOV = 92.0                      # degrees, the same horizontal and vertical field of view for every face
COLS, ROWS = 3, 2
TAN_HALF = math.tan(math.radians(FACE_FOV / 2.0))

# forward, up of each face camera (+x, -x, +y, -y, +z, -z). right = cross(up, forward) in Ursina's left-handed y-up world (+z forward, +x right, +y up).
FACE_AXES = (((1, 0, 0), (0, 1, 0)), ((-1, 0, 0), (0, 1, 0)), ((0, 1, 0), (0, 0, 1)), ((0, -1, 0), (0, 0, -1)), ((0, 0, 1), (0, 1, 0)), ((0, 0, -1), (0, 1, 0)))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def basis(face: int) -> tuple:
    """(right, up, forward) unit vectors of the camera that renders `face`."""
    forward, up = FACE_AXES[face]
    return _cross(up, forward), up, forward


def pick_face(d) -> int:
    """The face whose forward axis is closest to the direction `d` (the largest dot product)."""
    return max(range(6), key=lambda f: _dot(FACE_AXES[f][0], d))


def face_uv(d) -> tuple:
    """(face, u, v): where the direction `d` lands in that face, both in 0..1 (v up)."""
    f = pick_face(d)
    right, up, forward = basis(f)
    a = _dot(d, forward)
    x, y = _dot(d, right) / a, _dot(d, up) / a
    return f, 0.5 + 0.5 * x / TAN_HALF, 0.5 + 0.5 * y / TAN_HALF


def atlas_uv(d) -> tuple:
    """Texture coordinates (U, V) in the atlas of the direction `d` (OpenGL convention: V = 1 is the top of the PNG)."""
    f, u, v = face_uv(d)
    return ((f % COLS) + u) / COLS, ((f // COLS) + v) / ROWS


def direction_of(face: int, u: float, v: float) -> tuple:
    """Inverse of `face_uv`: the unit direction that lands at (u, v) of `face`."""
    right, up, forward = basis(face)
    x, y = (u - 0.5) * 2.0 * TAN_HALF, (v - 0.5) * 2.0 * TAN_HALF
    d = tuple(forward[i] + right[i] * x + up[i] * y for i in range(3))
    n = math.sqrt(_dot(d, d))
    return d[0] / n, d[1] / n, d[2] / n


def region(face: int) -> tuple:
    """(left, right, bottom, top) of the face's display region, as fractions of the atlas buffer."""
    c, r = face % COLS, face // COLS
    return c / COLS, (c + 1) / COLS, r / ROWS, (r + 1) / ROWS


def box_project(p, r, lo, hi, probe) -> tuple:
    """Parallax-corrected lookup direction: shoot the reflected ray `r` from the surface point `p` to the inside of the room box (lo, hi), then look from the probe to that hit.
    A fragment must be inside the box. Same math as water.frag."""
    t = math.inf
    for i in range(3):
        if abs(r[i]) < 1e-9:
            continue
        t = min(t, ((hi[i] if r[i] > 0 else lo[i]) - p[i]) / r[i])
    hit = tuple(p[i] + r[i] * t for i in range(3))
    return tuple(hit[i] - probe[i] for i in range(3))
