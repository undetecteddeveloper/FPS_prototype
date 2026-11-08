import dataclasses
import math

import numpy as np
import pytest

from fps.core.lightbake import (Occluders, any_hit, bake, cast, decode, direct_light, encode, sun_directions, sun_visibility, texel_positions, unit)
from fps.core.poolmap import build_map, face_texels
from fps.weapon_data import LookData, MapData

D = MapData()
LOOK = LookData()


@pytest.fixture(scope='module')
def pm():
    return build_map(D)


@pytest.fixture(scope='module')
def occ(pm):
    return Occluders(pm)


def test_cast_returns_nearest_box_axis_and_sign(pm):
    from fps.core.lightbake import Occluders as O

    class Tiny:
        boxes = [type('B', (), dict(visible=True, lo=(0, 0, 0), hi=(1, 1, 1), albedo=(1, 0, 0)))(),
                 type('B', (), dict(visible=True, lo=(3, 0, 0), hi=(4, 1, 1), albedo=(0, 1, 0)))()]
    o = O(Tiny)
    origins = np.array([[-1.0, 0.5, 0.5], [5.0, 0.5, 0.5], [0.5, 5.0, 0.5], [0.5, 0.5, 0.5]])
    dirs = np.array([[1.0, 0, 0], [-1.0, 0, 0], [0, -1.0, 0], [1.0, 0, 0]])
    t, idx, axis, sign = cast(o, origins, dirs)
    assert t[:3] == pytest.approx([1.0, 1.0, 4.0])
    assert list(idx[:3]) == [0, 1, 0] and list(axis[:3]) == [0, 0, 1]
    assert list(sign[:3]) == [-1, 1, 1]                      # entering the west face looks west, the east face east, the top face up
    assert idx[3] == 1                                       # the origin is inside box 0 (ignored): the next box along the ray is hit


def test_ray_parallel_to_an_axis_does_not_divide_by_zero(occ):
    p = np.array([[0.0, 1.0, 0.0]])
    t, idx, axis, sign = cast(occ, p, np.array([0.0, 1.0, 0.0]))
    assert np.isfinite(t[0]) and axis[0] == 1                # straight up hits the ceiling


def test_sun_disc_samples_are_unit_vectors_spread_around_the_centre():
    dirs = sun_directions((0.9, 0.2, -0.3), 8, 0.012)
    assert dirs.shape == (8, 3) and np.allclose(np.linalg.norm(dirs, axis=1), 1.0)
    centre = unit((0.9, 0.2, -0.3))
    angles = np.arccos(np.clip(dirs @ centre, -1, 1))
    assert angles.max() <= 0.012 * 1.001 and angles.min() > 0
    assert np.allclose(sun_directions((0.9, 0.2, -0.3), 1, 0.012)[0], centre)


def test_sun_patches_on_the_decks_match_the_windows_projected_along_the_sun():
    """Goal 3: with no column or stairs in the way, a floor point is lit exactly when its sun ray goes through a window hole (checked with a point sun, no soft edge)."""
    d = dataclasses.replace(D, column_z=(), stair_count=0)
    pm0 = build_map(d)
    pm0.boxes[:] = [b for b in pm0.boxes if not b.caster]                  # (the G14 ladder shadow casters are not windows' shade either)
    occ = Occluders(pm0)
    s = unit(LOOK.sun_dir)
    xs, zs = np.meshgrid(np.concatenate([np.arange(6.05, 9.95, 0.1), np.arange(-9.95, -6.05, 0.1)]), np.arange(-14.0, 14.0, 0.1))
    pts = np.stack([xs.ravel(), np.full(xs.size, 0.001), zs.ravel()], axis=1)
    vis = sun_visibility(occ, pts, LOOK.sun_dir, 1, 0.0)
    expected = np.array([any(_hole_lit(d, p, s, k) for k in range(len(d.window_z))) for p in pts])
    wrong = int(((vis > 0.5) != expected).sum())
    assert 50 < expected.sum() < len(pts) - 50                           # some floor lit, some in shade: the test is not vacuous
    assert wrong <= 3                                                    # points exactly on a patch edge may fall either way


def _hole_lit(d, p, s, k):
    hx, w = d.room_x / 2, d.wall
    zc = d.window_z[k]
    z0, z1 = zc - d.window_width / 2, zc + d.window_width / 2
    for plane in (hx, hx + w):
        t = (plane - p[0]) / s[0]
        y, z = p[1] + t * s[1], p[2] + t * s[2]
        if not (d.window_sill <= y <= d.window_top and z0 <= z <= z1):
            return False
    return True


def test_direct_light_is_sun_times_cosine_where_nothing_blocks(occ):
    s = unit(LOOK.sun_dir)
    zc = D.window_z[2]
    # a point above the pool (x = -2) whose sun ray goes through the middle of a window (it reaches the wall ~1.6 m up, between the 0.45 m sill and the 3.75 m top)
    x0 = -2.0
    t = (D.room_x / 2 - x0) / s[0]
    p = np.array([[x0, 0.001, zc - t * s[2]]])
    n = np.array([0.0, 1.0, 0.0])
    e = direct_light(occ, p, n, LOOK, dataclasses.replace(D, sun_samples=1))
    assert e[0] == pytest.approx(np.asarray(LOOK.sun_color) * float(n @ s), rel=1e-6)
    assert direct_light(occ, p, np.array([0.0, -1.0, 0.0]), LOOK, D)[0].sum() == 0.0      # facing away from the sun


def test_floor_in_the_shade_gets_no_direct_sun(occ):
    p = np.array([[-8.0, 0.001, -13.0]])                     # west bank, far from every window beam
    assert sun_visibility(occ, p, LOOK.sun_dir, 4, 0.012)[0] == 0.0


