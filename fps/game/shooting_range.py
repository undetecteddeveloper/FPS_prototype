"""Shooting range: a fully ENCLOSED hall (four walls + ceiling, tiled floor) 236 m long along +z; the player stands at z = 0 looking toward +z.

The room size is in `fps.core.room.RoomLayout`, the ceiling lamps in `LookData`. Walls, columns, beams, ceiling and lamps are MERGED into a few meshes
(one draw call each) instead of hundreds of Entities. Tile texture, concrete texture, skirting paint, etc. are drawn in assets/shaders/world.frag by the
`look_material` of each Entity (set in look.py), so here we only build the geometry + vertex colour.
Targets (G2/G6) and distance text signs (G6) are placed here too. Moving targets (G6) travel sideways across the lane, between the two walls.
"""
import math

from ursina import Entity, Mesh, color

from fps.core.room import (RoomLayout, beam_boxes, ceiling_box, grouped, lamp_positions, panel_boxes, pillar_boxes,
                           walk_bounds, wall_boxes)
from fps.core.signs import SignLayout, rod_xs, sign_rect
from fps.game.signs import build_atlas
from fps.weapon_data import LookData

ROOM = RoomLayout()
LANE_HALF_WIDTH = 8.0            # paint lines of the lane (the floor is as wide as the room: ±ROOM.half_width)
LANE_BACK_Z = ROOM.z_back
LANE_END_Z = 210.0               # foot of the earth backstop
DISTANCE_MARKS = (10, 25, 50, 100, 150, 200)
# (x_min, x_max, z_min, z_max): the player can walk within this range (inside the room, not touching the columns)
WALK_BOUNDS = walk_bounds(ROOM, LANE_BACK_Z + 5.0, LANE_END_Z - 12.0)

STRIPE_MAX_DISTANCE = 50
BACKSTOP_HEIGHT = 3.2            # earth backstop in front of the last wall (lower than the ceiling so the last wall stays visible)
POST_MAX_HEIGHT = ROOM.height - 0.9

# vertex colours (the shader multiplies the texture on top); three tones: warm grey concrete, brown-red brick, blue-grey paint (skirting), yellow/orange accents
WALL_TINT = (0.62, 0.60, 0.56)
PILLAR_TINT = (0.70, 0.68, 0.64)
BEAM_TINT = (0.52, 0.51, 0.49)
PANEL_TINT = (0.40, 0.52, 0.64)         # blue-grey cloth acoustic panel (cool tone)
CEILING_TINT = (0.42, 0.42, 0.43)
SHADE_TINT = (0.16, 0.19, 0.18)          # metal lamp shade painted dark blue-black
SHADE_INNER_TINT = (0.30, 0.25, 0.19)    # inside of the shade (self-lit, x lamp_emissive): darker than the bulb so the bulb stands out
BULB_TINT = (1.0, 0.93, 0.80)


def aabb_of(entity):
    """(lo, hi) of an unrotated 'cube' Entity, in world coordinates."""
    x, y, z = entity.position
    sx, sy, sz = entity.scale
    return (x - sx / 2, y - sy / 2, z - sz / 2), (x + sx / 2, y + sy / 2, z + sz / 2)


