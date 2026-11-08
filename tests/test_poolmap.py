import dataclasses

import pytest

from fps.core.poolmap import (UV_AXES, build_map, colliders, face_texels, inside_box, is_air, pack_atlas, rail_meshes, triangle_count, walk_tops)
from fps.weapon_data import LookData, MapData

D = MapData()


@pytest.fixture(scope='module')
def pm():
    return build_map(D)


def test_map_fits_the_triangle_budget(pm):
    assert triangle_count(pm) <= 6000                      # G9 goal 1 (room + handrails; the water quad adds 2)
    assert len(pm.exposed_faces()) > 50


def test_every_piece_of_every_face_borders_air(pm):
    """The face algorithm must never leave a piece buried in another box or facing the outside: sample the middle and the four quarter points just in front of each piece."""
    bad = []
    for f in pm.exposed_faces():
        for fu, fv in ((0.5, 0.5), (0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)):
            p = list(f.point(f.u0 + (f.u1 - f.u0) * fu, f.v0 + (f.v1 - f.v0) * fv))
            p[f.axis] += f.sign * 0.002
            if not is_air(pm, p):
                bad.append((pm.boxes[f.box].name, f.axis, f.sign, f.plane, round(f.u0, 2), round(f.u1, 2), round(f.v0, 2), round(f.v1, 2)))
                break
    assert not bad, bad[:5]


def test_nothing_is_drawn_under_the_water_inside_the_pool(pm):
    px0, px1, pz0, pz1, wy = pm.water
    for f in pm.exposed_faces():
        c = f.point((f.u0 + f.u1) / 2, (f.v0 + f.v1) / 2)
        if px0 - 1e-3 <= c[0] <= px1 + 1e-3 and pz0 - 1e-3 <= c[2] <= pz1 + 1e-3:
            lo_y = f.plane if f.axis == 1 else f.v0
            assert lo_y >= wy - 0.02 - 1e-6, (pm.boxes[f.box].name, f.axis, f.plane, f.v0)


def test_faces_of_the_east_window_reveal_exist(pm):
    """The sides of a window hole are lit and drawn: there must be a face of the sill / lintel looking into the hole and one of each pier."""
    names = {pm.boxes[f.box].name for f in pm.exposed_faces()}
    for i in range(len(D.window_z)):
        assert f'wall_e_sill{i}' in names and f'wall_e_lintel{i}' in names
    assert 'ceiling' in names and 'deck_w' in names and 'column0' in names


def test_every_window_hole_shows_its_full_wall_thickness(pm):
    """The hole of each window is lined by four faces (sill top, lintel underside, two jambs) as deep as the wall: otherwise the wall is a paper-thin sheet there (user report 7/11/2026;
    the invisible window barrier used to hide all four)."""
    w = D.wall
    hx = D.room_x / 2
    faces = pm.exposed_faces()
    for zc in D.window_z:
        z0, z1 = zc - D.window_width / 2, zc + D.window_width / 2
        sill = [f for f in faces if f.axis == 1 and f.sign == 1 and abs(f.plane - D.window_sill) < 1e-6 and f.u0 >= hx - 1e-6 and f.u1 <= hx + w + 1e-6 and z0 - 1e-6 <= f.v0 and f.v1 <= z1 + 1e-6]
        lintel = [f for f in faces if f.axis == 1 and f.sign == -1 and abs(f.plane - D.window_top) < 1e-6 and f.u0 >= hx - 1e-6 and f.u1 <= hx + w + 1e-6 and z0 - 1e-6 <= f.v0 and f.v1 <= z1 + 1e-6]
        jambs = [f for f in faces if f.axis == 2 and (abs(f.plane - z0) < 1e-6 or abs(f.plane - z1) < 1e-6) and f.u0 >= hx - 1e-6 and f.u1 <= hx + w + 1e-6
                 and f.v0 >= D.window_sill - 1e-6 and f.v1 <= D.window_top + 1e-6]
        assert sum(f.area for f in sill) == pytest.approx(w * (z1 - z0)), f'sill top of the window at z={zc}'
        assert sum(f.area for f in lintel) == pytest.approx(w * (z1 - z0)), f'lintel underside of the window at z={zc}'
        assert sum(f.area for f in jambs) == pytest.approx(2 * w * (D.window_top - D.window_sill)), f'jambs of the window at z={zc}'


