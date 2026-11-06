"""Áp camera shake (core/shake.py) lên màn hình: camera thế giới và súng.

Rung chỉ đặt vào `camera.position/rotation` (tương đối so với `player.camera_pivot`). `Player.aim_ray()` đọc yaw/pitch/độ cao từ chính
`Player` chứ không đọc camera: tia ngắm, hướng đạn, độ tản và recoil không thấy rung. Chỉ ảnh dựng ra là rung.
Dấu đã đo bằng phép chiếu thật (tools/g6_shake_selftest.py kiểm lại): rotation_x dương = nhìn xuống, rotation_y dương = quay phải,
rotation_z dương = nghiêng phải (điểm bên phải màn hình đi LÊN).
"""
from ursina import camera

from fps.core.shake import Shake


class ShakeView:
    def __init__(self, shake: Shake, head=None):
        self.shake = shake
        self.head = head                 # core.headcam.HeadCam: chuyển động đầu + thân + liếc súng khi nạp, cũng thuần hình ảnh (Game.update gọi head.update trước apply)

    def apply(self, ads: float) -> tuple:
        """Đặt rung + chuyển động đầu lên camera thế giới; trả về tư thế cộng thêm cho súng (đưa vào Viewmodel.update, `visual`).
        Phần liếc súng của HeadCam đi theo `glance_follow` (~1) nên lúc cúi nhìn súng, súng đi lên giữa khung chứ không dính ống kính."""
        sh = self.shake
        camera_pose = sh.camera_pose(ads) if sh.active else (0.0,) * 6
        gun_pose = sh.gun_pose(ads) if sh.active else (0.0,) * 6
        if self.head is not None:
            camera_pose = tuple(a + b for a, b in zip(camera_pose, self.head.camera_pose()))
            gun_pose = tuple(a + b for a, b in zip(gun_pose, self.head.gun_pose()))
        x, y, z, pitch_up, yaw_right, roll_right = camera_pose
        camera.position = (x, y, z)
        camera.rotation = (-pitch_up, yaw_right, roll_right)
        return gun_pose
