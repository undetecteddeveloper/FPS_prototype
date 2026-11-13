"""Progress through the run and the player's health (G18 / G19, pure, tests/test_level.py).

Stage 0 is the pool hall (no enemies), stages 1-5 the Backrooms floors. Phases of a stage:
  ARRIVE  he comes in: by the stair corridor (floor 1: the hall door opens when he nears it) or by the lift (the doors are open). Stepping `ENTER_DEPTH` into the floor
          shuts it behind him -> FIGHT. The pool hall starts in CLEAR (nothing to fight).
  FIGHT   until no enemy is left -> CLEAR.
  CLEAR   the way on is open: the stair corridor door (pool hall) or the lift doors.
  CLIMB   (pool hall) on the stairs: the door shuts behind him; once shut and halfway up -> 'swap' to floor 1, ARRIVE.
  BOARD   (lifts) he pressed E inside the cabin: the doors shut (stepping out first reopens them). Shut -> 'swap' to the next floor, RIDE; the last floor -> FINAL.
  RIDE    the cabin hums for `ride_time`, then the doors open -> ARRIVE.
  FINAL   the last ride; at its end -> WON (the run time is shown).
  DEAD    health 0: after `death_time` -> 'restart' (floor 1, user's choice).
"""
from dataclasses import dataclass

ARRIVE, FIGHT, CLEAR, CLIMB, BOARD, RIDE, FINAL, WON, DEAD = 'arrive', 'fight', 'clear', 'climb', 'board', 'ride', 'final', 'won', 'dead'
ENTER_DEPTH = 2.2          # m past the arrival door before it shuts behind him
OPEN_REACH = 3.0           # m before the corridor arrival door (along the corridor) where it opens
CLOSE_S = 3.0              # m up the exit corridor where its door shuts behind him


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
    arrive_s: float = None        # metres up the arrival corridor (floor 1; None: not in it)
    exit_s: float = None          # metres up the exit corridor (pool hall)
    in_arrive_cabin: bool = False
    in_exit_cabin: bool = False
    depth: float = 0.0            # metres from the arrival door into the floor (0 while still in the corridor / cabin)


class LevelState:
    def __init__(self, stages: int, corridor_length: float, swap_s: float, death_time: float, ride_time: float = 4.0, start: int = 0):
        self.stages = stages
        self.length = corridor_length
        self.swap_s = swap_s
        self.death_time = death_time
        self.ride_time = ride_time
        self.clock = 0.0              # run time (s) since floor 1 was reached
        self.dead_t = 0.0
        self.deaths = 0
        self.ride_t = 0.0
        self.enter(start)

    def enter(self, stage: int, phase: str = None):
        """Start stage `stage`: the pool hall is open at once; floor 1 is entered by the corridor; later floors by the lift (in RIDE when coming from one)."""
        self.stage = stage
        self.door = {'arrive': 0.0, 'exit': 0.0}       # target opening of the two ways in / out (0 shut, 1 open)
        if phase is None:
            phase = CLEAR if stage == 0 else ARRIVE
        self.phase = phase
        if phase == CLEAR:
            self.door['exit'] = 1.0
        if phase == ARRIVE and stage >= 2:
            self.door['arrive'] = 1.0                   # (a lift start without a ride: the doors are open)
        self.ride_t = 0.0

    @property
    def last(self) -> bool:
        return self.stage == self.stages - 1

    def update(self, dt: float, where: Where, enemies_left: int, exit_shut: bool, player_dead: bool, press_e: bool = False) -> list:
        """Advance the phases; returns this frame's events: 'fight', 'clear', 'climb', 'board', 'swap', 'arrived', 'won', 'died', 'restart'."""
        ev = []
        if self.phase not in (WON, DEAD) and self.stage >= 1:
            self.clock += min(dt, 0.1)                     # a floor-build hitch is not play time
        if player_dead and self.phase not in (DEAD, WON):
            self.phase, self.dead_t = DEAD, 0.0
            self.deaths += 1
            ev.append('died')
        if self.phase == DEAD:
            self.dead_t += dt
            if self.dead_t >= self.death_time:
                ev.append('restart')
            return ev
        if self.phase in (RIDE, FINAL):
            self.ride_t += dt
            if self.ride_t >= self.ride_time:
                if self.phase == FINAL:
                    self.phase = WON
                    ev.append('won')
                else:
                    self.phase = ARRIVE
                    self.door['arrive'] = 1.0
                    ev.append('arrived')
            return ev
        if self.phase == ARRIVE:
            self.door['exit'] = 0.0
            if where.arrive_s is not None and where.arrive_s >= self.length - OPEN_REACH:
                self.door['arrive'] = 1.0
            if where.arrive_s is None and not where.in_arrive_cabin and where.depth >= ENTER_DEPTH:
                self.phase = FIGHT
                self.door['arrive'] = 0.0
                ev.append('fight')
        if self.phase == FIGHT and enemies_left == 0:
            self.phase = CLEAR
            self.door['exit'] = 1.0
            ev.append('clear')
        if self.phase == CLEAR:
            if self.stage == 0:
                if where.exit_s is not None and where.exit_s >= CLOSE_S:
                    self.phase = CLIMB
                    self.door['exit'] = 0.0
                    ev.append('climb')
            elif where.in_exit_cabin and press_e:
                self.phase = BOARD
                self.door['exit'] = 0.0
                ev.append('board')
        if self.phase == CLIMB:
            if where.exit_s is None:                       # he turned back into the hall before the door shut
                self.phase = CLEAR
                self.door['exit'] = 1.0
            elif exit_shut and where.exit_s >= self.swap_s:
                self.enter(self.stage + 1)
                ev.append('swap')
        elif self.phase == BOARD:
            if not where.in_exit_cabin:                    # stepped out while the doors were closing
                self.phase = CLEAR
                self.door['exit'] = 1.0
            elif exit_shut:
                if self.last:
                    self.phase, self.ride_t = FINAL, 0.0
                else:
                    self.enter(self.stage + 1, RIDE)
                    ev.append('swap')
        return ev

    def restart(self, stage: int = 1):
        self.clock, self.dead_t = 0.0, 0.0
        self.enter(stage)