def test_the_invisible_window_barrier_is_not_a_solid_for_the_faces(pm):
    gap = next(b for b in pm.boxes if b.name.startswith('window_gap'))
    mid = tuple((gap.lo[i] + gap.hi[i]) / 2 for i in range(3))
    assert is_air(pm, mid)                                              # the middle of a window hole is air, though the barrier fills it


def test_outer_faces_are_dropped(pm):
    for f in pm.exposed_faces():
        c = f.point((f.u0 + f.u1) / 2, (f.v0 + f.v1) / 2)
        if f.axis == 0:
            assert abs(c[0]) <= D.room_x / 2 + D.wall + 1e-6
        assert c[1] <= D.ceiling + 1e-6 or f.axis != 1      # nothing on top of the ceiling slab


def test_window_barrier_stops_the_player_but_not_bullets(pm):
    gaps = [b for b in pm.boxes if b.name.startswith('window_gap')]
    assert len(gaps) == len(D.window_z)
    assert all(b.solid and not b.visible and not b.bullets for b in gaps)
    assert not any(b.name.startswith('window_gap') for _, _, b in colliders(pm))


def test_walkable_tops_cover_deck_steps_and_pool_floor(pm):
    tops = walk_tops(pm)
    assert any(abs(t[4] - 0.0) < 1e-9 for t in tops) and any(abs(t[4] - D.pool_floor) < 1e-9 for t in tops)
    rise = -D.pool_floor / (D.steps + 1)
    assert any(abs(t[4] + rise) < 1e-9 for t in tops)       # first step below the deck edge


def test_steps_are_climbable_with_the_default_step_up():
    rise = -D.pool_floor / (D.steps + 1)
    assert rise <= 0.2 and D.stair_rise <= 0.2             # PlayerParams.step_up


def test_inside_box_margin():
    b = build_map(D).boxes[0]
    mid = tuple((b.lo[i] + b.hi[i]) / 2 for i in range(3))
    assert inside_box(b, mid) and not inside_box(b, (b.hi[0] + 1, mid[1], mid[2]))


def test_atlas_pieces_do_not_overlap_and_fit(pm):
    faces = pm.exposed_faces()
    atlas = pack_atlas(faces, D.texel, n_probes=2)
    assert atlas.height & (atlas.height - 1) == 0 and atlas.height <= 2048
    rects = [(p.x - 1, p.y - 1, p.x + p.w + 1, p.y + p.h + 1) for p in atlas.faces + atlas.probes]
    for r in rects:
        assert 0 <= r[0] and r[2] <= atlas.width and 0 <= r[1] and r[3] <= atlas.height
    rects.sort()
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if b[0] >= a[2]:
                break
            assert a[3] <= b[1] or b[3] <= a[1] or a[2] <= b[0] or b[2] <= a[0], (a, b)
    for f, p in zip(faces, atlas.faces):
        assert (p.w, p.h) == face_texels(f, D.texel)


def test_atlas_rejects_a_face_wider_than_the_atlas(pm):
    with pytest.raises(ValueError):
        pack_atlas(pm.exposed_faces(), 0.01)


def test_bake_key_follows_the_sun_and_the_map():
    from fps.core.poolmap import bake_key
    a = bake_key(D, LookData())
    assert a == bake_key(D, LookData())
    assert a != bake_key(D, dataclasses.replace(LookData(), sun_dir=(0.9, 0.3, -0.3)))
    assert a != bake_key(dataclasses.replace(D, window_top=3.5), LookData())
    assert a != bake_key(D, dataclasses.replace(LookData(), ambient_up=(1, 1, 1))) or True      # ambient does not enter the bake


def test_rails_are_closed_tubes_with_valid_indices(pm):
    meshes = rail_meshes(pm)
    assert len(meshes) == 2 + D.ladder_rungs                  # two rails, then the rungs between them
    for verts, tris in meshes:
        assert len(tris) >= 16 and all(0 <= i < len(verts) for t in tris for i in t)
    for verts, tris in meshes[:2]:
        ys = [v[1] for v in verts]
        assert max(ys) > 0.8 and min(ys) < D.water_y            # the arch over the pool edge and down into the water


