"""Applies camera shake (core/shake.py) to the screen: world camera and gun.

Shake is applied only to `camera.position/rotation` (relative to `player.camera_pivot`). `Player.aim_ray()` reads yaw/pitch/height from the
`Player` itself, not from the camera: aim ray, bullet direction, spread and recoil do not see the shake. Only the rendered image shakes.
Signs measured with the real projection (tools/selftests/g6_shake_selftest.py re-checks them): rotation_x positive = looking down, rotation_y positive = turn right,
rotation_z positive = tilt right (the point on the right side of the screen goes UP).
"""
from ursina import camera

from fps.core.shake import Shake


class ShakeView:
    def __init__(self, shake: Shake, head=None):
        self.shake = shake
        self.head = head                 # core.headcam.HeadCam: head + body motion and glancing at the gun during reload; also image-only (Game.update calls head.update before apply)

    def apply(self, ads: float) -> tuple:
        """Sets shake + head motion on the world camera; returns the extra pose for the gun (fed to Viewmodel.update, `visual`).
        The glance part of HeadCam follows `glance_follow` (~1), so when looking down at the gun, the gun rises to the middle of the frame instead of sticking to the lens."""
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
