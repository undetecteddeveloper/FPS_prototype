"""G0: chạy thật từng clip bằng Actor.play(from, to) trong cửa sổ Ursina, đo thời gian và FPS.

Không có bước nào ở đây dùng pose(): đây là đường chạy mà game sẽ dùng.
"""
import sys
import time as pytime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from fps.game import gltf_patch

gltf_patch.apply()

from direct.actor.Actor import Actor
from panda3d.core import AmbientLight, DirectionalLight, Filename, loadPrcFileData
from ursina import Entity, Ursina, camera, color, scene, window

# khoảng khung hợp lệ (xem ghi chú: khung N của clip N khung bị bao về 0)
CLIPS = [
    ('Draw', 269, 299, 1.03),
    ('Reload', 1, 110, 3.63),
    ('Reload_Empty', 111, 224, 3.80),
    ('Fire', 226, 249, 0.80),
    ('Holster', 251, 268, 0.57),
]

loadPrcFileData('', 'sync-video 0')  # Ursina(vsync=False) một mình không tắt được vsync
app = Ursina(vsync=False, development_mode=False, title='G0 timing', borderless=False, size=(1280, 720))
window.color = color.rgb(0.55, 0.62, 0.7)
window.fps_counter.enabled = False
actor = Actor(Filename.from_os_specific(str(ROOT / 'guns' / 'm4_-_fps_weapon_animations_pack_v.1.glb')))
rig = Entity(scale=0.01, rotation=(0, 180, 0))
actor.reparent_to(rig)
amb = AmbientLight('amb')
amb.set_color((0.55, 0.55, 0.55, 1))
actor.set_light(scene.attach_new_node(amb))
camera.position = (-0.011, 1.539, -0.101)
camera.fov = 70
target = Entity(position=(-0.011, 1.539, 5))
camera.look_at(target)

state = {'i': -1, 't0': 0.0, 'last': None, 'dts': [], 'warm': 0, 'results': []}


def update():
    now = pytime.perf_counter()
    if state['last'] is not None:
        state['dts'].append(now - state['last'])
    state['last'] = now
    if state['warm'] < 30:  # bỏ vài khung đầu (nạp shader, cache)
        state['warm'] += 1
        state['dts'].clear()
        return

    i = state['i']
    if i >= 0:
        clip, a, b, expected = CLIPS[i]
        ctl = actor.getAnimControl(clip)
        if not ctl.isPlaying():
            took = now - state['t0']
            state['results'].append((clip, a, b, expected, took, actor.getCurrentFrame(clip)))
        else:
            return
    i += 1
    state['i'] = i
    if i >= len(CLIPS):
        report()
        sys.exit(0)
    clip, a, b, _ = CLIPS[i]
    state['t0'] = pytime.perf_counter()
    actor.play(clip, fromFrame=a, toFrame=b)


def report():
    dts = sorted(state['dts'])
    n = len(dts)
    fps_avg = n / sum(dts)
    fps_min = 1.0 / dts[-1]
    fps_p1 = 1.0 / dts[int(n * 0.99)]
    print('\n=== THỜI GIAN CHẠY THẬT TỪNG CLIP ===')
    print(f"{'clip':14s} {'khung':>9s} {'mong đợi':>9s} {'đo được':>9s} {'lệch':>7s}  khung cuối")
    for clip, a, b, expected, took, cur in state['results']:
        print(f'{clip:14s} {a:4d}-{b:<4d} {expected:8.2f}s {took:8.2f}s {took - expected:+6.2f}s  {cur}')
    print('\n=== FPS (vsync tắt, 1280x720, Actor đang phát clip) ===')
    print(f'số khung đo: {n}   trung bình: {fps_avg:.0f}   thấp nhất: {fps_min:.0f}   1% thấp nhất: {fps_p1:.0f}')


app.run()