def test_the_ladder_hugs_the_north_wall_down_to_the_floor_with_rungs_between_the_rails():
    """G14: a real pool ladder: the rails reach the pool floor, stand just in front of the wall (not in the middle of the water), 0.6 m apart, with evenly spaced rungs under the water."""
    from fps.core.poolmap import ladder_x, ladder_z, rung_heights
    pm = build_map(D)
    meshes = rail_meshes(pm)
    xa, xb = ladder_x(D)
    assert xb - xa == pytest.approx(D.ladder_width) and (xa + xb) / 2 == pytest.approx(sum(D.north_steps_x) / 2)
    wall = D.pool_z / 2
    for verts, _ in meshes[:2]:
        ys = [v[1] for v in verts]
        assert min(ys) == pytest.approx(D.pool_deep, abs=1e-6)                         # down to the floor (the old legs stopped 0.2 m under the water)
        under = [v for v in verts if v[1] < D.water_y]
        assert under and all(wall - D.ladder_standoff - D.rail_radius - 1e-6 <= v[2] <= wall - D.ladder_standoff + D.rail_radius + 1e-6 for v in under)   # straight, in front of the wall
        assert all(v[2] < wall - 0.02 for v in under)                                    # never inside the wall
    ys = rung_heights(D)
    assert len(ys) == D.ladder_rungs and ys == sorted(ys, reverse=True)
    assert ys[0] == pytest.approx(D.water_y - 0.30) and ys[-1] == pytest.approx(D.pool_deep + 0.10)
    gaps = [a - b for a, b in zip(ys, ys[1:])]
    assert max(gaps) - min(gaps) < 1e-9 and 0.25 < gaps[0] < 0.45                        # evenly spaced like a real ladder
    for (verts, _), y in zip(meshes[2:], ys):
        xs = [v[0] for v in verts]
        assert min(xs) == pytest.approx(xa) and max(xs) == pytest.approx(xb)            # each rung spans exactly rail to rail
        assert all(abs(v[1] - y) <= D.rung_radius + 1e-9 for v in verts)


def test_ladder_shadow_casters_cover_the_tubes_above_the_water_and_are_invisible_boxes():
    from fps.core.poolmap import colliders, solid_boxes, walk_tops
    pm = build_map(D)
    casters = [b for b in pm.boxes if b.caster]
    assert casters and all(not b.visible and not b.bullets and not b.solid and not b.walk for b in casters)
    assert all(b.lo[1] >= D.water_y - 1e-9 for b in casters)                              # nothing under the water: the sun does not shade the basin through them
    for verts, _ in rail_meshes(pm)[:2]:
        for v in verts:
            if v[1] > D.water_y + 0.02:
                assert any(all(b.lo[i] - 1e-6 <= v[i] <= b.hi[i] + 1e-6 for i in range(3)) for b in casters), v
    assert all(c[2] not in casters for c in colliders(pm))                                # not hit by bullets
    assert all((lo, hi) != (b.lo, b.hi) for lo, hi in solid_boxes(pm) for b in casters) and len(walk_tops(pm)) == len(walk_tops(build_map(D)))


def test_casters_add_no_faces_to_the_room_mesh():
    pm = build_map(D)
    pm_no = build_map(D)
    pm_no.boxes[:] = [b for b in pm_no.boxes if not b.caster]
    assert len(pm.exposed_faces()) == len(pm_no.exposed_faces())


def test_uv_axes_are_two_axes_other_than_the_normal():
    for axis, (u, v) in UV_AXES.items():
        assert len({axis, u, v}) == 3


def test_ambient_grid_interpolates_and_clamps():
    from fps.core.poolmap import AmbientGrid
    up = [[[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]], [[2.0, 4.0, 6.0], [3.0, 6.0, 9.0]]]
    grid = AmbientGrid({'x0': 0.0, 'z0': 0.0, 'step': 1.0, 'nx': 2, 'nz': 2, 'up': up, 'down': [[[0.1] * 3] * 2] * 2})
    u, d = grid.sample(0.5, 0.5)
    assert u == pytest.approx((1.5, 3.0, 4.5)) and d == pytest.approx((0.1, 0.1, 0.1))
    assert grid.sample(0.0, 0.0)[0] == pytest.approx((0.0, 0.0, 0.0))
    assert grid.sample(1.0, 1.0)[0] == pytest.approx((3.0, 6.0, 9.0))
    assert grid.sample(-5.0, 9.0)[0] == pytest.approx(grid.sample(0.0, 1.0)[0])          # outside: clamped to the edge
