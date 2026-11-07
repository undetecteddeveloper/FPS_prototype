"""Turns all camera shake into motion of the LENS FRAME (Bodycam: the chest camera swims, the dark rim and the distortion centre travel with the image).

The world camera is NOT moved any more: `camera.position/rotation` stay at the player's view, and `Player.aim_ray()` reads yaw/pitch/height from the `Player`,
so the aim ray, bullet direction, spread and recoil never see the shake. The pose the camera would have had (core/shake.py: shots, reload beats; core/headcam.py:
body, steps, jump / landing, idle drift, the reload gaze) is summed here and converted by `core.lens.frame_shake` into a shift + tilt of the whole composited
image (world AND gun) inside assets/shaders/lens.frag. The gun is part of that image, so it moves with the frame: it gets no separate follow pose any more.
"""
from fps.core.headcam import HeadCam
from fps.core.lens import frame_shake, soft_limit
from fps.core.shake import Shake
from fps.weapon_data import LensData


class ShakeView:
    def __init__(self, shake: Shake, head: HeadCam = None, lens: LensData = None):
        self.shake = shake
        self.head = head
        self.lens = lens or LensData()

    def pose(self, ads: float) -> tuple:
        """Camera pose (x right, y up, z forward, pitch up, yaw right, roll right; metres, degrees) the frame should express this frame."""
        sh, d = self.shake, self.lens
        total = list(sh.camera_pose(ads)) if sh is not None and sh.active else [0.0] * 6
        if self.head is not None:
            for i, (m, g) in enumerate(zip(self.head.move_pose(), self.head.glance_pose())):
                total[i] += m + g * d.shake_glance
        return tuple(c * d.shake_scale for c in total)

    def frame_offset(self, ads: float, hfov: float, aspect: float, fisheye: float = 0.0) -> tuple:
        """(dx, dy, roll) for Lens.update. `hfov` = the SHOWN horizontal FOV (not the overscanned one). The old camera shake was seen through the fisheye, which
        magnifies the centre (1 + fisheye) times: the shift is multiplied by that so the centre of the frame swims as much as before; then it is softly limited to the overscan margin."""
        dx, dy, roll = frame_shake(self.pose(ads), hfov, aspect, self.lens.shake_pos_ref)
        k = 1.0 + fisheye
        margin = 0.9 * self.lens.overscan                     # never shift past the extra image drawn around the frame: no black band (only the round rim)
        return soft_limit(dx * k, margin), soft_limit(dy * k, margin), roll
