"""G0: mở cửa sổ Ursina, nạp M4, đặt tư thế rồi chụp ảnh (bằng chứng hình ảnh).

--poses: "Clip:Khung ..." (mỗi tư thế một lượt). --views: "tên=camx,camy,camz>lookx,looky,lookz".
Ví dụ:
  python tools/g0_view.py --poses Reload:1 Reload:55 --views "eye=-0.011,1.539,-0.101>-0.011,1.539,5" --out shots/x
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.game import gltf_patch

gltf_patch.apply()

from direct.actor.Actor import Actor
from panda3d.core import AmbientLight, DirectionalLight, Filename
from ursina import Entity, Ursina, camera, color, scene, window

EYE = '-0.011,1.539,-0.101>-0.011,1.539,5'  # khớp FPS_Camera sau khi xoay 180° và scale 0,01

ap = argparse.ArgumentParser()
ap.add_argument('--poses', nargs='+', default=['Draw:299'])
ap.add_argument('--views', nargs='+', default=[f'eye={EYE}'])
ap.add_argument('--fov', type=float, default=70)
ap.add_argument('--out', default='shots/view')
args = ap.parse_args()

app = Ursina(vsync=False, development_mode=False, title='G0 view', borderless=False, size=(1280, 720))
window.color = color.rgb(0.55, 0.62, 0.7)
window.fps_counter.enabled = False

actor = Actor(Filename.from_os_specific(str(ROOT / 'guns' / 'm4_-_fps_weapon_animations_pack_v.1.glb')))
rig = Entity(scale=0.01, rotation=(0, 180, 0))
actor.reparent_to(rig)

amb = AmbientLight('amb')
amb.set_color((0.55, 0.55, 0.55, 1))
sun = DirectionalLight('sun')
sun.set_color((0.8, 0.8, 0.75, 1))
sun_np = scene.attach_new_node(sun)
sun_np.set_hpr(30, -40, 0)
actor.set_light(scene.attach_new_node(amb))
actor.set_light(sun_np)
camera.fov = args.fov
bundle = actor.getPartBundle('modelRoot')

views = []
for v in args.views:
    name, rest = v.split('=')
    cam_s, look_s = rest.split('>')
    views.append((name, [float(x) for x in cam_s.split(',')], [float(x) for x in look_s.split(',')]))
tasks = [(p, v) for p in args.poses for v in views]
state = {'n': 0, 'i': 0}
target = Entity()


def update():
    state['n'] += 1
    if state['i'] >= len(tasks):
        sys.exit(0)
    pose, (vname, cam, look) = tasks[state['i']]
    step = state['n'] % 4
    if step == 1:
        clip, frame = pose.split(':')
        actor.pose(clip, int(frame))
        bundle.force_update()
        camera.position = cam
        target.position = look
        camera.look_at(target)
    elif step == 0:
        out = Path(f"{args.out}_{pose.replace(':', '')}_{vname}.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        app.win.saveScreenshot(Filename.from_os_specific(str(out.resolve())))
        print('ĐÃ CHỤP', out)
        state['i'] += 1


app.run()
