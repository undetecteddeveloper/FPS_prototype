"""Uniform floor-plan grid over axis-aligned boxes (pure, tests/test_broadphase.py): which boxes can a point, a circle or a segment touch.

Every collision query of the game used to scan the WHOLE box list (bullets each 1/120 s step, the High Ready probe, the sun test of the gun, the player's feet and body).
That is ~3 us per box in Python: fine for the 40 boxes of the pool hall, ~2 ms a frame for a map of a few hundred boxes walked by a dozen enemies.
The grid buckets each item by its x / z footprint grown by `margin`, so a query only looks at one or a few cells. Results keep the ORIGINAL order of the
items (callers that pick 'the first / highest / nearest' get exactly what a full scan gives).
"""
import math


class Grid2D:
    def __init__(self, footprints: list, cell: float = 2.0, margin: float = 0.0):
        """footprints: [(x0, x1, z0, z1)] per item (index = position in the list). `margin` grows every footprint when bucketing: a circle query of radius
        <= margin around a point then only needs the point's own cell."""
        self.cell = cell
        self.margin = margin
        self.n = len(footprints)
        if not footprints:
            self.x0 = self.z0 = 0.0
            self.nx = self.nz = 1
            self.cells = [[]]
            return
        self.x0 = min(f[0] for f in footprints) - margin - 1e-6
        self.z0 = min(f[2] for f in footprints) - margin - 1e-6
        x1 = max(f[1] for f in footprints) + margin + 1e-6
        z1 = max(f[3] for f in footprints) + margin + 1e-6
        self.nx = max(1, math.ceil((x1 - self.x0) / cell))
        self.nz = max(1, math.ceil((z1 - self.z0) / cell))
        self.cells = [[] for _ in range(self.nx * self.nz)]
        for i, (fx0, fx1, fz0, fz1) in enumerate(footprints):
            ix0, ix1 = self._ix(fx0 - margin), self._ix(fx1 + margin)
            iz0, iz1 = self._iz(fz0 - margin), self._iz(fz1 + margin)
            for iz in range(iz0, iz1 + 1):
                row = iz * self.nx
                for ix in range(ix0, ix1 + 1):
                    self.cells[row + ix].append(i)

    def _ix(self, x: float) -> int:
        return min(max(int((x - self.x0) // self.cell), 0), self.nx - 1)

    def _iz(self, z: float) -> int:
        return min(max(int((z - self.z0) // self.cell), 0), self.nz - 1)

    def at(self, x: float, z: float) -> list:
        """Indices of the items whose footprint grown by `margin` may contain (x, z) (a superset; sorted). Outside the grid: the border cell, which is
        still a superset because nothing reaches past the grid."""
        return self.cells[self._iz(z) * self.nx + self._ix(x)]

    def box(self, x0: float, x1: float, z0: float, z1: float) -> list:
        """Sorted indices of the items whose grown footprint may overlap the rectangle."""
        ix0, ix1, iz0, iz1 = self._ix(x0), self._ix(x1), self._iz(z0), self._iz(z1)
        if ix0 == ix1 and iz0 == iz1:
            return self.cells[iz0 * self.nx + ix0]
        seen = set()
        for iz in range(iz0, iz1 + 1):
            row = iz * self.nx
            for ix in range(ix0, ix1 + 1):
                seen.update(self.cells[row + ix])
        return sorted(seen)


class BoxIndex:
    """The boxes [(lo, hi, owner)] bullets / rays are tested against, with a grid. `segment(p0, p1)` returns the candidates in the original order."""

    def __init__(self, boxes: list, cell: float = 2.0):
        self.boxes = list(boxes)
        self.grid = Grid2D([(lo[0], hi[0], lo[2], hi[2]) for lo, hi, _ in self.boxes], cell)

    def segment(self, p0, p1) -> list:
        idx = self.grid.box(min(p0[0], p1[0]), max(p0[0], p1[0]), min(p0[2], p1[2]), max(p0[2], p1[2]))
        if len(idx) == len(self.boxes):
            return self.boxes
        b = self.boxes
        return [b[i] for i in idx]

    def near(self, x: float, z: float, radius: float) -> list:
        b = self.boxes
        return [b[i] for i in self.grid.box(x - radius, x + radius, z - radius, z + radius)]
