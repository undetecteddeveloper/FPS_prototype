"""G18 level progress and health: phases, doors, floor swap, win, death and restart; regen and the lens inputs."""
from fps.core.level import ARRIVE, CLEAR, CLIMB, DEAD, FIGHT, WON, Health, LevelState, Where
from fps.weapon_data import HealthData


def _lvl(floors=5):
    return LevelState(floors, corridor_length=8.08, swap_s=4.04, death_time=3.0)


def test_one_floor_cycle():
    lv = _lvl()
    assert lv.update(0.1, Where(arrive_s=5.0), 8, True, False) == [] and lv.door['arrive'] == 0.0
    lv.update(0.1, Where(arrive_s=7.0), 8, True, False)
    assert lv.door['arrive'] == 1.0
    assert lv.update(0.1, Where(hall_depth=3.0), 8, True, False) == ['fight'] and lv.door['arrive'] == 0.0 and lv.phase == FIGHT
    assert lv.update(0.1, Where(hall_depth=10.0), 0, True, False) == ['clear'] and lv.door['exit'] == 1.0
    assert lv.update(0.1, Where(exit_s=3.5), 0, False, False) == ['climb'] and lv.door['exit'] == 0.0
    assert lv.update(0.1, Where(exit_s=4.5), 0, False, False) == []          # the door is still closing
    assert lv.update(0.1, Where(exit_s=4.5), 0, True, False) == ['swap']
    assert lv.floor == 1 and lv.phase == ARRIVE


def test_turning_back_reopens_the_exit():
    lv = _lvl()
    lv.phase = CLIMB
    lv.update(0.1, Where(hall_depth=20.0), 0, False, False)
    assert lv.phase == CLEAR and lv.door['exit'] == 1.0


def test_last_floor_wins_at_the_top():
    lv = _lvl()
    lv.floor, lv.phase = 4, CLIMB
    assert lv.update(0.1, Where(exit_s=5.0), 0, True, False) == []
    assert lv.update(0.1, Where(exit_s=7.0), 0, True, False) == ['won'] and lv.phase == WON
    t = lv.clock
    lv.update(1.0, Where(exit_s=7.0), 0, True, False)
    assert lv.clock == t                                   # the clock stops


def test_death_restarts_at_floor_one():
    lv = _lvl()
    lv.floor, lv.phase = 3, FIGHT
    assert lv.update(0.1, Where(hall_depth=5.0), 5, True, True) == ['died'] and lv.phase == DEAD
    assert lv.update(2.0, Where(), 5, True, True) == []
    assert lv.update(1.1, Where(), 5, True, True) == ['restart']
    lv.restart()
    assert lv.floor == 0 and lv.phase == ARRIVE and lv.clock == 0.0


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
