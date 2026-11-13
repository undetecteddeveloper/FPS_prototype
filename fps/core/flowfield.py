"""Flow field for the melee swarm (G18, pure, tests/test_flowfield.py; skill `enemy-swarm-ai`).

NavGrid: the hall's floor plan cut into square cells. Each cell has the height an enemy would stand at (the highest walkable top at its centre, the same `Terrain` the player
walks), is blocked where an enemy's body circle would overlap a wall / pillar or a ledge too high to step onto, and costs more in deep water. Two neighbouring cells
(8 directions, no corner cutting) are linked only if the height difference is at most `step_up`: the pool edge is a cliff, the swarm uses the steps and the slope.

FlowField: Dijkstra from the PLAYER's cell over the whole grid gives every cell its cost-to-player; an enemy walks toward its cheapest neighbour. One field serves every
enemy, so the cost does not grow with their number. Pure Python (numpy is not used at run time in this project), so the search is TIME-SLICED: `step(budget)` settles
at most `budget` cells per frame; the previous field is used until the new one is complete, and a new goal restarts the job.
"""
import heapq
import math

SQRT2 = math.sqrt(2.0)
INF = float('inf')
DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2))


def circle_hits_rect(x: float, z: float, r: float, x0: float, x1: float, z0: float, z1: float) -> bool:
    cx, cz = min(max(x, x0), x1), min(max(z, z0), z1)
    return (x - cx) ** 2 + (z - cz) ** 2 < r * r