# --- build meshes ---
class MeshBuilder:
    """Gathers many boxes / faces into one mesh. Ursina uses y-up-left: the front face is the one where cross(b - a, c - a) points OPPOSITE the normal
    (measured on Ursina's 'plane' model), so `quad` flips the vertex order to get it right."""

    def __init__(self):
        self.vertices, self.triangles, self.colors = [], [], []
        self.uvs = []                  # parallel to vertices; only put into the mesh if some face uses a texture (signs)

    def quad(self, corners, normal, tint, uvs=None):
        """`uvs`: 4 (u, v) pairs matching the order of `corners` (default (0, 0))."""
        a, b, c = corners[0], corners[1], corners[2]
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        cross = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        uvs = list(uvs) if uvs is not None else [(0.0, 0.0)] * 4
        if sum(cross[i] * normal[i] for i in range(3)) > 0:
            corners = corners[::-1]
            uvs = uvs[::-1]
        n = len(self.vertices)
        self.vertices.extend(corners)
        self.uvs.extend(uvs)
        self.colors.extend([color.rgba(*tint, 1.0)] * 4)
        self.triangles.extend([n, n + 1, n + 2, n, n + 2, n + 3])

    def box(self, lo, hi, tint, skip=(), uv=None):
        """Closed box (all 6 faces: hidden faces are still needed for the shadow map, which draws only the BACK faces to avoid 'acne'). `uv`: one texture point for the whole box."""
        for axis in range(3):
            u, v = [a for a in range(3) if a != axis]
            for sign in (-1, 1):
                if (axis, sign) in skip:
                    continue
                k = hi[axis] if sign > 0 else lo[axis]
                corners = []
                for cu, cv in ((lo[u], lo[v]), (hi[u], lo[v]), (hi[u], hi[v]), (lo[u], hi[v])):
                    p = [0.0, 0.0, 0.0]
                    p[axis], p[u], p[v] = k, cu, cv
                    corners.append(tuple(p))
                normal = [0.0, 0.0, 0.0]
                normal[axis] = float(sign)
                self.quad(corners, normal, tint, None if uv is None else [uv] * 4)

    def frustum(self, center, r_top, r_bottom, y_top, y_bottom, tint, inward=False, segments=10):
        """Side surface of a truncated cone (lamp shade), normals pointing outward (or inward if `inward`)."""
        cx, _, cz = center
        for i in range(segments):
            a0, a1 = 2 * math.pi * i / segments, 2 * math.pi * (i + 1) / segments
            ring = [(cx + r_bottom * math.cos(a0), y_bottom, cz + r_bottom * math.sin(a0)),
                    (cx + r_bottom * math.cos(a1), y_bottom, cz + r_bottom * math.sin(a1)),
                    (cx + r_top * math.cos(a1), y_top, cz + r_top * math.sin(a1)),
                    (cx + r_top * math.cos(a0), y_top, cz + r_top * math.sin(a0))]
            am = (a0 + a1) / 2
            n = (math.cos(am), (r_bottom - r_top) / (y_top - y_bottom), math.sin(am))
            if inward:
                n = tuple(-c for c in n)
            self.quad(ring, n, tint)

    def octahedron(self, center, r, tint):
        x, y, z = center
        pts = [(x + r, y, z), (x, y, z + r), (x - r, y, z), (x, y, z - r)]
        for top in ((x, y + r, z), (x, y - r, z)):
            for i in range(4):
                a, b = pts[i], pts[(i + 1) % 4]
                tri = [a, b, top]
                n = tuple((a[k] + b[k] + top[k]) / 3 - center[k] for k in range(3))
                e1 = [b[k] - a[k] for k in range(3)]
                e2 = [top[k] - a[k] for k in range(3)]
                cross = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                if sum(cross[k] * n[k] for k in range(3)) > 0:
                    tri = tri[::-1]
                m = len(self.vertices)
                self.vertices.extend(tri)
                self.colors.extend([color.rgba(*tint, 1.0)] * 3)
                self.triangles.extend([m, m + 1, m + 2])

    def entity(self, **kwargs) -> Entity:
        extra = {'uvs': self.uvs} if any(tuple(uv) != (0.0, 0.0) for uv in self.uvs) else {}
        mesh = Mesh(vertices=self.vertices, triangles=self.triangles, colors=self.colors, static=True, **extra)
        return Entity(model=mesh, **kwargs)


def _stripe(mb: MeshBuilder, z: float, width: float, tint):
    """Lane cross line. It lies flat on the ground, so a depth offset must be used instead of raising it (a 1 cm lift would still flicker at 200 m)."""
    x, h = LANE_HALF_WIDTH, width / 2.0
    mb.quad([(-x, 0.0, z - h), (x, 0.0, z - h), (x, 0.0, z + h), (-x, 0.0, z + h)], (0.0, 1.0, 0.0), tint)


