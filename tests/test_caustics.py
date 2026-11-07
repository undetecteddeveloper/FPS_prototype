"""Sun caustics, light-mesh version (G11, core/caustics.py; GPU: game/caustics.py + assets/shaders/caustics.*): flat water lands where the reference lands, light is conserved,
the default ripples fold the light into sharp lines at the pool's depths, the texture domain catches every landed point, and the shaders agree with the Python sizes."""
import json
import math
import re
from pathlib import Path

from fps.core import caustics
from fps.core.graphics import CAUSTIC_SIZES, OPTIONS, GraphicsSettings, from_json
from fps.weapon_data import LookData, MapData, WaterData

SHADERS = Path(__file__).resolve().parents[1] / 'assets' / 'shaders'
P = WaterData()
SUN = tuple(c / math.sqrt(sum(v * v for v in LookData().sun_dir)) for c in LookData().sun_dir)
TABLE = caustics.wave_table(P.wave_size, P.wave_height, P.wave_speed)
WY = MapData().water_y


def flat_bottom(depth: float) -> tuple:
    return (-100.0, 100.0, WY - depth, WY - depth)


def test_table_rms_height_and_band():
    rms = math.sqrt(sum(w[3] ** 2 for w in TABLE) / 2.0)
    assert math.isclose(rms, P.wave_height, rel_tol=1e-9)
    lams = [2 * math.pi / w[2] for w in TABLE]
    assert math.isclose(max(lams), P.wave_size * caustics.BAND[0], rel_tol=1e-9) and math.isclose(min(lams), P.wave_size * caustics.BAND[1], rel_tol=1e-9)
    assert all(math.isclose(w[0] ** 2 + w[1] ** 2, 1.0) for w in TABLE)
    assert caustics.wave_table(P.wave_size, 0.0, 1.0)[0][3] == 0.0


def test_slope_is_the_derivative_of_height():
    x, z, t, e = 1.37, -2.11, 3.3, 1e-5
    h, gx, gz = caustics.surface(x, z, t, TABLE)
    assert math.isclose(gx, (caustics.surface(x + e, z, t, TABLE)[0] - caustics.surface(x - e, z, t, TABLE)[0]) / (2 * e), rel_tol=1e-4, abs_tol=1e-7)
    assert math.isclose(gz, (caustics.surface(x, z + e, t, TABLE)[0] - caustics.surface(x, z - e, t, TABLE)[0]) / (2 * e), rel_tol=1e-4, abs_tol=1e-7)


def test_flat_water_lands_on_the_reference():
    ramp = (MapData().slope_z[0], MapData().slope_z[1], MapData().pool_floor, MapData().pool_deep)
    for x, z in ((0.0, -10.0), (3.0, 0.5), (-4.0, 9.0)):
        a = caustics.land(x, z, 0.0, 0.0, 0.0, SUN, WY, ramp)
        b = caustics.land_flat(x, z, SUN, WY, ramp)
        assert math.isclose(a[0], b[0], abs_tol=1e-12) and math.isclose(a[1], b[1], abs_tol=1e-12)


def test_drop_meets_the_sloping_bottom():
    ramp = (MapData().slope_z[0], MapData().slope_z[1], MapData().pool_floor, MapData().pool_deep)
    r = caustics.flat_ray(SUN)
    for z in (-6.0, 0.0, 5.5, 9.0):
        lx, lz = caustics.drop((0.0, WY, z), r, ramp)
        s = (lx - 0.0) / r[0]
        y = WY + s * r[1]
        assert abs(y - caustics.bottom_y(lz, ramp)) < 1e-3                   # 3 fixed-point steps are enough on this slope


def test_low_sun_enters_steeply_sideways():
    r = caustics.flat_ray(SUN)
    angle = math.degrees(math.acos(-r[1]))
    assert 45.0 < angle < 50.0                                              # the 7 degree sun, refracted: ~48 degrees from vertical
    assert r[0] < 0.0                                                        # it travels west (away from the east windows)


def test_light_is_conserved():
    g = caustics.brightness_grid(TABLE, 1.7, SUN, WY, flat_bottom(1.0), 0.0, 0.0, 2.0, 240, 8)   # 15 photons per bin side: no aliasing on flat water
    cells = [c for row in g for c in row]
    assert abs(sum(cells) / len(cells) - 1.0) < 0.03


def _min_det(depth: float, n: int = 40, size: float = 1.2, t: float = 0.8) -> float:
    ramp = flat_bottom(depth)
    step, e = size / n, 1e-4

    def at(x, z):
        h, gx, gz = caustics.surface(x, z, t, TABLE)
        return caustics.land(x, z, h, gx, gz, SUN, WY, ramp)
    worst = 1e9
    for i in range(n):
        for j in range(n):
            x, z = i * step, j * step
            ax, az = at(x + e, z)
            bx, bz = at(x - e, z)
            cx, cz = at(x, z + e)
            dx, dz = at(x, z - e)
            det = ((ax - bx) * (cz - dz) - (az - bz) * (cx - dx)) / (4 * e * e)
            worst = min(worst, det)
    return worst


def test_default_ripples_fold_the_light_at_pool_depth():
    """Folds (det < 0) = the sharp bright lines of a real pool: there at 1 m, none in a few cm of water (where the light is only gently modulated)."""
    assert _min_det(1.0) < 0.0
    assert _min_det(0.05) > 0.5


def test_domain_catches_every_landed_point():
    d = MapData()
    rect = (-d.pool_x / 2, d.pool_x / 2, -d.pool_z / 2, d.pool_z / 2)
    ramp = (d.slope_z[0], d.slope_z[1], d.pool_floor, d.pool_deep)
    dom = caustics.domain(rect, SUN, d.water_y - d.pool_deep + 0.1)
    for x in (rect[0], 0.0, rect[1]):
        for z in (rect[2], 0.0, rect[3]):
            lx, lz = caustics.land_flat(x, z, SUN, d.water_y, ramp)
            assert dom[0] < lx < dom[1] and dom[2] < lz < dom[3]
    w, h = caustics.texture_size(dom, 2048)
    assert h == 2048 and w % 16 == 0
    assert abs((dom[1] - dom[0]) / w - (dom[3] - dom[2]) / h) < 0.002        # texels nearly square


def test_shaders_agree_with_python():
    waves = (SHADERS / 'pool_waves.glsl').read_text(encoding='utf-8')
    assert f'wave_a[{caustics.N_WAVES}]' in waves and f'wave_b[{caustics.N_WAVES}]' in waves and f'i < {caustics.N_WAVES}' in waves
    vert = (SHADERS / 'caustics.vert').read_text(encoding='utf-8')
    assert 'ETA = 1.0 / 1.333' in vert and math.isclose(caustics.ETA, 1.0 / 1.333)
    assert re.search(r'for \(int i = 0; i < 3; i\+\+\) s = ', vert)            # caustics.drop iterations=3
    assert 'pool_waves.glsl' in (SHADERS / 'water.frag').read_text(encoding='utf-8')


def test_graphics_row_has_three_levels():
    row = next(c for f, _, c in OPTIONS if f == 'caustics')
    assert [v for v, _ in row] == [0, 1, 2] and len(CAUSTIC_SIZES) == 3 and CAUSTIC_SIZES[0][0] == 0
    assert all(a[0] < b[0] and a[2] < b[2] for a, b in zip(CAUSTIC_SIZES[1:], CAUSTIC_SIZES[2:]))
    old = from_json(json.dumps({'version': 1, 'graphics': {'caustics': True}}))      # a file saved before G11 (bool) falls back to the default
    assert old.caustics == GraphicsSettings().caustics
