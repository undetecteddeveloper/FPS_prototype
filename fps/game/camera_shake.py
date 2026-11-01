"""Áp camera shake (core/shake.py) lên màn hình: camera thế giới và súng.

Rung chỉ đặt vào `camera.position/rotation` (tương đối so với `player.camera_pivot`). `Player.aim_ray()` đọc yaw/pitch/độ cao từ chính
`Player` chứ không đọc camera: tia ngắm, hướng đạn, độ tản và recoil không thấy rung. Chỉ ảnh dựng ra là rung.
Dấu đã đo bằng phép chiếu thật (tools/g6_shake_selftest.py kiểm lại): rotation_x dương = nhìn xuống, rotation_y dương = quay phải,
rotation_z dương = nghiêng phải (điểm bên phải màn hình đi LÊN).
"""
from ursina import camera

from fps.core.shake import Shake


class ShakeView:
    def __init__(self, shake: Shake):
        self.shake = shake
        self._applied = False            # camera đang lệch khỏi (0,0,0)

    def apply(self, ads: float) -> tuple:
        """Đặt rung lên camera thế giới; trả về tư thế cộng thêm cho súng (đưa vào Viewmodel.update)."""
        sh = self.shake
        if not sh.active:
            if self._applied:
                self._applied = False
                camera.position = (0, 0, 0)
                camera.rotation = (0, 0, 0)
            return (0.0,) * 6
        x, y, z, pitch_up, yaw_right, roll_right = sh.camera_pose(ads)
        camera.position = (x, y, z)
        camera.rotation = (-pitch_up, yaw_right, roll_right)
        self._applied = True
        return sh.gun_pose(ads)