def build_range(look: LookData = None) -> dict:
    look = look or LookData()
    room = ROOM
    world = {'room': room}
    w = room.half_width

    # floor: one plane covering the whole room (tile pattern drawn in the shader from world coordinates)
    world['floor'] = Entity(model='plane', position=(0, 0, (room.z_back + room.z_end) / 2),
                            scale=(2 * w, 1, room.z_end - room.z_back), color=color.white)

    # enclosing walls (4 sides), one mesh
    mb = MeshBuilder()
    for lo, hi in wall_boxes(room):
        mb.box(lo, hi, WALL_TINT)
    world['walls'] = mb.entity()

    # pillars against the walls + ceiling beams joining two pillars, one mesh
    mb = MeshBuilder()
    for lo, hi in pillar_boxes(room):
        mb.box(lo, hi, PILLAR_TINT, skip=((1, -1),))
    for lo, hi in beam_boxes(room):
        mb.box(lo, hi, BEAM_TINT, skip=((1, 1),))
    for lo, hi in panel_boxes(room):
        mb.box(lo, hi, PANEL_TINT)
    world['pillars'] = mb.entity()

    mb = MeshBuilder()
    mb.box(*ceiling_box(room), CEILING_TINT)
    world['ceiling'] = mb.entity()

    # ceiling lamps: hanging rod + shade (dark body, receives light) and the shade interior + bulb (self-lit), two meshes
    lamps = lamp_positions(look.lamp_x, look.lamp_y, look.lamp_z0, look.lamp_spacing, look.lamp_count)
    shades, glow = MeshBuilder(), MeshBuilder()
    for x, y, z in lamps:
        top, bottom = y + 0.30, y - 0.12
        shades.frustum((x, y, z), 0.13, 0.42, top, bottom, SHADE_TINT)
        shades.box((x - 0.13, top, z - 0.13), (x + 0.13, top + 0.02, z + 0.13), SHADE_TINT)                    # shade cap
        shades.box((x - 0.02, top + 0.02, z - 0.02), (x + 0.02, room.height, z + 0.02), SHADE_TINT)             # hanging rod
        glow.frustum((x, y, z), 0.125, 0.41, top - 0.005, bottom, SHADE_INNER_TINT, inward=True)
        glow.octahedron((x, y - 0.02, z), 0.10, BULB_TINT)
    world['lamp_shades'] = shades.entity()
    world['lamp_glow'] = glow.entity()
    world['lamps'] = lamps

    # firing line and distance lines
    # Lines from 100 m on are thinner than one pixel, so they always break up (MSAA on this machine drops to ~20 FPS),
    # so only lines up to STRIPE_MAX_DISTANCE are drawn; farther away, tall posts are used (and the text signs in G6).
    stripes = MeshBuilder()
    _stripe(stripes, 0.0, 0.3, (1.0, 1.0, 0.0))
    for d in DISTANCE_MARKS:
        if d <= STRIPE_MAX_DISTANCE:
            _stripe(stripes, float(d), 0.25, (1.0, 1.0, 1.0))
    stripe_entity = stripes.entity()
    stripe_entity.set_depth_offset(1)
    world['stripes'] = [stripe_entity]

    # marker posts on both sides of the lane: taller with distance so they are visible from afar (not touching the ceiling). One mesh (12 posts = 1 draw call)
    posts = MeshBuilder()
    world['post_spots'], world['post_boxes'] = [], []
    for i, d in enumerate(DISTANCE_MARKS):
        h = min(1.6 + d * 0.02, POST_MAX_HEIGHT)
        tint = (1.0, 0.5, 0.0) if i % 2 == 0 else (1.0, 1.0, 1.0)
        for side in (-1, 1):
            x = side * (LANE_HALF_WIDTH + 0.5)
            lo, hi = (x - 0.15, 0.0, float(d) - 0.15), (x + 0.15, h, float(d) + 0.15)
            posts.box(lo, hi, tint, skip=((1, -1),))
            world['post_spots'].append((x, float(d)))
            world['post_boxes'].append((lo, hi))
    world['posts'] = [posts.entity()]

    # distance signs hung from the ceiling, one pair (left, right) at each mark, text side facing the shooter. One textured mesh (text atlas) +
    # one mesh for the hanging rods. Layout in fps/core/signs.py, text in fps/game/signs.py.
    layout = SignLayout()
    atlas, cells, patch = build_atlas(DISTANCE_MARKS)
    boards, rods = MeshBuilder(), MeshBuilder()
    world['sign_rects'] = []
    for d in DISTANCE_MARKS:
        u0, u1, v0, v1 = cells[d]
        for side in (-1, 1):
            r = sign_rect(layout, d, side)
            lo, hi = r['lo'], r['hi']
            boards.box(lo, hi, (1.0, 1.0, 1.0), skip=((2, -1),), uv=patch)                 # body + back face: flat background
            zf = lo[2]                                                                       # front face (-z): text
            boards.quad([(lo[0], lo[1], zf), (hi[0], lo[1], zf), (hi[0], hi[1], zf), (lo[0], hi[1], zf)], (0.0, 0.0, -1.0),
                        (1.0, 1.0, 1.0), uvs=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
            for rx in rod_xs(r):                                                             # hanging rods from the top of the sign up to the ceiling
                if room.height - hi[1] > 0.08:
                    h = layout.rod_half
                    rods.box((rx - h, hi[1], r['cz'] - h), (rx + h, room.height, r['cz'] + h), SHADE_TINT)
            world['sign_rects'].append((d, side, r))
    world['signs'] = boards.entity(texture=atlas)
    world['sign_rods'] = rods.entity()
    world['sign_atlas'] = atlas
    world['sign_cells'] = cells

    # earth backstop at the end of the lane, against the last wall
    earth = color.rgb(0.40, 0.31, 0.22)
    depth = room.z_end - LANE_END_Z
    world['berms'] = [Entity(model='cube', color=earth, scale=(2 * w, BACKSTOP_HEIGHT, depth),
                             position=(0, BACKSTOP_HEIGHT / 2, LANE_END_Z + depth / 2))]

    # collision boxes for bullets (AABB); the ground is handled separately at y = 0. Columns and beams are grouped in 30 m spans (BoxGroup) so bullets
    # do not have to test each one at every step.
    world['colliders'] = ([(*aabb_of(e), e) for e in world['berms']]
                          + [(lo, hi, world['walls']) for lo, hi in wall_boxes(room)]
                          + [(*ceiling_box(room), world['ceiling'])]
                          + grouped(pillar_boxes(room) + panel_boxes(room), world['pillars'], 30.0)
                          + grouped(beam_boxes(room), world['pillars'], 30.0))
    world['shadow_casters'] = [world['walls'], world['pillars'], world['signs'], world['sign_rods'], *world['posts'], *world['berms']]
    return world
