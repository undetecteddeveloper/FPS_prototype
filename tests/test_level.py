"""G18 / G19 progress through the run and health: the pool hall -> stairs -> floor 1, lifts between floors, the last ride wins, death restarts at floor 1."""
from fps.core.level import ARRIVE, BOARD, CLEAR, CLIMB, DEAD, FIGHT, FINAL, RIDE, WON, Health, LevelState, Where
from fps.weapon_data import HealthData


def _lvl(start=0):
    return LevelState(6, corridor_length=8.08, swap_s=4.04, death_time=3.0, ride_time=4.0, start=start)


def test_pool_hall_to_floor_one_by_the_stairs():
    lv = _lvl(0)
    assert lv.phase == CLEAR and lv.door['exit'] == 1.0
    assert lv.update(0.1, Where(exit_s=3.5), 0, False, False) == ['climb'] and lv.door['exit'] == 0.0
    assert lv.update(0.1, Where(exit_s=4.5), 0, False, False) == []          # still shutting
    assert lv.update(0.1, Where(exit_s=4.5), 0, True, False) == ['swap'] and lv.stage == 1 and lv.phase == ARRIVE
    lv.update(0.1, Where(arrive_s=7.0), 8, True, False)
    assert lv.door['arrive'] == 1.0
    assert lv.update(0.1, Where(depth=3.0), 8, True, False) == ['fight'] and lv.door['arrive'] == 0.0


def test_turning_back_on_the_stairs_reopens():
    lv = _lvl(0)
    lv.update(0.1, Where(exit_s=3.5), 0, False, False)
    lv.update(0.1, Where(), 0, False, False)
    assert lv.phase == CLEAR and lv.door['exit'] == 1.0


def test_lift_ride_between_floors():
    lv = _lvl(1)
    lv.phase = FIGHT
    assert lv.update(0.1, Where(depth=10.0), 0, True, False) == ['clear'] and lv.door['exit'] == 1.0
    assert lv.update(0.1, Where(in_exit_cabin=True), 0, False, False) == []          # inside, no E yet
    assert lv.update(0.1, Where(in_exit_cabin=True), 0, False, False, press_e=True) == ['board'] and lv.phase == BOARD
    assert lv.update(0.1, Where(in_exit_cabin=True), 0, False, False) == []          # doors shutting
    assert lv.update(0.1, Where(in_exit_cabin=True), 0, True, False) == ['swap'] and lv.stage == 2 and lv.phase == RIDE
    assert lv.door['arrive'] == 0.0
    assert lv.update(2.0, Where(in_arrive_cabin=True), 8, True, False) == []
    assert lv.update(2.1, Where(in_arrive_cabin=True), 8, True, False) == ['arrived'] and lv.door['arrive'] == 1.0 and lv.phase == ARRIVE
    assert lv.update(0.1, Where(in_arrive_cabin=True), 8, True, False) == []         # still in the cabin
    assert lv.update(0.1, Where(depth=3.0), 8, True, False) == ['fight']


def test_stepping_out_while_boarding_reopens():
    lv = _lvl(2)
    lv.phase, lv.door['exit'] = CLEAR, 1.0
    lv.update(0.1, Where(in_exit_cabin=True), 0, False, False, press_e=True)
    lv.update(0.1, Where(depth=5.0), 0, False, False)
    assert lv.phase == CLEAR and lv.door['exit'] == 1.0


def test_last_ride_wins():
    lv = _lvl(5)
    lv.phase = CLEAR
    lv.update(0.1, Where(in_exit_cabin=True), 0, False, False, press_e=True)
    assert lv.update(0.1, Where(in_exit_cabin=True), 0, True, False) == [] and lv.phase == FINAL and lv.stage == 5
    assert lv.update(4.1, Where(in_exit_cabin=True), 0, True, False) == ['won'] and lv.phase == WON
    t = lv.clock
    lv.update(1.0, Where(), 0, True, False)
    assert lv.clock == t


def test_death_restarts_at_floor_one():
    lv = _lvl(3)
    lv.phase = FIGHT
    assert lv.update(0.1, Where(depth=5.0), 5, True, True) == ['died'] and lv.phase == DEAD
    assert lv.update(2.0, Where(), 5, True, True) == []
    assert lv.update(1.1, Where(), 5, True, True) == ['restart']
    lv.restart()
    assert lv.stage == 1 and lv.phase == ARRIVE and lv.clock == 0.0


def test_clock_runs_from_floor_one_and_skips_hitches():
    lv = _lvl(0)
    lv.update(1.0, Where(), 0, True, False)
    assert lv.clock == 0.0                                  # the pool hall is not timed
    lv.enter(1)
    lv.update(0.5, Where(arrive_s=1.0), 8, True, False)
    assert abs(lv.clock - 0.1) < 1e-9                       # a 0.5 s hitch counts 0.1 s


def test_health_regen_and_lens():
    h = Health(HealthData())
    assert h.hurt_inputs() == (0.0, 0.0)
    h.hit(30.0)
    assert h.hp == 70.0 and h.hurt_inputs()[0] > 0.5
    for _ in range(int(HealthData().regen_delay * 10) - 1):
        h.update(0.1)
    assert h.hp == 70.0
    for _ in range(20):
        h.update(0.1)
    assert 70.0 < h.hp <= 100.0
    h.reset()
    h.hit(80.0)
    edge, drain = h.hurt_inputs()
    assert drain > 0.0 and not h.dead
    assert h.hit(50.0) and h.dead and h.hurt_inputs()[1] == HealthData().low_desaturate
