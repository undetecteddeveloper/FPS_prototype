"""Progress through the Backrooms level and the player's health (G18, pure, tests/test_level.py).

Phases of a floor:
  ARRIVE  the player is in the arrival corridor; the hall door opens when he comes near it (top landing).
  FIGHT   he stepped into the hall: the door behind him closes. Ends when no enemy is left.
  CLEAR   the exit door (north wall, the stairs up) opens; the next floor is built now (a short hitch while nobody attacks).
  CLIMB   he is on the stairs up: the exit door closes behind him; once it is shut and he is halfway up, the floor is swapped (`'swap'`).
  WON     the last floor's stairs reached the top landing: the time is shown.
  DEAD    health 0: after `death_time` the level restarts at floor 1 (user's choice).
"""
from dataclasses import dataclass

ARRIVE, FIGHT, CLEAR, CLIMB, WON, DEAD = 'arrive', 'fight', 'clear', 'climb', 'won', 'dead'
ENTER_DEPTH = 2.2          # m into the hall past the arrival door before it closes behind him
OPEN_REACH = 3.0           # m before the arrival door (along the corridor) where it opens
CLOSE_S = 3.0              # m up the exit corridor where the exit door closes behind him
WIN_S = 1.5                # m before the top end of the last corridor where the level is won


class Health:
    def __init__(self, data):
        self.d = data
        self.hp = data.max_hp
        self.since_hit = 1e9
        self.flash = 0.0                  # red edge right after a hit, 0..1

    @property
    def dead(self) -> bool:
        return self.hp <= 0.0

    @property
    def share(self) -> float:
        return max(self.hp, 0.0) / self.d.max_hp

    def hit(self, damage: float) -> bool:
        """Take damage. True when this hit killed."""
        if self.dead:
            return False
        self.hp = max(0.0, self.hp - damage)
        self.since_hit = 0.0
        self.flash = min(1.0, self.flash + self.d.flash * damage / 25.0)
        return self.dead

    def update(self, dt: float):
        self.flash = max(0.0, self.flash - self.d.flash_decay * dt)
        self.since_hit += dt
        if not self.dead and self.since_hit >= self.d.regen_delay:
            self.hp = min(self.d.max_hp, self.hp + self.d.regen_rate * dt)

    def reset(self):
        self.hp, self.since_hit, self.flash = self.d.max_hp, 1e9, 0.0

    def hurt_inputs(self) -> tuple:
        """(red edge 0..1, colour drain 0..1) for the lens: the hit flash, or the steady edge of low health."""
        low = min(max((self.d.low_start - self.share) / max(self.d.low_start, 1e-3), 0.0), 1.0)
        if self.dead:
            low = 1.0
        return max(self.flash, low * 0.8), low * self.d.low_desaturate


@dataclass
class Where:
    """Where the player is, in the terms the level cares about (the game measures it every frame)."""
    arrive_s: float = None        # metres up the arrival corridor (None: not in it)
    exit_s: float = None          # metres up the exit corridor
    hall_depth: float = 0.0       # metres into the hall from the arrival wall (south)


class LevelState:
    def __init__(self, floors: int, corridor_length: float, swap_s: float, death_time: float):
        self.floors = floors
        self.length = corridor_length
        self.swap_s = swap_s
        self.death_time = death_time
        self.floor = 0
        self.phase = ARRIVE
        self.clock = 0.0              # run time (s) since floor 1 started
        self.dead_t = 0.0
        self.deaths = 0
        self.door = {'arrive': 0.0, 'exit': 0.0}       # target opening of the two hall doors (0 shut, 1 open)

    def update(self, dt: float, where: Where, enemies_left: int, exit_shut: bool, player_dead: bool) -> list:
        """Advance the phases; returns the events of this frame: 'fight', 'clear', 'climb', 'swap', 'won', 'died', 'restart'."""
        ev = []
        if self.phase not in (WON, DEAD):
            self.clock += min(dt, 0.1)                        # a floor build hitch is not play time
        if player_dead and self.phase != DEAD and self.phase != WON:
            self.phase, self.dead_t = DEAD, 0.0
            self.deaths += 1
            ev.append('died')
        if self.phase == DEAD:
            self.dead_t += dt
            if self.dead_t >= self.death_time:
                ev.append('restart')
            return ev
        if self.phase == ARRIVE:
            self.door['exit'] = 0.0
            near = where.arrive_s is not None and where.arrive_s >= self.length - OPEN_REACH
            if near or where.hall_depth > 0.0:
                self.door['arrive'] = 1.0
            if where.arrive_s is None and where.hall_depth >= ENTER_DEPTH:
                self.phase = FIGHT
                self.door['arrive'] = 0.0
                ev.append('fight')
        if self.phase == FIGHT and enemies_left == 0:
            self.phase = CLEAR
            self.door['exit'] = 1.0
            ev.append('clear')
        if self.phase == CLEAR and where.exit_s is not None and where.exit_s >= CLOSE_S:
            self.phase = CLIMB
            self.door['exit'] = 0.0
            ev.append('climb')
        if self.phase == CLIMB and where.exit_s is None:      # he turned back into the hall before the door shut: open it again
            self.phase = CLEAR
            self.door['exit'] = 1.0
        if self.phase == CLIMB:
            last = self.floor == self.floors - 1
            if last:
                if where.exit_s is not None and where.exit_s >= self.length - WIN_S:
                    self.phase = WON
                    ev.append('won')
            elif exit_shut and where.exit_s is not None and where.exit_s >= self.swap_s:
                self.floor += 1
                self.phase = ARRIVE
                self.door = {'arrive': 0.0, 'exit': 0.0}
                ev.append('swap')
        return ev

    def restart(self):
        self.floor, self.phase, self.clock, self.dead_t = 0, ARRIVE, 0.0, 0.0
        self.door = {'arrive': 0.0, 'exit': 0.0}
