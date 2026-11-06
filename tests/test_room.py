import math

import pytest

from fps.core.ballistics import GROUND, BoxGroup, first_hit, segment_touches_aabb
from fps.core.room import (FACES, RoomLayout, atlas_grid, beam_boxes, ceiling_box, cube_face, face_fov, grouped,
                           lamp_positions, nearest_lamp, panel_boxes, pillar_boxes, pillar_zs, tile_index, tile_rect, walk_bounds,
                           wall_boxes)

ROOM = RoomLayout()


def colliders():
    walls = [(lo, hi, 'wall') for lo, hi in wall_boxes(ROOM)] + [(*ceiling_box(ROOM), 'ceiling')]
    return walls + grouped(pillar_boxes(ROOM), 'pillar', 30.0) + grouped(beam_boxes(ROOM), 'beam', 30.0)


def test_room_is_closed_and_lane_fits():
    (lo_l, hi_l), (lo_r, hi_r), (lo_b, hi_b), (lo_e, hi_e) = wall_boxes(ROOM)
    assert hi_l[0] == -ROOM.half_width and lo_r[0] == ROOM.half_width
    assert hi_b[2] == ROOM.z_back and lo_e[2] == ROOM.z_end
    assert ROOM.z_end - 0.0 >= 200.0                                 # lane >= 200 m measured from the firing line
    for lo, hi in wall_boxes(ROOM):                                  # walls reach the ceiling
        assert hi[1] >= ROOM.height
    # the walls meet at the corners (no gaps)
    assert lo_b[0] <= lo_l[0] and hi_b[0] >= hi_r[0] and lo_e[0] <= lo_l[0] and hi_e[0] >= hi_r[0]


def test_pillars_stay_inside_the_walls_and_off_the_walk_area():
    x_min, x_max, z_min, z_max = walk_bounds(ROOM, -15.0, 198.0)
    for lo, hi in pillar_boxes(ROOM):
        assert -ROOM.half_width <= lo[0] and hi[0] <= ROOM.half_width
        assert hi[0] < x_min or lo[0] > x_max                         # pillars do not intrude on the walkable area
    assert all(ROOM.z_back < z < ROOM.z_end for z in pillar_zs(ROOM))
    assert (z_min, z_max) == (-15.0, 198.0)


@pytest.mark.parametrize('direction, owner, axis, sign', [
    ((1, 0, 0), 'wall', 0, -1), ((-1, 0, 0), 'wall', 0, 1),          # shots across into the side walls (between two pillars)
    ((0, 1, 0), 'ceiling', 1, -1), ((0, 0, -1), 'wall', 2, 1)])
def test_bullets_hit_walls_and_ceiling_from_inside(direction, owner, axis, sign):
    p0 = (0.0, 1.6, 5.0)                                              # z = 5: between two pillars (pillars at 0 and 10)
    p1 = tuple(p + d * 50 for p, d in zip(p0, direction))
    hit = first_hit(p0, p1, colliders())
    assert hit is not None and hit.owner == owner
    assert hit.normal[axis] == sign


def test_bullet_hits_the_pillar_face_not_the_wall_behind_it():
    z = pillar_zs(ROOM)[3]
    hit = first_hit((0.0, 1.6, z), (30.0, 1.6, z), colliders())
    assert hit.owner == 'pillar'
    assert hit.point[0] == pytest.approx(ROOM.half_width - ROOM.pillar_depth)
    assert hit.normal == (-1.0, 0.0, 0.0)


def test_bullet_down_the_lane_hits_the_end_wall_or_ground_never_escapes():
    hit = first_hit((0.0, 1.6, 0.0), (0.0, 1.6, 400.0), colliders())
    assert hit.owner == 'wall' and hit.point[2] == pytest.approx(ROOM.z_end)
    assert first_hit((0.0, 1.6, 0.0), (0.0, -1.0, 40.0), colliders()).owner == GROUND


def test_group_is_equivalent_to_flat_list_and_is_skipped_when_far():
    boxes = [(lo, hi, i) for i, (lo, hi) in enumerate(pillar_boxes(ROOM)) if lo[0] > 0]      # row of pillars on the right
    group = BoxGroup(boxes)
    p0, p1 = (0.0, 1.0, 9.0), (20.0, 1.2, 11.0)
    flat, grp = first_hit(p0, p1, boxes, None), first_hit(p0, p1, [group.entry()], None)
    assert flat.owner == grp.owner and flat.t == pytest.approx(grp.t)
    assert not segment_touches_aabb((0.0, 1.6, 0.0), (0.0, 1.6, 8.0), group.lo, group.hi)
    assert segment_touches_aabb((11.9, 1.0, 0.0), (11.9, 1.0, 1.0), group.lo, group.hi)   # starts inside


def test_thin_wall_is_not_tunnelled_at_low_fps():
    # a 25 m bullet step (20 FPS, not subdivided) still stops at the face of the 0.5 m thick wall
    hit = first_hit((0.0, 1.6, 5.0), (25.0, 1.6, 5.0), colliders())
    assert hit.point[0] == pytest.approx(ROOM.half_width)


def test_panels_sit_on_the_side_walls_between_pillars():
    panels = panel_boxes(ROOM)
    assert panels
    pillars = pillar_boxes(ROOM)
    for lo, hi in panels:
        assert lo[0] == -ROOM.half_width or hi[0] == ROOM.half_width
        for plo, phi in pillars:                                     # does not overlap a pillar
            assert hi[2] <= plo[2] or lo[2] >= phi[2]


def test_nearest_lamp_and_positions():
    lamps = lamp_positions(0.0, 4.6, -15.0, 10.0, 23)
    assert lamps[0][2] == -15.0 and lamps[-1][2] == 205.0
    assert ROOM.z_back < lamps[0][2] and lamps[-1][2] < ROOM.z_end
    assert nearest_lamp(0.0, -15.0, 10.0, 23) in (1, 2)
    assert nearest_lamp(-100.0, -15.0, 10.0, 23) == 0
    assert nearest_lamp(1000.0, -15.0, 10.0, 23) == 22
    for i, (_, _, z) in enumerate(lamps):
        assert nearest_lamp(z + 4.9, -15.0, 10.0, 23) == i


def test_cube_face_picks_the_major_axis():
    for i, d in enumerate(FACES):
        assert cube_face(tuple(c * 3 + 0.1 for c in d)) == i
    assert cube_face((0.1, 2.0, -0.3)) is None                         # above the lamp: no face
    assert cube_face((1.0, -1.0, 0.0)) == 0                            # tie: x takes priority, as in the shader


def test_atlas_tiles_do_not_overlap_and_cover_all_lamps():
    cols, rows = atlas_grid(23 * 5)
    assert cols * rows >= 115 and cols - rows <= 1
    rects = {tile_rect(tile_index(l, f), cols, rows) for l in range(23) for f in range(5)}
    assert len(rects) == 115
    for l, r, b, t in rects:
        assert 0 <= l < r <= 1 and 0 <= b < t <= 1
        assert r - l == pytest.approx(1 / cols) and t - b == pytest.approx(1 / rows)


def test_face_fov_guard_band():
    fov = face_fov(256, 2)
    # 90 degrees fills exactly 252 pixels in the middle of the tile
    assert math.tan(math.radians(45)) / math.tan(math.radians(fov / 2)) == pytest.approx(252 / 256)
    assert face_fov(256, 0) == pytest.approx(90.0)
