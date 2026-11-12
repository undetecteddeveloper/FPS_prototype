r"""Screenshots of the gun from outside the eye (side, top, back, 3/4) in the REAL game, for checking a model's orientation, scale, sights and hands (shots\views_<gun>_<view>.png).
The gun camera is moved around the gun for the shot and put back; nothing is checked.

Run: .venv\Scripts\python.exe -X utf8 tools\with_game_lock.py .venv\Scripts\python.exe -X utf8 tools\measure\gun_views.py [--gun m1014] [--clip reload --frame 20] [--center 0.07,-0.07,0.35] [--dist 1.2]
  --clip / --frame : pose the gun in a frame of one of its clips (a key of GunData.clips) instead of the ready pose
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from main import create_game  # noqa: E402
from panda3d.core import Filename, Point3, Vec3  # noqa: E402
from ursina import Entity, application, mouse  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--gun', default='m1014')
ap.add_argument('--clip', default='')
ap.add_argument('--frame', type=int, default=0)
ap.add_argument('--center', default='0.07,-0.07,0.35')
ap.add_argument('--dist', type=float, default=1.2)
ap.add_argument('--size', default='1280x720')
args = ap.parse_args()
W, H = (int(v) for v in args.size.lower().split('x'))
centre = Point3(*(float(v) for v in args.center.split(',')))

game = create_game(vsync=False, size=(W, H), sound=False, draw=False, effects=False, gun=args.gun)
mouse.locked = False
vm = game.viewmodel
SHOTS = ROOT / 'shots'
SHOTS.mkdir(exist_ok=True)
VIEWS = {'side': (Vec3(1, 0, 0), Vec3(0, 1, 0)), 'top': (Vec3(0, 1, 0), Vec3(0, 0, 1)), 'back': (Vec3(0, 0, -1), Vec3(0, 1, 0)), 'three_quarter': (Vec3(0.7, 0.45, -0.6), Vec3(0, 1, 0)),
         'left': (Vec3(-1, 0, 0), Vec3(0, 1, 0))}


class Script(Entity):
    def __init__(self):
        super().__init__()
        self.gen = self.run()

    def update(self):
        try:
            next(self.gen)
        except StopIteration:
            print('xong')
            sys.stdout.flush()
            os._exit(0)

    def run(self):
        for _ in range(30):
            yield
        if args.clip:
            clip = game.params.gun.clips[args.clip]
            vm.actor.stop()
            vm.actor.pose(clip.anim, args.frame)
            vm._bundle.force_update()
            vm._more = True
            vm.clip_key = args.clip if args.clip.startswith('reload') else vm.clip_key
            vm._refresh_parts()
        game.player.free_look.reset()
        for name, (direction, up) in VIEWS.items():
            vm.cam_np.set_pos(centre + direction.normalized() * args.dist)
            vm.cam_np.look_at(centre, up)
            vm.lens.set_fov(40)
            for _ in range(4):
                yield
            tag = f'_{args.clip}{args.frame}' if args.clip else ''
            application.base.win.save_screenshot(Filename.from_os_specific(str(SHOTS / f'views_{args.gun}{tag}_{name}.png')))
            print('đã chụp', name)
        yield


Script()
game.app.run()
