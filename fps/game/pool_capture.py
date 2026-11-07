"""Captures the room ONCE for the water's reflection: six 92-degree renders from a probe above the pool, packed into one 3 x 2 atlas PNG (core/cubemap.py).

Runs inside the game (needs the window's graphics context and the world shader inputs on `render`). The water is hidden for the capture (the caller does it).
The camera axes are read back after pointing each camera and compared with the table in core/cubemap.py: if Panda's idea of 'right' ever differs, this fails loudly instead of mirroring the reflection.
"""
from panda3d.core import Camera, Filename, PerspectiveLens, Point3, Vec3, Vec4
from ursina import application

from fps.core.cubemap import COLS, FACE_FOV, ROWS, basis, region


def capture_reflection(hall, light, path, log=print):
    base = application.base
    render = base.render
    d = hall.data
    probe = Point3(*d.probe)
    size = d.reflect_size
    light.set_camera(d.probe, (1, 0, 0), (0, 1, 0), (0, 0, 1))
    buf = base.win.make_texture_buffer('reflect_capture', size * COLS, size * ROWS, to_ram=True)
    if buf is None:
        raise RuntimeError('không tạo được bộ đệm ảnh để chụp phản chiếu')
    fog = hall.params.look.fog_color
    buf.set_clear_color(Vec4(fog[0], fog[1], fog[2], 1.0))
    buf.set_clear_color_active(True)
    buf.set_clear_depth_active(True)
    cams = []
    try:
        for f in range(6):
            right, up, forward = basis(f)
            lens = PerspectiveLens()
            lens.set_aspect_ratio(1.0)
            lens.set_fov(FACE_FOV)
            lens.set_near_far(0.05, 300.0)
            cam = render.attach_new_node(Camera(f'reflect_face{f}'))
            cam.node().set_lens(lens)
            cam.set_pos(probe)
            cam.look_at(probe + Vec3(*forward), Vec3(*up))
            got = [render.get_relative_vector(cam, Vec3(*axis)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            for name, axis, vec in zip(('phải', 'lên', 'tới'), (right, up, forward), got):
                if (vec - Vec3(*axis)).length() > 1e-3:
                    raise RuntimeError(f'camera chụp mặt {f}: trục {name} lệch bảng cubemap ({tuple(round(c, 3) for c in vec)} thay vì {axis})')
            l, r, b, t = region(f)
            buf.make_display_region(l, r, b, t).set_camera(cam)
            cams.append(cam)
        base.graphicsEngine.render_frame()
        base.graphicsEngine.render_frame()
        tex = buf.get_texture()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not tex.write(Filename.from_os_specific(str(path))):
            raise RuntimeError(f'không ghi được {path}')
    finally:
        for cam in cams:
            cam.remove_node()
        base.graphicsEngine.remove_window(buf)
    log(f'[map] đã chụp phản chiếu căn phòng -> {path.name} ({size * COLS}x{size * ROWS})')