def test_texel_positions_cover_the_piece_and_sit_in_front_of_it(pm):
    f = pm.exposed_faces()[0]
    nu, nv = face_texels(f, D.texel)
    pts = texel_positions(f, nu, nv)
    assert pts.shape == (nv, nu, 3)
    assert np.all(np.abs(pts[..., f.axis] - (f.plane + f.sign * 1e-3)) < 1e-9)


def test_encode_decode_round_trip_keeps_dark_values():
    e = np.array([[[0.02, 0.5, 3.9]]])
    back = decode(encode(e, 4.0), 4.0)
    assert back[0, 0, 2] == pytest.approx(3.9, rel=0.02)
    assert back[0, 0, 0] == pytest.approx(0.02, abs=0.004)             # gamma 2 keeps a useful resolution in the shade
    assert encode(np.array([[[9.0, 9.0, 9.0]]]), 4.0).max() == 255      # clipped, not wrapped


def test_small_bake_gives_sun_patches_brighter_than_shade_and_a_warm_bounce():
    d = dataclasses.replace(D, texel=0.5, coarse=1.5, sun_samples=2, bounce_rays=24)
    pm = build_map(d)
    res = bake(pm, LOOK, probes=[((0.0, 0.5, 13.5), (0.0, 1.0, 0.0))])
    assert res.rgb.shape[2] == 3 and res.rgb.dtype == np.uint8
    e = decode(res.rgb, res.e_max)
    occ = Occluders(pm)
    lit, shade = [], []
    for f, p in zip(res.faces, res.atlas.faces):
        if pm.boxes[f.box].name == 'wall_w' and f.axis == 0 and f.sign == 1:        # the west wall faces the windows: beams reach it low down
            nu, nv = face_texels(f, d.texel)
            pts = texel_positions(f, nu, nv).reshape(-1, 3)
            sunny = direct_light(occ, pts, np.array(f.normal), LOOK, d).sum(axis=1) > 0
            block = e[p.y:p.y + p.h, p.x:p.x + p.w].reshape(-1, 3)
            lit.extend(block[sunny])
            shade.extend(block[~sunny])
    assert len(lit) > 5 and len(shade) > 5
    lit_mean, shade_mean = np.mean(lit, axis=0), np.mean(shade, axis=0)
    assert lit_mean[0] > 3 * shade_mean[0]                              # a sunlit patch is far brighter than the wall next to it
    assert lit_mean[0] > lit_mean[2]                                    # golden: more red than blue in the patch
    assert shade_mean.min() > 0.005                                     # the shade is not black: sky + bounce reach it
    pp = res.atlas.probes[0]
    assert e[pp.y:pp.y + 2, pp.x:pp.x + 2].sum() > 0


def test_every_texel_of_every_piece_is_written_not_left_black():
    d = dataclasses.replace(D, texel=0.5, coarse=1.5, sun_samples=1, bounce_rays=16)
    pm = build_map(d)
    res = bake(pm, LOOK)
    e = decode(res.rgb, res.e_max)
    for f, p in zip(res.faces, res.atlas.faces):
        block = e[p.y:p.y + p.h, p.x:p.x + p.w]
        assert block.sum(axis=2).min() > 0.0, (pm.boxes[f.box].name, f.axis, f.sign)


def test_baked_ambient_grid_is_dark_in_the_dark_corner_and_lighter_by_the_windows():
    """The gun's local ambient light: no direct sun in it, brighter where the sky and the lit walls reach, never zero, and every probe has a value (none left inside a column)."""
    from fps.core.poolmap import AmbientGrid
    d = dataclasses.replace(D, texel=0.5, coarse=1.5, sun_samples=1, bounce_rays=48)
    pm = build_map(d)
    res = bake(pm, LOOK)
    grid = AmbientGrid(res.ambient)
    assert (grid.nx, grid.nz) == (20, 30)
    import numpy as np
    assert np.isfinite(np.array(res.ambient['up'])).all() and np.isfinite(np.array(res.ambient['down'])).all()
    assert np.array(res.ambient['up']).min() > 0.0
    corner_up, _ = grid.sample(-9.5, -14.5)                            # south-west corner, far from every window
    window_up, _ = grid.sample(8.5, 0.0)                               # under the east windows
    assert sum(window_up) > 1.5 * sum(corner_up)



def test_the_ladder_casts_a_sun_shadow_on_the_north_deck_and_nothing_else_changes():
    """G14: the shadow casters stand for the rail tubes above the water: points near them lose sun; far points are exactly as without them."""
    pm = build_map(D)
    pm_no = build_map(D)
    pm_no.boxes[:] = [b for b in pm_no.boxes if not b.caster]
    assert any(b.caster for b in pm.boxes)
    xs, zs = np.meshgrid(np.arange(-4.0, 0.0, 0.1), np.arange(12.0, 15.0, 0.1))
    near = np.stack([xs.ravel(), np.full(xs.size, 0.001), zs.ravel()], axis=1)
    a = sun_visibility(Occluders(pm), near, LOOK.sun_dir, 4, D.sun_radius)
    b = sun_visibility(Occluders(pm_no), near, LOOK.sun_dir, 4, D.sun_radius)
    assert (a < b - 0.05).sum() > 20 and (a > b + 1e-9).sum() == 0          # only darker, never lighter
    far = np.stack([np.arange(4.0, 9.0, 0.1), np.full(50, 0.001), np.full(50, -2.0)], axis=1)
    assert np.allclose(sun_visibility(Occluders(pm), far, LOOK.sun_dir, 4, D.sun_radius), sun_visibility(Occluders(pm_no), far, LOOK.sun_dir, 4, D.sun_radius))
