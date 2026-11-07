"""The world: one big flat slab of ground. The player stands at the origin looking toward +z; the top face is the plane y = 0.

The slab is a box (not an infinite plane), so bullets hit a finite surface: past its edge a bullet simply keeps falling into the void. The optional noise is drawn by
assets/shaders/world.frag from world coordinates (set in look.py), so here we only build the geometry.
"""
from ursina import Entity, color

GROUND_HALF = 60.0               # m: the slab is 2 * GROUND_HALF on a side
GROUND_THICKNESS = 2.0           # m: below y = 0
EDGE_MARGIN = 2.0                # m: the player cannot walk closer than this to the edge
# (x_min, x_max, z_min, z_max): the player can walk within this range
WALK_BOUNDS = (-GROUND_HALF + EDGE_MARGIN, GROUND_HALF - EDGE_MARGIN, -GROUND_HALF + EDGE_MARGIN, GROUND_HALF - EDGE_MARGIN)


def aabb_of(entity):
    """(lo, hi) of an unrotated 'cube' Entity, in world coordinates."""
    x, y, z = entity.position
    sx, sy, sz = entity.scale
    return (x - sx / 2, y - sy / 2, z - sz / 2), (x + sx / 2, y + sy / 2, z + sz / 2)


def build_ground(ground_color=(1.0, 1.0, 1.0)) -> dict:
    """`floor`: the slab Entity; `colliders`: [(lo, hi, owner)] boxes bullets hit."""
    floor = Entity(model='cube', color=color.rgb(*ground_color), position=(0, -GROUND_THICKNESS / 2, 0),
                   scale=(2 * GROUND_HALF, GROUND_THICKNESS, 2 * GROUND_HALF))
    return {'floor': floor, 'colliders': [(*aabb_of(floor), floor)]}
