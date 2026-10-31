"""Tay + súng nhìn từ mắt người chơi.

Súng nằm trong đồ thị cảnh RIÊNG, vẽ bằng camera riêng (vùng hiển thị thứ hai, xoá lại độ sâu):
  - FOV của súng độc lập với FOV thế giới (ADS hạ FOV thế giới mà súng không bị méo, G4),
  - súng không bao giờ xuyên vào tường/bia,
  - độ sâu tầm 200 m của thế giới không bị mặt phẳng gần 1 cm của súng làm hỏng.

Chuỗi nút: root -> sway -> rig -> actor.   `sway` dành cho code recoil/sway/ADS (G3, G4);
`rig` chỉ làm nhiệm vụ căn mô hình sao cho khớp FPS_Camera trùng gốc camera.
"""
from pathlib import Path

from direct.actor.Actor import Actor
from panda3d.core import (AmbientLight, Camera, DirectionalLight, Filename, NodePath, PerspectiveLens, Point3,
                          Vec3)
from ursina import application, window

from weapon_data import GunData


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

        # file tính bằng cm và quay mặt về -z: đổi sang mét và quay 180 độ cho nhìn về +z
        self.rig.set_scale(gun.model_scale)
        self.rig.set_h(180)
        self.hold_ready_pose()

        # tịnh tiến sao cho khớp FPS_Camera nằm đúng gốc (= vị trí camera vẽ súng)
        eye_joint = self.actor.exposeJoint(None, 'modelRoot', gun.eye_joint)
        eye = self.sway.get_relative_point(eye_joint, Point3(0, 0, 0))
        self.rig.set_pos(-eye + Vec3(*gun.hip_offset))

        self._set_up_lights()
        self._set_up_camera(base)
        self._hide_reload_props()

    # --- dựng ---
    def _set_up_lights(self):
        ambient = AmbientLight('viewmodel_ambient')
        ambient.set_color((0.6, 0.6, 0.6, 1))
        sun = DirectionalLight('viewmodel_sun')
        sun.set_color((0.8, 0.8, 0.75, 1))
        sun_np = self.root.attach_new_node(sun)
        sun_np.set_hpr(30, -40, 0)
        self.root.set_light(self.root.attach_new_node(ambient))
        self.root.set_light(sun_np)

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

    def _sync_lens(self):
        aspect = window.aspect_ratio
        if aspect != self._aspect:
            self._aspect = aspect
            self.lens.set_aspect_ratio(aspect)
            self.lens.set_fov(self.gun.view_fov)     # FOV ngang

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

    # --- dùng ---
    def hold_ready_pose(self):
        """Tư thế sẵn sàng = khung cuối của Draw."""
        clip = self.gun.clips['draw']
        self.actor.pose(clip.anim, clip.end)
        self._bundle.force_update()

    def set_reload_props_visible(self, visible: bool):
        for node in self.reload_props:
            node.show() if visible else node.hide()

    def update(self):
        self._sync_lens()

    def destroy(self):
        base = application.base
        base.win.remove_display_region(self.region)
        self.actor.cleanup()
        self.actor.remove_node()
        self.root.remove_node()
