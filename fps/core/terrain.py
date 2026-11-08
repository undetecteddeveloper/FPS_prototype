"""Walking on the pool map (pure, tests/test_terrain.py): the height of the floor under the feet, steps up and down, and sideways pushing by columns and walls.

The floor is a list of rectangles with a top height (deck, steps, pool bottom); the feet stand on the highest top that is at most `step_up` above them.
A taller ledge ahead blocks the move (the pool edge seen from the bottom), a lower floor makes the player fall (the same physics as a jump).
Solid boxes (walls, columns) push the player's circle out sideways while the body overlaps the box vertically; the velocity into the box is removed, so he slides along it.
G14: a ledge too high to step onto (the pool edge seen from the water, the landing of the stairs) pushes the CIRCLE out the same way. It used to stop only the centre point, so
the eye ended up exactly on the pool wall plane and the camera looked through the wall.
"""
import math


def ramp_y(ramp: tuple, z: float) -> float:
    """Height of a ramp (x0, x1, z0, z1, y0, y1) at z: y0 at z0, y1 at z1, linear between."""
    _, _, z0, z1, y0, y1 = ramp
    return y0 + (y1 - y0) * (z - z0) / (z1 - z0)


class Terrain:
    def __init__(self, tops: list, solids: list, bounds: tuple, ramps: list = ()):
        """tops: [(x0, x1, z0, z1, top)]; solids: [(lo, hi)] boxes; bounds: (x_min, x_max, z_min, z_max) for the centre of the player.
        ramps: [(x0, x1, z0, z1, y0, y1)] floors sloping along z (the pool bottom between the shallow and the deep end).
        G12: the deep water is no longer blocked (G10 had a 'rope line' at chest depth): he walks down to the 2 m bottom with his head under the water."""
        self.tops = tops
        self.solids = solids
        self.bounds = bounds
        self.ramps = list(ramps)

    def _surfaces(self, x: float, z: float):
        """Every walkable height at (x, z): box tops and ramps."""
        for x0, x1, z0, z1, top in self.tops:
            if x0 <= x <= x1 and z0 <= z <= z1:
                yield top
        for r in self.ramps:
            if r[0] <= x <= r[1] and r[2] <= z <= r[3]:
                yield ramp_y(r, z)

    def floor_at(self, x: float, z: float, y_limit: float):
        """Highest walkable top at (x, z) that is <= y_limit, or None."""
        best = None
        for top in self._surfaces(x, z):
            if top <= y_limit + 1e-9 and (best is None or top > best):
                best = top
        return best

    def highest_top(self, x: float, z: float):
        return max(self._surfaces(x, z), default=None)

    def blocked_by_ledge(self, x: float, z: float, y: float, step_up: float) -> bool:
        """A walkable surface at (x, z) that is higher than the feet can step up to."""
        top = self.highest_top(x, z)
        return top is not None and top > y + step_up + 1e-9


def push_out_of_box(x: float, z: float, r: float, lo: tuple, hi: tuple):
    """Move the circle (x, z, r) out of the box footprint. Returns (x, z, nx, nz): the new centre and the push direction (0, 0 when nothing moved)."""
    cx = min(max(x, lo[0]), hi[0])
    cz = min(max(z, lo[2]), hi[2])
    dx, dz = x - cx, z - cz
    d2 = dx * dx + dz * dz
    if d2 >= r * r:
        return x, z, 0.0, 0.0
    if d2 > 1e-12:
        d = math.sqrt(d2)
        return cx + dx / d * r, cz + dz / d * r, dx / d, dz / d
    # the centre is inside the footprint: leave through the nearest side
    gaps = ((x - lo[0], -1.0, 0.0, lo[0] - r, None), (hi[0] - x, 1.0, 0.0, hi[0] + r, None), (z - lo[2], 0.0, -1.0, None, lo[2] - r), (hi[2] - z, 0.0, 1.0, None, hi[2] + r))
    gap, nx, nz, nx_pos, nz_pos = min(gaps, key=lambda g: g[0])
    return (nx_pos if nx_pos is not None else x), (nz_pos if nz_pos is not None else z), nx, nz


def resolve_move(t: Terrain, x: float, z: float, y: float, vx: float, vz: float, dt: float, radius: float, step_up: float, height: float) -> tuple:
    """Move the player's circle by (vx, vz) * dt. Returns (x, z, vx, vz) with the blocked parts of the velocity removed."""
    bx0, bx1, bz0, bz1 = t.bounds

    def clamp(px, pz):
        return min(max(px, bx0), bx1), min(max(pz, bz0), bz1)

    def blocked(px, pz):
        return t.blocked_by_ledge(px, pz, y, step_up)                # a ledge too high to step up (the pool edge seen from the bottom)

    tx, tz = clamp(x + vx * dt, z + vz * dt)
    if blocked(tx, tz):                                              # try each axis alone so he slides along the pool edge
        ax, az = clamp(x + vx * dt, z)
        bx, bz = clamp(x, z + vz * dt)
        if not blocked(ax, az):
            tx, tz, vz = ax, az, 0.0
        elif not blocked(bx, bz):
            tx, tz, vx = bx, bz, 0.0
        else:
            tx, tz, vx, vz = x, z, 0.0, 0.0
    for _ in range(2):                                               # two passes: pushing out of one box can push into the next
        for lo, hi in t.solids:
            if hi[1] <= y + 0.05 or lo[1] >= y + height:
                continue
            tx, tz, nx, nz = push_out_of_box(tx, tz, radius, lo, hi)
            if nx or nz:
                into = vx * nx + vz * nz
                if into < 0.0:
                    vx, vz = vx - into * nx, vz - into * nz
        limit = y + step_up + 1e-9
        for x0, x1, z0, z1, top in t.tops:                           # G14: a walkable top the feet cannot step onto is a wall for the whole body circle
            if top <= limit:
                continue
            tx, tz, nx, nz = push_out_of_box(tx, tz, radius, (x0, 0.0, z0), (x1, 0.0, z1))
            if nx or nz:
                into = vx * nx + vz * nz
                if into < 0.0:
                    vx, vz = vx - into * nx, vz - into * nz
    tx, tz = clamp(tx, tz)
    return tx, tz, vx, vz