class NavGrid:
    def __init__(self, terrain, rect: tuple, cell: float, radius: float, step_up: float, height: float = 1.8,
                 water: tuple = None, deep_cost: float = 6.0, knee: float = 0.5, climb: float = 0.36):
        """climb: largest height difference between two linked cells (G19: a stair ramp rises ~0.27 m per 0.5 m cell; the pool edge, 0.62 m, stays a cliff)."""
        """rect (x0, x1, z0, z1): the area enemies live in. water (x0, x1, z0, z1, surface y) or None."""
        self.x0, self.z0 = rect[0], rect[2]
        self.cell = cell
        self.nx = max(1, int(math.ceil((rect[1] - rect[0]) / cell)))
        self.nz = max(1, int(math.ceil((rect[3] - rect[2]) / cell)))
        self.step_up = step_up
        self.climb = max(climb, step_up)
        n = self.nx * self.nz
        self.height = [None] * n
        self.cost = [1.0] * n
        for iz in range(self.nz):
            for ix in range(self.nx):
                i = iz * self.nx + ix
                x, z = self.center(i)
                h = terrain.highest_top(x, z)
                if h is None or self._body_blocked(terrain, x, z, h, radius, step_up, height):
                    continue
                self.height[i] = h
                if water is not None and water[0] <= x <= water[1] and water[2] <= z <= water[3]:
                    depth = water[4] - h
                    self.cost[i] = 1.0 + deep_cost * max(0.0, depth - knee)
        # links: [(j, step length in cells x mean cost)]
        self.links = [[] for _ in range(n)]
        for i in range(n):
            hi = self.height[i]
            if hi is None:
                continue
            ix, iz = i % self.nx, i // self.nx
            for dx, dz, length in DIRS:
                jx, jz = ix + dx, iz + dz
                if not (0 <= jx < self.nx and 0 <= jz < self.nz):
                    continue
                j = jz * self.nx + jx
                if not self._link_ok(i, j):
                    continue
                if dx and dz and not (self._link_ok(i, iz * self.nx + jx) and self._link_ok(i, jz * self.nx + ix)):
                    continue                                       # no corner cutting past a pillar
                self.links[i].append((j, length * 0.5 * (self.cost[i] + self.cost[j])))

    @staticmethod
    def _body_blocked(terrain, x, z, h, radius, step_up, height) -> bool:
        """An enemy standing here at height h would overlap a solid box or a ledge too high to step onto (what `resolve_move` would push him out of)."""
        pad = radius + 0.05
        for lo, hi in terrain.near_solids(x - pad, x + pad, z - pad, z + pad):
            if hi[1] > h + 0.05 and lo[1] < h + height and circle_hits_rect(x, z, radius, lo[0], hi[0], lo[2], hi[2]):
                return True
        for x0, x1, z0, z1, top in terrain.near_tops(x - pad, x + pad, z - pad, z + pad):
            if top > h + step_up + 1e-6 and circle_hits_rect(x, z, radius, x0, x1, z0, z1):
                return True
        return False

    def _link_ok(self, i: int, j: int) -> bool:
        hi, hj = self.height[i], self.height[j]
        return hi is not None and hj is not None and abs(hi - hj) <= self.climb + 1e-6

    def center(self, i: int) -> tuple:
        return self.x0 + (i % self.nx + 0.5) * self.cell, self.z0 + (i // self.nx + 0.5) * self.cell

    def index(self, x: float, z: float):
        ix, iz = int((x - self.x0) // self.cell), int((z - self.z0) // self.cell)
        if 0 <= ix < self.nx and 0 <= iz < self.nz:
            return iz * self.nx + ix
        return None

    def open(self, i) -> bool:
        return i is not None and self.height[i] is not None

    def nearest_open(self, x: float, z: float, max_ring: int = 6):
        """The open cell nearest to (x, z) (the player can stand where an enemy's wider body cannot), or None. Clamps a point outside the grid onto it first."""
        ix = min(max(int((x - self.x0) // self.cell), 0), self.nx - 1)
        iz = min(max(int((z - self.z0) // self.cell), 0), self.nz - 1)
        best, best_d = None, INF
        for ring in range(max_ring + 1):
            for jz in range(iz - ring, iz + ring + 1):
                for jx in range(ix - ring, ix + ring + 1):
                    if max(abs(jx - ix), abs(jz - iz)) != ring or not (0 <= jx < self.nx and 0 <= jz < self.nz):
                        continue
                    j = jz * self.nx + jx
                    if self.height[j] is None:
                        continue
                    cx, cz = self.center(j)
                    d = (cx - x) ** 2 + (cz - z) ** 2
                    if d < best_d:
                        best, best_d = j, d
            if best is not None:
                return best
        return None

    def open_cells(self) -> list:
        return [i for i, h in enumerate(self.height) if h is not None]


class FlowField:
    def __init__(self, nav: NavGrid):
        self.nav = nav
        self.dist = None                    # the finished field (list of cost-to-goal per cell), None until the first one is done
        self.goal = None                    # goal cell of `dist`
        self._job = None                    # (goal, dist, heap, settled flags) being built
        self._pending = None                # goal asked for while a job was running: started when it ends (restarting at every move of a walking player never finished a field)
        self.completed = 0                  # how many fields were finished (for checks)

    def request(self, goal):
        """Ask for a field toward cell `goal`: started now if nothing runs, else right after the running job (no-op if it is already the goal)."""
        if goal is None:
            return
        if self._job is not None:
            self._pending = None if goal == self._job[0] else goal
            return
        if goal != self.goal:
            self._start(goal)

    def _start(self, goal):
        n = len(self.nav.height)
        dist = [INF] * n
        dist[goal] = 0.0
        self._job = (goal, dist, [(0.0, goal)], [False] * n)

    @property
    def busy(self) -> bool:
        return self._job is not None

    def step(self, budget: int) -> bool:
        """Settle up to `budget` cells of the job under way. True when a field was finished in this call."""
        if self._job is None:
            return False
        goal, dist, heap, done = self._job
        links = self.nav.links
        pop, push = heapq.heappop, heapq.heappush
        while heap and budget > 0:
            d, i = pop(heap)
            if done[i]:
                continue
            done[i] = True
            budget -= 1
            for j, c in links[i]:
                nd = d + c
                if nd < dist[j]:
                    dist[j] = nd
                    push(heap, (nd, j))
        if heap:
            return False
        self.dist, self.goal, self._job = dist, goal, None
        self.completed += 1
        if self._pending is not None:
            pending, self._pending = self._pending, None
            if pending != goal:
                self._start(pending)
        return True

    def solve(self, goal):
        """The whole field at once (tests, start-up)."""
        self._job = self._pending = None
        self._start(goal)
        while self._job is not None:
            self.step(1 << 30)

    def cost(self, i) -> float:
        return INF if self.dist is None or i is None else self.dist[i]

    def direction(self, i):
        """Unit (dx, dz) from cell i toward its cheapest linked neighbour, or None (no field yet, i is the goal, or unreachable)."""
        if self.dist is None or i is None or self.dist[i] == INF or i == self.goal:
            return None
        dist, nav = self.dist, self.nav
        best_j, best = None, dist[i]
        for j, _ in nav.links[i]:
            if dist[j] < best:
                best_j, best = j, dist[j]
        if best_j is None:
            return None
        nx = nav.nx
        dx, dz = best_j % nx - i % nx, best_j // nx - i // nx
        k = 1.0 / math.hypot(dx, dz)
        return dx * k, dz * k
