"""Tay + súng nhìn từ mắt người chơi.

Súng nằm trong đồ thị cảnh RIÊNG, vẽ bằng camera riêng (vùng hiển thị thứ hai, xoá lại độ sâu):
  - FOV của súng độc lập với FOV thế giới (ADS hạ FOV thế giới mà súng không bị méo, G4),
  - súng không bao giờ xuyên vào tường/bia,
  - độ sâu tầm 200 m của thế giới không bị mặt phẳng gần 1 cm của súng làm hỏng.

Chuỗi nút: root -> sway -> rig -> actor.   `sway` nhận kick súng, sway, bob, tư thế chạy và ADS (cộng lại trong `update`);
`rig` chỉ làm nhiệm vụ căn mô hình sao cho khớp FPS_Camera trùng gốc camera.
"""
from pathlib import Path

from direct.actor.Actor import Actor
from panda3d.core import (Camera, Filename, NodePath, PerspectiveLens, Point3, PTA_LVecBase3f, ShaderAttrib, Vec3)
from ursina import application, window

from fps.core.movement import smoothstep, step_toward
from fps.game.shaders import load_glsl
from fps.weapon_data import GunData


class Viewmodel:
    def __init__(self, gun: GunData, project_root: Path):
        self.gun = gun
        base = application.base

        self.root = NodePath('viewmodel_root')      # không gắn vào render: camera chính không thấy
        self.sway = self.root.attach_new_node('viewmodel_sway')
        self.rig = self.sway.attach_new_node('viewmodel_rig')

        self.actor = Actor(Filename.from_os_specific(str(project_root / gun.glb)))
        self.actor.reparent_to(self.rig)
        self._bundle = self.actor.getPartBundle('modelRoot')
        self.actor.setBlend(frameBlend=True)         # clip 30 fps mà màn hình 60+ Hz: nội suy giữa hai khung cho mượt

        self.clip_key = None                          # clip đang phát (khoá của GunData.clips) hoặc None
        self._fade = None                             # đang trượt từ tư thế đứng yên của clip bị huỷ về tư thế sẵn sàng
        self._empty = 0.0                             # 0 bolt đóng .. 1 bolt khoá sau (băng cạn)
        self._view = 0.0                              # 0 .. 1 góc nhìn riêng cho clip nạp (FOV rộng, súng nhích lên)
        self._fov = None

        # file tính bằng cm và quay mặt về -z: đổi sang mét và quay 180 độ cho nhìn về +z
        self.rig.set_scale(gun.model_scale)
        self.rig.set_h(180)
        self.hold_ready_pose()

        # tịnh tiến sao cho khớp FPS_Camera nằm đúng gốc (= vị trí camera vẽ súng)
        eye_joint = self.actor.exposeJoint(None, 'modelRoot', gun.eye_joint)
        eye = self.sway.get_relative_point(eye_joint, Point3(0, 0, 0))
        self.rig.set_pos(-eye + Vec3(*gun.hip_offset))

        self._set_up_shading()
        self._set_up_camera(base)
        self._hide_reload_props()

    # --- dựng ---
    def _set_up_shading(self):
        """Shader riêng cho súng + tay, skin bộ xương trên GPU.

        Skin trên CPU (mặc định của Panda) tính lại 2 875 đỉnh bàn tay mỗi khung ~1,3 ms; vì clip 30 fps được nội suy để mượt ở
        màn 60+ Hz nên bộ xương đổi MỌI khung hình và FPS tụt rõ lúc nạp đạn. Mesh có skin (cột transform_blend) dùng biến thể
        ENABLE_SKINNING + cờ F_hardware_skinning; mesh cứng (thân súng, băng đạn gắn vào khớp) dùng biến thể không skin."""
        static = ShaderAttrib.make(load_glsl('viewmodel'))
        skinned = ShaderAttrib.make(load_glsl('viewmodel', ('ENABLE_SKINNING',))).set_flag(ShaderAttrib.F_hardware_skinning, True)
        self.root.set_attrib(static)
        self.skinned_vertices = 0
        for geom_np in self.actor.find_all_matches('**/+GeomNode'):
            node = geom_np.node()
            for i in range(node.get_num_geoms()):
                vd = node.get_geom(i).get_vertex_data()
                if vd.get_format().has_column('transform_blend'):
                    self.skinned_vertices += vd.get_num_rows()
                    geom_np.set_attrib(skinned)
                    break
        self.apply_light()
        r = self.root
        # đèn tia lửa đổi MỖI khung lúc bắn: đưa vào shader bằng mảng PTA sửa tại chỗ. Gọi set_shader_input lại mỗi khung thì trạng thái
        # vẽ của cả súng đổi theo, Panda phải ghép lại trạng thái cho từng mesh (khung bắn đầu tiên chậm ~40 ms và mỗi khung bắn đều tốn thêm)
        self._flash_pos = PTA_LVecBase3f.empty_array(1)
        self._flash_color = PTA_LVecBase3f.empty_array(1)
        self._flash_falloff = float(self.gun.flash.light_attenuation[2])
        r.set_shader_input('flash_pos', self._flash_pos)
        r.set_shader_input('flash_color', self._flash_color)
        r.set_shader_input('flash_falloff', float(self.gun.flash.light_attenuation[2]))
        self.set_flash_light(Vec3(0, 0, 0), Vec3(0, 0, 0))

    def apply_light(self):
        """Đẩy `GunData.view_light` vào shader của súng (lúc dựng, và mỗi khi bảng debug đổi một số ánh sáng; chỉ đổi vài uniform)."""
        light, r = self.gun.view_light, self.root
        norm = sum(c * c for c in light.sun_dir) ** 0.5 or 1.0
        r.set_shader_input('sun_dir', Vec3(*(c / norm for c in light.sun_dir)))
        r.set_shader_input('sun_color', Vec3(*light.sun_color))
        r.set_shader_input('sky_color', Vec3(*light.sky_color))
        r.set_shader_input('ground_color', Vec3(*light.ground_color))
        r.set_shader_input('spec_strength', light.specular)
        r.set_shader_input('rim_strength', light.rim)

    def set_flash_light(self, view_pos, color, falloff: float = None):
        """Đèn tia lửa đầu nòng. `view_pos` trong hệ của cảnh súng (x phải, y lên, z ra trước); `color` đen = tắt.
        `falloff` đặt một lần lúc dựng (đổi giữa chừng sẽ đổi trạng thái vẽ)."""
        self._flash_pos.set_element(0, Vec3(view_pos[0], view_pos[1], -view_pos[2]))     # không gian nhìn của GL: -z là phía trước
        self._flash_color.set_element(0, Vec3(*color))
        if falloff is not None and falloff != self._flash_falloff:
            self._flash_falloff = falloff
            self.root.set_shader_input('flash_falloff', float(falloff))

    def _set_up_camera(self, base):
        self.lens = PerspectiveLens()
        self.lens.set_near_far(0.01, 20.0)
        self._aspect = None
        self._sync_lens()
        cam_node = Camera('viewmodel_cam')
        cam_node.set_lens(self.lens)
        self.cam_np = self.root.attach_new_node(cam_node)

        self.region = base.win.make_display_region()
        self.region.set_sort(5)                      # sau thế giới (0), trước giao diện (20)
        self.region.set_clear_depth_active(True)
        self.region.set_clear_depth(1.0)
        self.region.set_clear_color_active(False)
        self.region.set_camera(self.cam_np)

    @property
    def current_fov(self) -> float:
        """FOV ngang đang dùng của camera súng (đổi khi nạp đạn)."""
        return self._fov

    def _sync_lens(self):
        r = self.gun.reload
        fov = self.gun.view_fov + (r.view_fov - self.gun.view_fov) * smoothstep(self._view)
        aspect = window.aspect_ratio
        if aspect != self._aspect or fov != self._fov:
            self._aspect, self._fov = aspect, fov
            self.lens.set_aspect_ratio(aspect)
            self.lens.set_fov(fov)                   # FOV ngang

    def _hide_reload_props(self):
        """Mag2 và viên đạn của nó chỉ có trong clip reload; ngoài reload chúng lơ lửng bên dưới súng."""
        self.reload_props = []
        mag2 = self.actor.find('**/Mag2_M4_D_0-parent')
        if mag2.is_empty():
            return
        center = self._center(mag2)
        bullets = list(self.actor.find_all_matches('**/Bullet5_56x45mm_Bullet5_56x45mm_D_0-parent'))
        # hai viên đạn trùng tên: viên đi theo Mag2 là viên ở gần Mag2 nhất
        bullets.sort(key=lambda b: (self._center(b) - center).length())
        self.reload_props = [mag2] + bullets[:1]
        self.set_reload_props_visible(False)

    def _center(self, node):
        lo, hi = node.get_tight_bounds(self.actor)
        return (lo + hi) / 2

    # --- animation: tư thế đứng yên, phát clip, huỷ ---
    def _ready_frame(self) -> tuple:
        """(anim, khung) của tư thế sẵn sàng = khung cuối của Draw (bolt đóng)."""
        clip = self.gun.clips['draw']
        return clip.anim, clip.end

    def _locked_frame(self) -> tuple:
        """(anim, khung) của tư thế băng cạn: khung đầu Reload_Empty có bolt khoá sau (các khớp khác trùng tư thế sẵn sàng)."""
        clip = self.gun.clips['reload_empty']
        return clip.anim, clip.start

    def hold_ready_pose(self):
        """Đứng yên ở tư thế sẵn sàng, bolt đóng. Tắt trộn: mỗi tư thế đặt vào là tư thế duy nhất."""
        self.clip_key, self._fade, self._empty = None, None, 0.0
        self.actor.disableBlend()
        self.actor.pose(*self._ready_frame())
        self._bundle.force_update()

    def set_reload_props_visible(self, visible: bool):
        for node in self.reload_props:
            node.show() if visible else node.hide()

    def on_event(self, event: tuple):
        """Sự kiện của core.handling.Handling: ('start', key, speed) / ('swap', key) / ('done', key) / ('cancel', key, frame)."""
        name = event[0]
        if name == 'start':
            self._play(event[1], event[2])
        elif name == 'done':
            self.hold_ready_pose()
        elif name == 'cancel':
            self._begin_fade(event[1])

    def _play(self, key: str, speed: float):
        clip = self.gun.clips[key]
        self.hold_ready_pose()                            # xoá mọi trộn / trượt còn dở trước khi phát (phát là tư thế duy nhất)
        self.actor.play(clip.anim, fromFrame=clip.start, toFrame=clip.end)
        self.actor.setPlayRate(speed, clip.anim)
        self.clip_key = key

    def _begin_fade(self, key: str):
        """Huỷ clip: đứng yên tại khung hiện tại, trượt về tư thế sẵn sàng trong `reload.cancel_blend` giây."""
        anim = self.gun.clips[key].anim
        self.actor.stop(anim)
        self.actor.enableBlend()
        self.actor.setControlEffect(anim, 1.0)
        ready_anim, ready_frame = self._ready_frame()
        self.actor.pose(ready_anim, ready_frame)
        self.actor.setControlEffect(ready_anim, 0.0)
        self._fade = {'anim': anim, 't': 0.0}
        self.clip_key = None

    def _reload_view_wanted(self) -> bool:
        """Đang nạp và chưa tới `Clip.settle` trừ thời gian trộn: góc nhìn nạp (FOV rộng, súng nhích lên) phải tắt XONG khi súng về chỗ,
        không đợi hết clip (đoạn cuối chỉ là ngón tay xếp lại, súng nhích lên mà không có gì xảy ra trông như bị đặt sai chỗ)."""
        if self.clip_key not in ('reload', 'reload_empty'):
            return False
        clip = self.gun.clips[self.clip_key]
        settle = clip.settle if clip.settle is not None else clip.end
        left = (settle - self.actor.getCurrentFrame(clip.anim)) / 30.0 / max(self.gun.reload.speed, 1e-3)
        return left > self.gun.reload.view_blend

    def animate(self, dt: float, magazine_empty: bool):
        """Mỗi khung (trước `update`): tiến trình trượt khi huỷ, và bolt khoá sau / nhả khi băng cạn / có đạn."""
        r = self.gun.reload
        self._view = step_toward(self._view, 1.0 if self._reload_view_wanted() else 0.0, 1.0 / max(r.view_blend, 1e-3), dt)
        if self._fade:
            f = self._fade
            f['t'] += dt
            w = smoothstep(f['t'] / r.cancel_blend) if r.cancel_blend > 0 else 1.0
            ready_anim = self._ready_frame()[0]
            self.actor.setControlEffect(f['anim'], 1.0 - w)
            self.actor.setControlEffect(ready_anim, w)
            if w >= 1.0:
                self.hold_ready_pose()
            return
        if self.clip_key:
            return                                        # clip tự chạy theo đồng hồ Panda
        target = 1.0 if magazine_empty else 0.0
        if self._empty == target:
            return
        self._empty = step_toward(self._empty, target, 1.0 / max(r.bolt_lock_blend, 1e-3), dt)
        ready, locked = self._ready_frame(), self._locked_frame()
        if self._empty <= 0.0 or self._empty >= 1.0:
            self.actor.disableBlend()
            self.actor.pose(*(locked if self._empty >= 1.0 else ready))
        else:
            self.actor.enableBlend()
            self.actor.pose(*ready)
            self.actor.pose(*locked)
            self.actor.setControlEffect(ready[0], 1.0 - self._empty)
            self.actor.setControlEffect(locked[0], self._empty)
        self._bundle.force_update()

    def update(self, *poses: tuple):
        """Mỗi tư thế = (x phải, y lên, z ra trước, pitch ngóc lên, yaw phải, roll phải), mét và độ: kick súng
        (GunKick.pose) và sway/ADS/chạy (Sway.update). Cộng lại rồi đặt lên nút `sway`.

        BẪY dấu (đã đo bằng tools/g3_selftest.py): `set_hpr` THÔ của nút trong đồ thị súng này khác `Entity.rotation`
        của Ursina ở thế giới: h dương quay súng sang TRÁI, p dương ngóc nòng LÊN, r dương nghiêng PHẢI."""
        self._sync_lens()
        k = smoothstep(self._view)
        if k > 0.0:
            poses = poses + (tuple(c * k for c in self.gun.reload.view_pose),)
        x, y, z, pitch_up, yaw_right, roll_right = (sum(c) for c in zip(*poses)) if poses else (0,) * 6
        self.sway.set_pos_hpr(x, y, z, -yaw_right, pitch_up, roll_right)

    def destroy(self):
        base = application.base
        base.win.remove_display_region(self.region)
        self.actor.cleanup()
        self.actor.remove_node()
        self.root.remove_node()
