"""G5: đo FPS lúc đứng yên so với lúc đang nạp đạn / rút súng, và tìm thứ làm tụt FPS bằng cách tắt từng thứ.

Mỗi lần chạy đo một "biến thể" (tên đưa vào dòng lệnh), vsync tắt, 1280x720:
  base          nguyên trạng
  noblend       tắt nội suy giữa hai khung của clip (setBlend(frameBlend=False))
  nolook        không có shader thế giới (cách cũ: màu phẳng không đèn) để đo chi phí của nó
  nofx          không có tia lửa / tracer
  cpuskin       bỏ shader của súng: Panda skin bàn tay trên CPU (cách cũ, để so sánh)
  noview        không đổi FOV / nhích súng khi nạp
  nohud         tắt HUD
In ra FPS trung bình, 1% thấp nhất, khung chậm nhất của từng đoạn: đứng yên, nạp (Reload), nạp (Reload_Empty), rút súng.

Chạy:  .venv\\Scripts\\python.exe -X utf8 tools\\measure\\g5_perf.py base
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from ursina import Entity, mouse  # noqa: E402

from fps.core.handling import Phase  # noqa: E402

variant = sys.argv[1] if len(sys.argv) > 1 else 'base'
game = create_game(vsync=False, sound=False, draw=True, look=(variant != 'nolook'), effects=(variant != 'nofx'), hud=True)
mouse.locked = False
combat, viewmodel, handling, weapon = game.combat, game.viewmodel, game.combat.handling, game.combat.weapon
gun = game.params.gun

if variant == 'noblend':
    viewmodel.actor.setBlend(frameBlend=False)
elif variant == 'noview':
    gun.reload.view_pose = (0.0,) * 6
    gun.reload.view_fov = gun.view_fov
elif variant == 'cpuskin':
    from panda3d.core import ShaderAttrib
    viewmodel.root.clear_attrib(ShaderAttrib)
    for g in viewmodel.actor.find_all_matches('**/+GeomNode'):
        g.clear_attrib(ShaderAttrib)
elif variant == 'nohud':
    for e in (game.hud.fps_text, game.hud.hint, game.hud.credit, game.hud.ammo, game.hud.mode, game.hud.prompt):
        e.main.enabled = False
        if e.shadow:
            e.shadow.enabled = False
    game.hud.update = lambda *a, **k: None

segments = {}
parts = {}                      # đoạn -> {tên phần: tổng giây}: thời gian Python của từng phần trong Game.update


def timed(obj, name, label):
    fn = getattr(obj, name)

    def wrapper(*a, **k):
        t0 = pytime.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            seg = state['cur']
            if seg is not None:
                d = parts.setdefault(seg, {})
                d[label] = d.get(label, 0.0) + pytime.perf_counter() - t0
    setattr(obj, name, wrapper)


state = {'cur': None}
timed(game, 'update', 'Game.update (Python, toàn bộ)')
timed(game.combat, 'update', '  combat.update')
timed(game.viewmodel, 'animate', '  viewmodel.animate')
timed(game.viewmodel, 'update', '  viewmodel.update')
timed(game.hud, 'update', '  hud.update')
timed(game.player, 'tick', '  player.tick')


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()
        self.last = None
        self.cur = None

    def update(self):
        now = pytime.perf_counter()
        if self.last is not None and self.cur is not None:
            segments.setdefault(self.cur, []).append(now - self.last)
        self.last = now
        state['cur'] = self.cur
        try:
            next(self.gen)
        except StopIteration:
            report()
            sys.exit(0)

    def run(self):
        self.cur = 'khởi động (rút súng)'
        yield from self.until(lambda: handling.phase is Phase.READY, 5.0)
        for _ in range(60):
            yield
        self.cur = 'đứng yên'
        for _ in range(240):
            yield
        for key, mag in (('Reload (còn đạn)', 12), ('Reload_Empty (cạn)', 0)):
            weapon.mag, weapon.reserve = mag, 150
            self.cur = None
            for _ in range(30):
                yield
            self.cur = key
            game.input('r')
            yield
            yield from self.until(lambda: handling.phase is Phase.READY, 6.0)
            self.cur = None
            for _ in range(30):
                yield

    def until(self, cond, timeout):
        t0 = pytime.perf_counter()
        while not cond() and pytime.perf_counter() - t0 < timeout:
            yield


def report():
    print(f'\n=== FPS: biến thể "{variant}" ===')
    for name, dts in segments.items():
        d = sorted(dts)
        n = len(d)
        print(f'{name:24s} {n:5d} khung  trung bình {n / sum(d):6.1f} FPS   1% thấp nhất {1 / d[int(n * 0.99)]:6.1f}   '
              f'khung chậm nhất {d[-1] * 1000:6.1f} ms   khung trung bình {sum(d) / n * 1000:5.2f} ms   trung vị {d[n // 2] * 1000:5.2f} ms')
        for label, total in parts.get(name, {}).items():
            print(f'      {label:34s} {total / n * 1000:6.3f} ms/khung')
    skinned = 0
    for geom_np in viewmodel.actor.find_all_matches('**/+GeomNode'):
        node = geom_np.node()
        for i in range(node.get_num_geoms()):
            vd = node.get_geom(i).get_vertex_data()
            if vd.get_format().has_column('transform_blend'):
                skinned += vd.get_num_rows()
    print(f'số đỉnh có skin (skin trên GPU; nếu bỏ shader thì Panda tính lại trên CPU mỗi khung): {skinned}')


Script()
game.app.run()
