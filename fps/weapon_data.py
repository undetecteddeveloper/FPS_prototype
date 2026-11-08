"""Every tunable game parameter lives here (one place). Units: meters, seconds, degrees.

The debug panel (G6) will read/write these dataclasses; other modules only READ them, never set numbers themselves.
"""
from dataclasses import dataclass, field


@dataclass
class PlayerParams:
    # target speed per movement state (m/s)
    walk_speed: float = 4.5
    sprint_speed: float = 6.8
    crouch_speed: float = 2.2
    ads_speed_multiplier: float = 0.6     # multiplier on speed while aiming (used since G4)
    accel_ground: float = 45.0            # m/s^2
    accel_air: float = 6.0                # in the air, momentum is almost kept
    gravity: float = 22.0
    jump_speed: float = 6.4               # jump height = v^2 / 2g ≈ 0.93 m
    eye_height_stand: float = 1.68        # head camera: ~6 cm above the eyes
    eye_height_crouch: float = 1.20
    eye_height_change_speed: float = 4.0  # m/s when standing up / crouching down
    fov: float = 90.0                     # horizontal FOV of the image BEFORE the lens (user choice 8/11/2026, was 96); the fisheye lens magnifies the center ~1.25x, so the center looks narrower and the edges show more
    mouse_sensitivity: float = 45.0       # degrees turned when the mouse moves the full window HEIGHT (independent of resolution)
    pitch_limit: float = 89.0
    moving_speed_threshold: float = 0.5   # above this counts as "moving"
    ads_look_multiplier: float = 0.7      # multiplier on mouse sensitivity when fully aimed
    sprint_blocks_fire: bool = True       # pulling the trigger while sprinting: stop sprinting, lower the gun, then fire (sprint-to-fire). False: fire straight from the sprint pose
    land_dip_per_speed: float = 0.006     # m the camera dips per m/s of landing speed (falling at 6.4 m/s dips ~4 cm)
    land_dip_omega: float = 18.0          # rad/s
    land_dip_zeta: float = 0.5
    radius: float = 0.30                  # body circle for walls and columns (m)
    body_height: float = 1.70             # a solid box only pushes him while it overlaps the body from the feet up to here
    step_up: float = 0.20                 # the highest ledge he walks onto without jumping (pool steps 0.155 m, stairs 0.17 m)
    step_smooth: float = 14.0             # 1/s: after a step the camera catches up with the new height at this rate (no pop)


@dataclass(frozen=True)
class Clip:
    """One animation segment of the glb. Frames are counted at 30 fps on the file's shared timeline."""
    anim: str
    start: int
    end: int       # LAST valid frame (frame N of a clip with N frames is wrapped to 0, so N itself is not used)
    swap: int = None   # frame where the new magazine seats (measured with tools/measure/g5_reload_probe.py); reload clips only
    settle: int = None  # frame where the gun, magazine and bolt are back in place: the rest of the clip is only the hand re-folding its fingers (the reload view is switched off at this frame).
                        # Draw clips: the gun is up and still (measured: joints move < 0.5 cm per frame after it); firing / aiming are allowed from here while the tail plays on

    @property
    def duration(self) -> float:
        return (self.end - self.start) / 30.0

    @property
    def settle_time(self) -> float:
        """Seconds (clip time at speed 1) from the clip start to `settle`; None if there is none."""
        return None if self.settle is None else (self.settle - self.start) / 30.0

    @property
    def swap_time(self) -> float:
        """Seconds (clip time at speed 1) from the clip start to the magazine swap; None if there is none."""
        return None if self.swap is None else (self.swap - self.start) / 30.0


@dataclass
class RecoilData:
    """Random per-shot recoil (Bodycam style), no fixed pattern. Angles in degrees, TOTAL per shot; `camera_share` goes into the view
    (the player pulls the mouse to compensate), the rest makes the GUN drift off center (core/freeaim.py). Bullets leave the barrel, so both change the hit point."""
    up: float = 0.72                      # up per shot
    up_noise: float = 0.20                # ± random part of the up kick
    right_bias: float = 0.05              # average rightward bias per shot
    right_noise: float = 0.30             # ± random per-shot part of the sideways kick
    right_walk: float = 0.07              # random walk of the sideways bias per shot: each burst drifts differently
    right_walk_max: float = 0.30          # cap on the drifting sideways bias
    up_scale: float = 1.0                 # multiplier on the up part (debug panel: 2 = double, 0 = no upward kick)
    right_scale: float = 1.0              # multiplier on the sideways part
    camera_share: float = 0.30            # share of the kick going into the camera; the remaining 0.7 makes the gun drift
    ads_scale: float = 0.75               # aiming (stock to shoulder): kick multiplied by this
    crouch_scale: float = 0.85            # crouching: multiplied by this
    burst_reset_time: float = 0.35        # a pause longer than this resets the burst's sideways bias from the start
    kick_time: float = 0.025              # time constant (s) that smooths the kick: the camera does not jump within one frame
    recovery: float = 0.3                 # share of the camera kick that recovers after firing stops (0 = no recovery, 1 = full recovery)
    recovery_delay: float = 0.12          # how long after firing stops before recovery starts
    recovery_time: float = 0.18           # time constant (s) of the recovery curve


@dataclass
class AccuracyData:
    """MECHANICAL spread of gun + bullet (half cone angle, degrees). Inaccuracy while walking / running / kicking now comes from the barrel actually moving (bullets leave the barrel),
    so the state-based cone was removed (every state ~2 MOA = 0.03, still the Glock's numbers). 8/11/2026: the user tuned a per-state cone for the M4 on the F1 panel
    and these class defaults (= the M4) carry it; the Glock pins 0.03 in its own GunData."""
    stand: float = 1.0
    walk: float = 2.2
    sprint: float = 0.03
    air: float = 5.05                     # jump / fall
    crouch_multiplier: float = 0.8        # multiplier on the base when crouching
    ads: float = 0.1                     # aiming, standing still
    ads_move: float = 0.25                # aiming, moving
    bloom_per_shot: float = 0.0
    bloom_max: float = 4.0
    bloom_recovery: float = 6.0           # degrees/second
    bloom_recovery_delay: float = 0.15    # s after the last shot before recovery starts
    ads_bloom_multiplier: float = 0.05    # when fully aimed, bloom is reduced to this fraction


@dataclass
class GunKickData:
    """Gun kick on screen: a damped spring, each shot pushes an impulse. Smaller and faster than the camera recoil.

    The arrays are (x right, y up, z forward, pitch up, yaw right, roll right); meters and degrees.
    `peak` = peak deviation of ONE single shot; `random` = random ± amplitude added to each shot."""
    omega: float = 38.0                   # rad/s, natural frequency (period ~0.17 s)
    zeta: float = 0.55                    # <1: the gun bounces slightly before settling
    peak: tuple = (0.0, 0.004, 0.0, 0.7, 0.0, 0.0)      # z = 0: the push-back is handled by the separate spring below (this spring is fast, so one shot's peak does not pile up in full-auto fire)
    random: tuple = (0.002, 0.001, 0.0, 0.25, 0.25, 1.3)
    # PUSH-BACK (MW2): the gun is shoved toward the eye (negative z) and slides back. A SEPARATE spring, slower than the one above (period longer than the 0.08 s fire interval), so the
    # shots pile up: at 750 RPM one single shot pushes back 3.6 cm, the full magazine piles up to ~6 cm then saturates (when aiming, multiplied by back_ads_scale) (measured: tools/selftests/g3_selftest.py); after firing stops it returns in ~0.3 s.
    back_peak: float = -0.04             # m: peak of ONE single shot; negative = back toward the eye
    back_random: float = 0.003            # m: ± random per shot
    back_omega: float = 18.0              # rad/s (period ~0.35 s)
    back_zeta: float = 0.7
    back_ads_scale: float = 1.0          # when fully aimed the push-back is multiplied by this (1.3 = 30% MORE push-back than at the hip; visual only: the camera and bullet direction do not change)
    back_x_ratio: float = 0.3             # sideways shift along with the push-back (m sideways per m back; when the gun pushes back it shifts toward screen center, so it does not slide off the right edge). Hip only; 0 when aiming


@dataclass
class SwayData:
    """Gun sway on screen (the file has no Idle/Walk clips, so it is all done in code). Meters and degrees.
    Pose = (x right, y up, z forward, pitch up, yaw right, roll right), same as GunKick.peak."""
    # breathing while standing still: a 1:2 Lissajous path
    breath_freq: float = 0.28             # Hz
    breath_x: float = 0.0022
    breath_y: float = 0.0020
    breath_pitch: float = 0.22
    breath_yaw: float = 0.18
    # mouse lag (core/sway.py MouseLag): the gun follows the view through a second-order system, lagging by the turn VELOCITY; when the mouse stops it catches up, overshoots, and settles
    lag_gain: float = 0.055               # s: at a steady turn rate (deg/s) the gun lags by lag_gain * rate degrees (100 deg/s -> ~5 deg), linear region
    lag_max: float = 12.0                 # deg: asymptote of the steady lag under very fast turns (soft tanh compression, not a flat clamp); the peak of a flick is about this value
    lag_omega: float = 9.5                # rad/s: larger = the gun catches up faster (does not change the amplitude)
    lag_zeta: float = 0.62                # damping: smaller = more bounce (0.6 ~ 13% overshoot, 0.45 ~ 25%); 0.99 = no overshoot
    lag_roll: float = 0.9                 # roll in degrees per degree of yaw lag
    lag_pitch_scale: float = 0.8          # vertical lag (up/down) relative to the horizontal lag
    lag_shift: float = 0.0022             # m of horizontal/vertical shift per degree of lag (added to the arc motion from rotating around the eye)
    lag_deadzone: float = 12.0            # deg/s: below this (slow turns while aiming carefully) the gun is almost still
    lag_smooth: float = 0.02              # s: smoothing of the turn rate measured from the mouse (mouse input comes as discrete counts)
    lag_follow: float = 0.0               # 0 = fully lagging by the turn rate; 1 = the gun tracks closely, bouncing only when the rate changes
    # bob from footsteps (phase advances with distance travelled, so the rhythm is right at any speed)
    bob_stride: float = 2.4               # m travelled per left-right step cycle (when bob_rate = 1)
    bob_rate: float = 0.56                # bob rate relative to bob_stride when walking / crouch-walking (0.56: up 40% from 0.4; ~4.3 m per cycle)
    bob_sprint_rate: float = 0.483        # bob rate when sprinting (0.3 -> 0.42 up 40%, then +15% more: ~2.8 steps/s)
    bob_x: float = 0.0070
    bob_y: float = 0.0100
    bob_pitch: float = 1.0
    bob_roll: float = 1.1
    bob_sprint_multiplier: float = 1.8
    bob_crouch_multiplier: float = 0.6
    bob_min_speed: float = 1.5            # m/s: below this the bob amplitude shrinks to 0
    bob_blend: float = 10.0               # 1/s: amplitude slides to the new level; stopping abruptly does not jerk
    # hip rest pose: low and near the middle of the frame, not aimed. Added to hip_offset; blends to 0 when aiming
    rest_pose: tuple = (-0.050, -0.112, 0.020, 0.0, 0.0, -3.0)
    # sprint pose, ADDED to rest_pose and blended by player.sprint_amount: the gun drops below the camera and out of the frame (user 7/11/2026), pulled back a little and the muzzle tipped down.
    # Measured on both guns (rear sight, front sight, muzzle): >= 55 deg below the view axis, the frame's bottom edge is at 30 deg, so lens shake / bob (<= ~10 deg) never bring it back
    sprint_pose: tuple = (-0.01, -0.30, -0.10, -25.0, -16.0, 10.0)
    # G14 High Ready (core/weaponcol.py), ADDED to rest_pose and blended by the wall raise amount: the barrel points up at the ceiling. The pitch turns the gun about the EYE, so the shift
    # brings the receiver (rear sight) back to where the hands are at rest, 3 cm lower and 4 cm closer (the M4's numbers; the Glock sits 0.15 m farther out, see GLOCK; solved in tests/test_weaponcol.py)
    wall_pose: tuple = (0.0, -0.175, 0.043, 65.0, 0.0, 0.0)
    # inertia from vertical camera motion (jump, crouch, stand up, fall)
    vlag_gain: float = 0.05
    vlag_max: float = 0.03                # m
    jolt_omega: float = 14.0
    jolt_zeta: float = 0.6
    land_peak: tuple = (0.0, -0.012, -0.008, -1.5, 0.0, 0.0)   # peak deviation on landing at 6.4 m/s (scales with speed)
    land_reference_speed: float = 6.4
    # aiming: everything above (breathing, lag, bob, inertia) is multiplied by this when fully aimed
    ads_multiplier: float = 0.45


@dataclass
class ReloadData:
    """Draw (unholster) and reload (Reload / Reload_Empty). Timings come from the file's clips, multiplied by `speed`."""
    speed: float = 1.0                    # multiplies the reload clip speed: 1 = the original clip (3.6 s with rounds / 3.8 s empty); 1.5 gives ~2.4 s / 2.5 s
    draw_speed: float = 1.0
    sprint_cancels: bool = True           # sprinting cancels the reload (CoD style); False: keep reloading, the sprint pose is layered on top
    cancel_blend: float = 0.18            # s: the gun slides from the reloading pose back to ready when cancelled
    bolt_lock_blend: float = 0.04         # s: the bolt snaps back (locks open) after the last round of the magazine
    # The reload clip is built for a wider view: the left hand and magazine sit below the bottom edge at the hip FOV (70). While reloading, the gun's own FOV
    # widens and the gun rises, blending in/out over `view_blend` seconds (measured from screenshots in tools/selftests/g5_selftest.py)
    view_fov: float = 92.0
    # (x right, y up, z forward, pitch up, yaw right, roll right), m and degrees. y 0.125 -> 0.105 after adding the gun glance (HeadCamData.glance_*): the head tilts down 18 degrees
    # and the gun follows, so the magazine at the swap (measured on the model: 27-32 degrees below the eye, ~30 cm ahead) sits ~12-16 degrees below screen center, the gun body just below center
    view_pose: tuple = (0.07, 0.0, -0.02, 0.0, 0.0, 2.5)
    view_blend: float = 0.25
    # The clip keeps playing for 0.5-0.75 s after the gun, magazine and bolt are back (`Clip.settle`): only the hands settling. Shooting / aiming / swapping / reloading again are allowed
    # from `Clip.settle` minus this many seconds (never before the new magazine is seated); the tail plays on and a shot cuts it. 0 = at settle; larger = earlier (a Glock shot
    # that early snaps the left hand to the fire clip: a pop of several cm)
    ready_lead: float = 0.0


@dataclass
class ViewLightData:
    """Gun + hand materials (assets/shaders/viewmodel.*). NO separate light: the gun receives the same ceiling lamps, shadows, ambient light and muzzle flash as the world."""
    specular: float = 0.55                # metallic sheen of the gun body (highlights from the ceiling lamps)
    gloss: float = 26.0                   # how concentrated the highlight is on the gun body
    env: float = 0.35                     # faint environment reflection (multiplied by the local ambient light: it vanishes in dark spots)
    normal_strength: float = 1.0          # strength of the normal map
    albedo: float = 1.25                  # multiplies the texture color: the gun texture is very dark and would lose all detail through the harsh tone curve
    skin_color: tuple = (0.58, 0.37, 0.27)      # bare skin of the Hand_D material (fingers and forearm outside the gloves); was a near-black "sleeve" until 8/11/2026, which read as black hands
    skin_detail: float = 0.45                     # 0 = flat skin colour shaded by the texture's light / dark, 1 = the texture's own colours (the file's forearm has a twisted pattern)


@dataclass
class FlashData:
    """Muzzle flash: ONLY a short point light at the muzzle that lights the gun, hands and ground (no visible flame card: the visible part of a shot is the smoke, SmokeData).
    It lives `life` seconds then fades (at 750 RPM the shots overlap into a continuous flicker)."""
    life: float = 0.055                   # s
    forward: float = 0.025                # m: the light sits this far in front of the muzzle
    light_color: tuple = (1.0, 0.62, 0.28)
    light_power: float = 1.5              # multiplies the light color at its brightest
    light_attenuation: tuple = (1.0, 0.0, 40.0)   # unused since the gun got its own flash light (gun_falloff below); kept so saved params still load
    gun_lift: float = 0.14                # m: the flash light on the gun sits this far above the muzzle (the gun's visible faces look up / back, not forward)
    gun_back: float = 0.22                # m: ... and this far back toward the camera
    gun_wrap: float = 0.5                 # diffuse wrap: 0 = only faces turned to the light, larger = also the sides and the far side
    gun_falloff: float = 7.0              # 1 / (1 + falloff * d^2) on the gun: half strength at ~0.38 m
    world_power: float = 3.5              # flash brightness on walls / floor (0 = only lights the gun)
    world_falloff: float = 0.22           # 1 / (1 + falloff * d^2): half strength at ~2 m


@dataclass
class TracerData:
    """Tracer: a light streak that follows the real bullet (same position, same drop), starting at the muzzle and converging onto the bullet path from the eye."""
    every: int = 2                        # one tracer every N rounds (1 = every round); the first round of a burst always has one
    burst_reset: float = 0.30             # a pause longer than this (s) starts a new burst: counting restarts from the first round
    max_range: float = 600.0              # m: past this distance the streak stops following the bullet (a bullet flying up lives 3 s, but needs no streak chasing it)
    length: float = 7.0                   # m: streak length (a 500 m/s bullet travels ~8 m per frame at 60 FPS; shorter becomes separate dots)
    width: float = 0.05                   # m: width near the camera
    min_pixels: float = 2.2               # minimum width on screen (far away a tracer thinner than 1 pixel would flicker)
    glow_pixels: float = 20.0             # the streak head has a bright dot facing the camera, this size on screen (when a bullet flies far along the view direction the streak shrinks to a dot)
    glow_color: tuple = (1.0, 0.62, 0.18)
    blend_distance: float = 18.0          # m: distance at which the streak no longer deviates from the real bullet path (deviation = muzzle vs. eye)
    head_color: tuple = (1.0, 0.86, 0.45)   # additive blending onto bright backgrounds needs saturated colors; white would sink into the road surface and sky
    tail_color: tuple = (1.0, 0.36, 0.06)
    intensity: float = 1.0
    pool: int = 16                        # max streaks at once


def _m4_reload_beats() -> dict:
    """Reload shake beats, by clip frame (measured with tools/measure/g5_reload_probe.py): old magazine drops out, new magazine seats (= Clip.swap), bolt releases.
    Frames count on the file's shared timeline; Handling.frame already multiplies by ReloadData.speed, so the beats land correctly at any reload speed."""
    return {
        'reload': ((27, 'mag_out'), (61, 'seat')),
        'reload_empty': ((137, 'mag_out'), (172, 'seat'), (190, 'bolt')),
    }


def _beat_peaks() -> dict:
    # peak camera deviation for ONE beat: (x right, y up, z forward, pitch up, yaw right, roll right), meters and degrees. Gentle: at most ~0.2 degrees, ~2 mm
    return {
        'mag_out': (0.0, -0.0004, 0.0, -0.06, 0.03, 0.10),
        'seat': (0.0, -0.0010, -0.0012, -0.20, 0.05, 0.22),
        'bolt': (0.0, 0.0005, -0.0020, 0.15, 0.06, 0.18),
    }


@dataclass
class ShakeData:
    """Camera shake: purely visual shake (does not change bullet direction), see core/shake.py. Meters and degrees."""
    seed: int = 7
    # firing: EACH SHOT is one camera kick (spring impulse) with random strength and direction; the gun heats up while firing, kicking harder and shaking more
    # peak deviation of one shot (spring at rest, strength 1) = fire_bias + fire_spread x a signed random number in [-1, 1], per axis (x, y, z, pitch, yaw, roll)
    fire_bias: tuple = (0.0, 0.0, -0.003, 1.0, 0.0, 0.0)              # fixed part: back 3 mm, pitch up 1 degree
    fire_spread: tuple = (0.0015, 0.0015, 0.0015, 0.30, 0.55, 2.0)    # random ± part: roll up to 2 degrees is the most visible channel (the camera recoil has no roll)
    direction_shape: float = 0.6          # exponent of the random part (< 1: few shots near 0; yaw / roll usually lean to one side)
    strength_var: float = 0.4             # strength of a shot = 1 ± this (0.6 .. 1.4)
    strength_shape: float = 0.7           # < 1: more shots are clearly strong or clearly weak than medium
    fire_omega: float = 38.0              # rad/s: spring of the kick; peaks after ~0.03 s, ~25% left after one 0.08 s interval so bursts pile up moderately
    fire_zeta: float = 0.45               # bounces back slightly, then settles in ~0.15 s
    fire_scale: float = 1.0               # multiplies ALL shake while firing (kick + hand tremor, camera + gun, also when aiming); reload shake is not multiplied
    # heating: heat 0..1 of the burst
    heat_shots: float = 25.0              # consecutive shots to fully heat up (each shot adds 1 / this)
    heat_hold: float = 0.12               # s: the gun only cools after a pause longer than this (> the 0.08 s interval, so heat does not drop mid-burst)
    heat_cool: float = 3.0                # /s: cools from 1 to 0 in 0.33 s (after heat_hold)
    heat_boost: float = 1.2               # kick multiplied by 1 + this x heat. Peak over a full magazine / peak over 30 single shots (average of 10 seeds): pitch 1.9, roll 2.0
                                          # (1.0 only gives ~1.8 because the peak of 30 single shots is already the strongest random shot)
    tremor_amp: tuple = (0.0006, 0.0006, 0.0004, 0.25, 0.30, 0.60)   # base hand tremor when fully hot (x, y, z, pitch, yaw, roll), multiplied by heat
    tremor_freq: float = 22.0             # Hz: the tremor is clearly faster than the fire rate (12.5 Hz)
    # reload: spring impulses at the clip's beats, not continuous shaking
    reload_beats: dict = field(default_factory=_m4_reload_beats)    # clip key -> ((frame, beat type), ...)
    beat_peaks: dict = field(default_factory=_beat_peaks)          # beat type -> peak deviation
    beat_omega: float = 42.0              # rad/s (period ~0.15 s)
    beat_zeta: float = 0.45               # bounces 1-2 times, then settles in ~0.15 s
    # when fully aimed the shake drops to this
    ads_multiplier: float = 0.5
    # the on-screen gun follows the world (sign flipped) by this amount and lags by `gun_delay` seconds: the gun shakes less and lags slightly behind the world, which looks more natural
    gun_follow: float = 0.6
    gun_delay: float = 0.02


@dataclass
class FreeAimData:
    """The gun does not return to one fixed point on screen (core/freeaim.py). Bullets leave the barrel. Degrees and meters."""
    barrel_aim: bool = True               # True: bullets follow the barrel and the mouse moves the gun first; False: the mouse turns the screen directly and bullets leave from the center (selftests measuring drop / when a comparison is needed)
    # FREE ZONE (core/freeaim.py FreeLook): the mouse moves the GUN inside an ellipse around the screen center; the screen only turns once it reaches the edge.
    # Values chosen by me: no public source gives Bodycam's numbers (a Garry's Mod mod uses 45 / 30 degrees, too wide for this screen)
    zone_yaw: float = 15.0                # deg: half-width of the free zone
    zone_pitch: float = 9.0               # deg: half-height
    zone_soft: float = 0.70               # from this fraction of the zone radius outward the screen starts turning gradually (no hard jolt at the edge)
    zone_ads: float = 0.20                # when fully aimed the zone shrinks to this: the sight moves toward the center, the screen turns to compensate so the aim point does not jump
    zone_sprint: float = 0.35             # when sprinting
    zone_reload: float = 0.50             # when reloading
    zone_blend: float = 0.14              # s: smooth shrink / grow of the zone
    recenter_idle: float = 0.22           # /s: standing still, the head slowly turns toward the gun (the gun keeps its world direction; only the frame catches up)
    recenter_move: float = 1.0            # /s: while walking the body turns toward the gun faster
    hand_omega: float = 15.0              # rad/s: the hand moves the gun with the mouse, without sticking rigidly to it
    hand_zeta: float = 0.85
    offset_roll: float = 0.22             # gun roll per degree of horizontal offset
    offset_shift: float = 0.0016          # m the gun shifts on the frame per degree of offset (added to the arc around the eye)
    drift_omega: float = 7.0              # rad/s: the gun drifts back from the kick on this spring (smaller = slower return, shots pile up)
    drift_zeta: float = 0.95
    drift_max: float = 9.0                # deg: the drift approaches this level after very long firing (soft compression)
    rest_yaw: float = 0.8                 # deg: after each turn / burst, the rest pose is random within ± this (it does not return to one exact coordinate)
    rest_pitch: float = 0.6
    rest_roll: float = 2.2
    rest_pos: float = 0.007               # m
    rest_time: float = 0.55               # s: time to slide to the new rest pose
    rest_turn_threshold: float = 60.0     # deg/s: turning faster than this picks a new rest pose when stopping
    idle_yaw: float = 0.32                # deg: slow drift while standing still (the hand is not rigid like a tripod)
    idle_pitch: float = 0.26
    idle_roll: float = 0.45
    idle_freq: float = 0.22               # Hz
    ads_scale: float = 0.30               # when fully aimed: rest drift + slow drift are reduced to this (the kick part is kept)


@dataclass
class HeadCamData:
    """Head camera (core/headcam.py): VISUAL ONLY, does not change the aim ray. Degrees and meters."""
    seed: int = 23
    turn_roll: float = 0.016              # roll in degrees per deg/s of horizontal turn (the head tilts with the turn)
    turn_roll_max: float = 4.5
    strafe_roll: float = 0.55             # roll in degrees per m/s of sideways movement
    move_pitch: float = 0.20              # pitch down in degrees per m/s of forward movement
    turn_yaw_lag: float = 0.008           # s: the frame lags slightly behind a turn (the body arrives late)
    body_omega: float = 8.0               # rad/s: body spring: smaller = the body arrives later
    body_zeta: float = 0.75
    # footsteps when WALKING (same phase as Sway.phase, i.e. same rhythm as the footstep sounds). Bodycam-style sway: visible but not nauseating
    step_y: float = 0.012                 # m: bob (-40 % for walking, user 7/11/2026) (the -2 cm trough lands exactly when the foot touches the ground; the peak is lower because the trough is sharp)
    step_x: float = 0.006                 # m: sideways sway with the supporting leg
    step_roll: float = 0.66               # deg: left-right roll with the step rhythm
    step_pitch: float = 0.42              # deg: nod with each step
    step_yaw: float = 0.24                # deg: head turns with the shoulders
    step_sharp: float = 0.6               # 0 = sine bob; 1 = sharp trough like a stomp
    step_crouch: float = 0.55             # crouch-walking: multiplies the step amplitude + hand shake
    step_min_speed: float = 1.5           # m/s: below this the amplitude shrinks to 0
    step_blend: float = 8.0               # 1/s: amplitude slides to the new level
    # sprinting: its own amplitude set (blended smoothly with the walk set by `sprint_blend`)
    sprint_y: float = 0.021               # sprint set: -30 % (user 7/11/2026)
    sprint_x: float = 0.0112
    sprint_roll: float = 1.82             # deg: strong left-right roll with the step rhythm
    sprint_pitch: float = 0.91
    sprint_yaw: float = 0.63
    sprint_lean: float = 1.5              # deg: extra forward lean (added to move_pitch by speed)
    sprint_blend: float = 5.0             # 1/s
    # high-frequency hand / machine vibration: smooth noise, grows with speed, strongest when sprinting
    jitter_angle: float = 0.35            # deg (pitch; yaw x0.8; roll x1.2) when sprinting (-30 %)
    jitter_pos: float = 0.00105           # m
    jitter_walk: float = 0.257            # walking: this much remains (keeps walking at -40 %: 0.35 x 0.257 = 0.6 x 0.5 x 0.3)
    jitter_freq: float = 12.0             # Hz when sprinting
    jitter_freq_walk: float = 7.0         # Hz when walking
    idle_pitch: float = 0.22              # deg: head drifts slowly while standing still
    idle_yaw: float = 0.22
    idle_roll: float = 0.32
    idle_y: float = 0.0025                # m: breathing
    idle_freq: float = 0.17               # Hz
    # jump / fall / landing: impulses into the fast `jolt_*` spring (zeta < 0.5, so it bounces back once); peaks are set at reference speed and scale with speed
    jump_pitch: float = 1.6               # deg: pitch up at jump takeoff
    jump_y: float = 0.008                 # m
    jump_roll: float = 0.6                # deg: ± random
    air_sway: float = 0.5                 # deg: slow sway while airborne
    air_freq: float = 1.4                 # Hz
    land_pitch: float = 4.0               # deg: dip down on landing at reference speed
    land_y: float = 0.025                 # m: dip down (added to the real landing bob of Player._dip)
    land_roll: float = 1.4                # deg: ± random roll (yaw ± 30% of this)
    land_reference_speed: float = 6.4     # m/s fall speed matching the peak above (= jump takeoff speed)
    land_max: float = 1.8                 # falls higher than this are capped at this many times the reference
    jolt_omega: float = 14.0              # rad/s
    jolt_zeta: float = 0.40
    ads_multiplier: float = 0.5           # fully aimed: head motion reduced to this (does not apply to the gun glance)
    gun_follow: float = 0.55              # the gun follows head motion (sign flipped) by this much: the hand is attached to the body, not stuck to the lens
    # GUN GLANCE WHILE RELOADING: the head tilts down to look at the magazine, then comes back up, timed to the clip (visual only; the mouse still turns and the aim ray does not change).
    # 18 deg down + the gun following at 1 brings the magazine at the swap (~30 deg below the eye) to the lower middle of the frame (measured on the model, see ReloadData.view_pose)
    glance_pitch: float = 18.0            # deg: pitch down
    glance_yaw: float = 6.0               # deg: turn toward the gun (the gun is offset to the right)
    glance_roll: float = 3.0              # deg: roll along
    glance_y: float = -0.015              # m: when the head tilts down the eye drops
    glance_z: float = 0.015               # m: and moves forward
    glance_in_delay: float = 0.06         # s after pressing reload before the head starts to tilt down
    glance_in_time: float = 0.45          # s to fully tilt down (eased by gaze_enter_ease)
    glance_out_lead: float = 0.7         # s BEFORE Clip.settle the head starts to come up (so the slow look-up ends before the clip does)
    glance_out_time: float = 1.0         # s to fully come up (eased by gaze_leave_ease; user choice 0.7 s)
    glance_cancel_time: float = 0.2       # s: when reloading is cancelled the head comes back within this time
    glance_drift: float = 1.0             # deg: the eye drifts slightly while looking
    glance_drift_freq: float = 0.5        # Hz
    glance_seat_nod: float = 1.2          # deg: small nod when the magazine seats (Clip.swap)
    glance_follow: float = 1.0            # the gun follows the glance part (sign flipped): 1 = the gun stays still relative to the body and moves up to the middle of the frame on screen
    # GAZE while reloading (core/gaze.py): the look jumps between what the hands work on (saccades), rests, follows the hand slowly; each reload a little different
    gaze_hand_weight: float = 0.85        # 0 = look at the gun, 1 = look at the left hand (it carries the magazine); the target is the point in between
    gaze_threshold: float = 4.0           # deg: the target must move this far from where the gaze rests before the next glance
    # a HEAD glance is slow (eye saccades are 3-4x faster; see .claude/skills/camera-easing-bezier): 0.3 s + 0.012 s per degree, i.e. ~0.4 s for 8 deg
    gaze_time: float = 0.4               # s: base duration of a glance
    gaze_time_per_deg: float = 0.012      # s per degree of glance amplitude
    gaze_overshoot: float = 0.0           # extra overshoot of the glance target (the settle now lives in gaze_glance_ease)
    gaze_dwell_min: float = 0.60          # s: the gaze rests at least this long on a point ... (user choice: 2-3 points per reload, ~0.7 s each)
    gaze_dwell_max: float = 0.85          # s: ... and at most this long before it may jump again
    gaze_pursuit: float = 0.8             # 1/s: while resting, the gaze creeps toward the moving hand at this rate (slow: a rest must look like a rest)
    # cubic-bezier (x1, y1, x2, y2) like CSS: x = time, y = progress; x1, x2 in [0, 1], y may leave [0, 1] to overshoot (core/easing.py)
    gaze_enter_ease: tuple = (0.45, 0.0, 0.20, 1.0)     # the first dip: slow start, firm middle, soft landing
    gaze_glance_ease: tuple = (0.40, 0.0, 0.30, 1.04)   # glance between two points: eases in and settles with a 4% overshoot
    gaze_leave_ease: tuple = (0.45, 0.0, 0.15, 1.0)     # looking back up: slow start, long soft landing
    gaze_jitter: float = 0.0             # +- share: each reload draws its own depth, tempo and a side offset (x8 deg)
    gaze_max_yaw: float = 14.0            # deg: the gaze never turns further sideways than this


@dataclass
class SmokeData:
    """Gunpowder smoke (maths: core/smoke.py, drawing: game/smoke.py): soft white puffs that live in the WORLD (walking on leaves them behind).
    Each shot blows `puffs` puffs out of the muzzle along the barrel and `port_puffs` smaller ones out of the ejection port; the air brakes them quickly
    (velocity relative to the wind decays as exp(-drag t)), warm gas rises a little, they swell and fade within about `life` seconds; a puff that reaches the ground spreads sideways."""
    puffs: int = 5                        # muzzle puffs per shot
    speed: float = 9.0                    # m/s: muzzle puff speed along the barrel
    speed_jitter: float = 0.35            # +- random ratio of the speed per puff
    cone: float = 14.0                    # deg: random spread of the puff direction around the barrel axis
    drag: float = 7.0                     # 1/s
    rise: float = 0.35                    # m/s^2: buoyancy of the warm gas
    turbulence: float = 0.30              # m/s: random drift added per puff (smooth, not per frame)
    life: float = 1.0                     # s: a puff is gone after this (+- life_jitter)
    life_jitter: float = 0.30             # +- ratio
    size: float = 0.05                    # m: radius at birth
    growth: float = 0.45                  # m: radius added by the end of life (grows like sqrt(age))
    opacity: float = 0.42                 # peak opacity of one puff
    color: tuple = (0.55, 0.56, 0.57)     # lit by the sun / sky like the ground: shows as a pale grey-white (pure white smoke vanishes on the white ground)
    ground_spread: float = 0.6            # hitting the ground: this share of the downward speed turns into outward speed along the ground
    port_puffs: int = 2                   # ejection-port puffs per shot (0 = none)
    port_speed: float = 1.2               # m/s
    port_size: float = 0.03               # m
    port_opacity: float = 0.22
    ejection_port: tuple = (0.088, -0.060, 0.25)   # port position in the camera frame at rest, like `muzzle` (hip_offset not included); None = no port smoke.
    #                                                the default is the M4's: right side of the receiver behind the handguard (estimated from the model: ~2 cm right of the bore, 25 cm from the eye)
    port_dir: tuple = (0.55, 0.83, 0.0)   # puff direction out of the port, camera frame (x right, y up, z forward)


@dataclass
class WallData:
    """G14 weapon collision, 'High Ready' (core/weaponcol.py): standing too close to a wall, the gun points at the ceiling (SwayData.wall_pose), the more the closer the wall;
    firing and aiming are locked while it is up (reloading still works). Distances are in units of the gun's reach (eye -> muzzle at rest: M4 0.78 m, Glock 0.60 m)."""
    clear_ratio: float = 1.12             # the gun starts to rise when the wall is closer than this x reach
    full_ratio: float = 0.52              # fully raised when closer than this x reach (the body stops 0.30 m from a wall: M4 full at 0.41 m, Glock at 0.31 m, so a wall you walk into is always fully up)
    side_angle: float = 18.0              # deg: two more probe rays to each side of the view direction (an oblique wall, a corner)
    in_time: float = 0.16                 # s to raise
    out_time: float = 0.30                # s to lower again after stepping back
    block_at: float = 0.30                # firing / aiming are locked from this share of the raise ...
    block_hysteresis: float = 0.10        # ... and released below block_at - this (the trigger does not flicker at the threshold)
    blocked_text: str = 'Quá sát tường'   # the small line at the bottom when the trigger is pulled while locked
    blocked_time: float = 0.9             # s the line stays


@dataclass
class GunData:
    """Data for one gun. Adding a second gun = adding one GunData, no logic changes."""
    name: str
    glb: str
    credit: str
    clips: dict
    recoil: RecoilData = field(default_factory=RecoilData)
    accuracy: AccuracyData = field(default_factory=AccuracyData)
    kick: GunKickData = field(default_factory=GunKickData)
    sway: SwayData = field(default_factory=SwayData)
    reload: ReloadData = field(default_factory=ReloadData)
    view_light: ViewLightData = field(default_factory=ViewLightData)
    flash: FlashData = field(default_factory=FlashData)
    tracer: TracerData = field(default_factory=TracerData)
    shake: ShakeData = field(default_factory=ShakeData)
    free_aim: FreeAimData = field(default_factory=FreeAimData)
    head: HeadCamData = field(default_factory=HeadCamData)
    smoke: SmokeData = field(default_factory=SmokeData)
    wall: WallData = field(default_factory=WallData)      # G14 High Ready near a wall
    # aiming (ADS)
    ads_time: float = 0.19                # s to go in / out
    ads_fov: float = 84.5                 # horizontal world FOV when fully aimed: with the lens distortion reduced (LensData.fisheye_ads), the center is magnified ~13%
    ads_view_fov: float = 74.0            # FOV of the gun-drawing camera when fully aimed: the sight is large enough to use (bullets still go where the front sight points, see freeaim.barrel_view_dir)
    ads_sights: tuple = None              # (center of the rear aperture, top of the front post) in the camera frame at rest, NOT including hip_offset
    ads_eye_relief: float = 0.18          # m: distance from the eye to the rear aperture when aiming (farther: smaller aperture, less occlusion)
    muzzle: tuple = None                  # muzzle in the camera frame at rest, like ads_sights (measured with tools/measure/g5_muzzle_align.py)
    # sprinting
    sprint_in_time: float = 0.20          # s to lower the gun into the sprint pose
    sprint_out_time: float = 0.25         # s to raise the gun again; firing is not possible during this time (sprint-to-fire)
    # gunshot sound
    shot_sound: tuple = ()                # paths from the project root (several variants, played in rotation); built with tools/build/prep_elevenlabs.py from assets/sounds/source/elevenlabs
    shot_volume: float = 0.8
    shot_pool: int = 8                    # number of rotating playback copies: sound length (0.5 s) / fire interval (0.08 s) + 1, so a later sound does not cut off the previous one
    shot_pitch_variation: float = 0.03    # ± random pitch change ratio per shot to avoid a "machine" sound; 0 = off
    eye_joint: str = 'FPS_Camera_j_01'    # joint where the animation's original view places the camera
    model_scale: float = 0.01             # the file is in cm
    view_fov: float = 92.0                # horizontal FOV of the gun-drawing camera: close to the world FOV so the gun is at true scale relative to the room
    hip_offset: tuple = (0.0, 0.0, 0.0)   # extra viewmodel offset from the original view (x right, y up, z forward)
    # firing
    rpm: float = 750.0                    # rounds per minute
    magazine: int = 30
    reserve: int = 600
    full_auto: bool = True                # mode at game start (key B toggles auto / semi)
    # bullet drop: ~0.11 m at 75 m and ~0.44 m at 150 m
    muzzle_velocity: float = 500.0        # m/s
    bullet_gravity: float = 9.81          # m/s^2
    bullet_lifetime: float = 3.0          # s; past this the bullet is removed (it flew out of the lane)
    # per-gun model / animation hooks; the defaults keep the M4 behaviour
    ready_pose: tuple = None              # (anim, frame) of the ready pose (bolt closed); None = last frame of the 'draw' clip (M4)
    locked_pose: tuple = None             # (anim, frame) of the pose with the slide/bolt locked open (empty magazine); None = first frame of 'reload_empty' (M4)
    mag_nodes: tuple = None               # (glob of the magazine nodes seated in the ready pose, glob of those seated in the locked-slide pose); each state draws only its own. None = the M4 logic (Mag2 + bullet stay hidden)
    fire_clips: tuple = ()                # (clip key of a normal shot[, clip key of the last round]); played on every shot. () = no shot clip (the M4 kicks in code only)
    fire_clip_speed: float = 1.5          # play rate of the shot clip (the clip is slower than the fire interval at full rate)
    materials: dict = None                # material name -> (specular, gloss, env, albedo) multipliers of ViewLightData; None = the M4 table in game/viewmodel.py
    sound_cues: dict = None               # clip key -> tuple of SoundCue; None = AudioData.cues (M4)
    sound_files: dict = None              # extra logical sound name -> file group in AudioData.folder, merged into AudioData.sound_files


M4 = GunData(
    name='M4',
    glb='assets/guns/m4_-_fps_weapon_animations_pack_v.1.glb',
    credit='M4: BarcodeGames (CC BY 4.0)',
    clips={
        # swap = frame where the new magazine seats (with rounds left: old magazine drawn out, new one pressed in at 2.0 s; empty: 2.03 s, bolt released at frame 190)
        'reload': Clip('Reload', 1, 110, swap=61, settle=88),
        'reload_empty': Clip('Reload_Empty', 111, 224, swap=172, settle=206),
        'fire': Clip('Fire', 226, 249),
        'holster': Clip('Holster', 251, 268),
        'draw': Clip('Draw', 269, 299, settle=291),
    },
    # measured from the model's peaks (tools/measure/g4_ads_align.py): center of the rear aperture and top of the front post
    ads_sights=((0.0678, -0.0074, 0.1556), (0.0678, -0.0069, 0.5622)),
    muzzle=(0.0677, -0.0752, 0.7326),
    shot_sound=('assets/sounds/m4_shot_new.wav',),
    shot_pool=24,                          # the new shot is 2.56 s long (reverb tail): a copy comes round again after 24 x 80 ms = 1.9 s
)


@dataclass
class FeedbackParams:
    """Feedback on bullet hits: bullet holes (core/holes.py, game/decals.py, assets/shaders/decal.*)."""
    hole_base_size: float = 0.28          # m: width of the whole decal (crater ~8 cm, flaked glaze ~13 cm, cracks out to ~25 cm: readable from 5-10 m); a real 5.56 mm hole is far smaller, so it is enlarged
    hole_size_per_meter: float = 0.002    # holes grow with distance (150 m: ~0.35 m)
    max_holes: int = 64                   # past this, the oldest hole is reused (a full-auto M4 makes 12.5 holes/s, each lives hole_life: ~19 alive at most)
    hole_life: float = 1.5                # s a hole stays (user's choice 8/11/2026: gone quickly, the mesh is hidden while no hole is alive)
    hole_fade: float = 0.4                # s at the end of its life over which the hole fades out


@dataclass
class LookData:
    """Visual look of the world (shaders assets/shaders/room.*, water.*, world.*) and the screen overlay. Directions are in world space (y up, z forward).
    The pool hall (G9) is lit by a LOW GOLDEN SUN through its windows: the hard-edged patches are baked once (core/lightbake.py) from `sun_dir` / `sun_color` / `sky_irradiance`,
    so changing those three needs `tools/build/bake_pool.py` (the game re-bakes by itself when the stored hash differs). The ambient terms still light the gun, the bullet holes and the flat map."""
    sun_dir: tuple = (0.93, 0.125, -0.30)     # direction TOWARD the sun (normalized in code): very low (~7 degrees) over the east windows, so the beams cross the 20 m room and reach the west wall and the columns
    sun_color: tuple = (1.60, 1.10, 0.50)     # sunlight colour x intensity (golden hour: orange-gold, not white)
    sky_irradiance: tuple = (0.74, 0.92, 1.18)    # light the open sky sends in through the windows (used only by the bake: rays that leave through a window)
    ambient_up: tuple = (0.27, 0.27, 0.26)    # indoor ambient on upward-facing surfaces (gun, bullet holes, flat map)
    ambient_down: tuple = (0.13, 0.11, 0.08)  # light bounced from the floor onto downward-facing surfaces
    exposure: float = 1.7                     # multiplies the auto exposure (LensData); the ACES tone curve is shared by the world and the gun (G9: 1.0 -> 1.7, the baked hall is lit by low sun only)
    fog_color: tuple = (0.62, 0.74, 0.86)     # haze, also the sky colour seen through the windows
    fog_density: float = 0.0015               # exp: ~4% at 30 m (indoors the haze must stay faint)
    wind: tuple = (0.6, 0.0, 0.25)            # m/s: light steady wind (x right, y up, z forward of the spawn view); the gun smoke drifts with it
    ground_color: tuple = (1.0, 1.0, 1.0)     # pure white ground (decided by the user)
    detail_strength: float = 0.0              # strength of the noise on the ground (0 = plain, one flat colour)
    # surface detail of the pool hall's tiles (assets/textures/tile_*; F2 'Chi tiết bề mặt' picks flat / normal map / parallax)
    tile_depth_floor: float = 0.006           # m: how deep the grout joints of the deck look (parallax); the relief's normals were baked for this much (tools/build/surface_textures.py TILE_DEPTH_FLOOR)
    tile_depth_wall: float = 0.003            # m: the same for the wall mosaic and the pool basin tiles
    tile_bump: float = 1.0                    # strength of the tiles' normal map (0 = flat, 2 = twice the baked slope)
    # a thin grid on the ground: on a plain white floor there is nothing to show that the player is moving
    grid_strength: float = 0.85               # how dark the lines are (0 = no grid)
    grid_spacing: float = 2.0                 # m between two thin lines
    grid_major: int = 5                       # every this many lines one is drawn heavier (5 x 2 m = a 10 m square)
    grid_width: float = 0.03                  # m: half the width of a thin line (a heavy line is twice as wide)
    # --- G10: sun shafts seen in the air (assets/shaders/sun_window.glsl: every surface shader marches from the eye to its pixel and adds the sunlit air on the way) ---
    shaft_density: float = 0.045              # 1/m: how much of the light the dusty air scatters toward the eye (0 = no shafts)
    shaft_anisotropy: float = 0.55            # Henyey-Greenstein g: > 0 = brighter looking toward the sun
    shaft_dust: float = 0.6                   # 0..1: how much slow-moving dust clouds modulate the shafts
    shaft_range: float = 26.0                 # m: the march stops this far from the eye
    dust_size: float = 0.005                  # m: radius of one dust mote (game/dust.py; graphics level High)
    dust_brightness: float = 1.6              # how strongly a mote glints in a sun beam (it is invisible in the shade)
    dust_box: float = 7.0                     # m: the motes fill a box this wide around the eye (it wraps as he walks)


@dataclass
class WaterData:
    """The pool water (assets/shaders/water.*, math in core/waves.py + core/cubemap.py): dark mirror, Fresnel, teal in the shallows, faint ripples, rings where a bullet lands.
    The reflection is the room captured ONCE (box-projected cube), so smoke, tracers and the gun are not mirrored."""
    deep_color: tuple = (0.004, 0.012, 0.014)     # body colour of deep water (linear light): nearly black, like the photo
    shallow_color: tuple = (0.004, 0.045, 0.110)  # body colour in the shallows and what the water scatters on the way to the bottom (G11: blue, was teal)
    shallow_width: float = 1.4                    # m: how far the teal reaches from the pool wall / steps
    reflect_strength: float = 1.0                 # multiplies the mirrored room (1 = as captured)
    fresnel_f0: float = 0.06                      # reflectivity looking straight down (real water 0.02); grazing view is always near 1
    ripple_strength: float = 0.030                # tilt of the surface normal from the ambient ripples (0 = flat mirror)
    ripple_scale: float = 1.0                     # multiplies the ripple wavelength
    ripple_speed: float = 0.55                    # drift speed of the ripples
    impact_strength: float = 0.20                 # tilt of the normal at the crest of a bullet ring
    impact_speed: float = 1.7                     # m/s: the ring expands this fast
    impact_wavelength: float = 0.34               # m between two crests of a ring
    impact_width: float = 0.60                    # m: thickness of the packet of crests (the ring)
    impact_life: float = 2.6                      # s: a ring fades out in about this time
    impact_reach: float = 5.0                     # m: distance at which a ring has faded to 1/e (spreading out)
    ripple_slots: int = 12                        # most rings alive at once (a burst reuses the oldest ring)
    # --- G10: clear water, wave simulation (core/watersim.py, game/water_sim.py), see-through bottom, caustics; graphics level 'low' keeps the G9 dark mirror + rings above ---
    sim_speed: float = 1.1                        # m/s: waves of the simulation travel this fast (real ripples 0.3-2 m/s)
    sim_life: float = 2.5                         # s: a wave left alone loses 1/e of its height in this time
    sim_slope: float = 1.0                        # multiplies the simulated slope on the normal (how strongly waves bend the picture)
    bullet_push: float = -0.015                   # m: a bullet landing pushes the water down this much (Gaussian)
    bullet_radius: float = 0.06                   # m: radius of that push
    basin_color: tuple = (0.14, 0.36, 1.00)       # tile colour of the pool basin under the water (linear; pool blue, G11: bluer like the user's photos). Only seen through the water: not baked
    basin_tile: float = 0.15                      # m: tile size on the basin floor and walls
    basin_light: float = 0.75                     # multiplies the baked room ambient (at gun height) to light the basin bottom
    absorption: tuple = (0.45, 0.13, 0.03)        # 1/m per colour: water swallows red first, then green (real water: a deeper path turns blue)
    # G11 caustics (core/caustics.py, game/caustics.py): a light mesh refracted by the small ripples + the simulated waves, drawn each frame into a texture over the pool plan
    caustic_strength: float = 1.0                 # multiplies the sunlight on the bottom where the caustic pattern lies (1 = physical)
    caustic_ambient: float = 0.12                 # how much the pattern also shows where only sky light reaches (0 = only in the sun)
    caustic_wall: float = 0.7                     # share of the pattern on the pool walls (they read the floor's pattern along the sun ray: an approximation)
    caustic_peak: float = 6.0                     # the brightest the lines get (multiples of the average light): brighter ones saturate softly
    caustic_white: float = 0.9                    # 0..1: how much the bright lines lose the tile colour (a real photo burns them to white)
    caustic_sim: float = 1.0                      # weight of the simulated waves (bullets, wading) in the light mesh (1 = physical)
    wave_size: float = 0.35                       # m: middle wavelength of the small ripples = about the size of a caustic cell
    wave_height: float = 0.003                    # m: rms height of the ripples: larger = sharper lines that cross sooner (shallower)
    wave_speed: float = 0.4                       # factor on the real ripple speed (1 = capillary-gravity waves, ~0.8 m/s)
    wave_bend: float = 2.5                        # how much the ripples bend the view of the tiles under the water (1 = physical; more = the wobbly grout of the photo)
    wave_mirror: float = 0.5                      # share of the ripples in the reflection (1 = physical: breaks the mirrored room into small pieces)
    glint_strength: float = 2.5                   # the sun's sparkle on the waves (only where the sun reaches the water)
    glint_power: float = 900.0                    # sharpness of the sparkle (larger = smaller, harder dots)


@dataclass(frozen=True)
class GraphicsLevel:
    """One graphics level (F2 switches live, core/graphics.py). Every G10 effect reads its share from here; switching changes uniforms / enables buffers, never recompiles."""
    name: str                     # shown on screen when switching
    sim_cols: int                 # wave simulation grid (0 = no simulation: analytic bullet rings, as G9)
    sim_rows: int
    refraction: bool              # see the pool bottom through the water (False = the G9 dark mirror)
    caustics: int                 # 0 off, 1 / 2: light mesh + texture size (core/graphics.py CAUSTIC_SIZES)
    glint: bool                   # the sun's sparkle on the waves
    shaft_steps: int              # sun shafts: dust noise samples per lit piece of a view ray (0 = no shafts; the lit length itself is exact, sun_window.glsl)
    splash: float                 # share of the splash droplets drawn (0 = none)
    wet: bool                     # wet deck: puddles mirroring the room, wet footprints
    gun_env: bool                 # the room mirrored on the gun's metal (else the old ambient guess)
    dust: bool                    # dust motes glinting in the sun beams
    under: int = 1                # G12 under the water: 0 simple (fog only: no caustics on the basin, flat surface seen from below), 1 full (caustics, waves bend the Snell window)
    render_scale: float = 1.0     # G13: world + gun are drawn at this share of the window size, the lens pass upscales (text and panels stay sharp); core/graphics.py RENDER_SCALES
    smoke_simple: bool = False    # G13: gun smoke shaded per corner (colour, haze, size fade interpolated): ~40% cheaper while firing
    surface: int = 2              # 8/11/2026 surface detail (tile floor and walls, bullet holes): 0 = flat colour, 1 = normal map + cavity, 2 = also parallax (the grout / crater really sunk in)


SMOKE_SIMPLE_KEEP = 0.5           # G13: share of the gun smoke puffs drawn when the smoke is 'Đơn giản' (core/smoke.py thin_items); the M4's full-auto smoke cost ~2 ms at 1440 x 810


GRAPHICS_LEVELS = (
    GraphicsLevel('Thấp', 0, 0, False, 0, False, 0, 0.0, False, False, False, 0, 0.75, True, 0),     # G13: 3D at 75%, simple smoke, no surface relief: weak laptops (UHD 620 class)
    GraphicsLevel('Vừa', 128, 256, True, 1, True, 1, 0.6, True, True, False, 1, 1.0, False, 1),
    GraphicsLevel('Cao', 256, 512, True, 2, True, 3, 1.0, True, True, True, 1),
)


@dataclass
class SplashData:
    """G10: water droplets (core/splash.py, game/splash.py) and wading (slower legs, the body pushing the water). Droplet counts are multiplied by the graphics level."""
    bullet_drops: int = 16                # drops thrown up by one bullet landing on the water
    bullet_speed: float = 3.4             # m/s
    bullet_cone: float = 16.0             # deg around straight up
    land_drops: int = 46                  # drops when the player lands in the water (jump / fall)
    land_speed: float = 2.4
    land_cone: float = 50.0
    land_push: float = -0.05              # m: the landing pushes the water down this much...
    land_radius: float = 0.40             # ...over this radius
    wade_drops: int = 3                   # drops kicked up per wading push (more when running)
    speed_jitter: float = 0.45            # share of random speed change per drop
    drop_size: float = 0.011              # m: radius of a drop
    drop_life: float = 1.4                # s at most (most fall back into the water sooner)
    gravity: float = 9.81
    drag: float = 0.5                     # 1/s: air drag on a drop
    wade_slow: float = 0.55               # walking speed multiplier in chest-deep water (1 on the deck; linear with depth between)
    under_slow: float = 0.38              # G12: walking speed multiplier on the bottom with the head under the water (slower than chest-deep)
    wake_spacing: float = 0.32            # m walked in the water between two pushes of the surface
    wake_push: float = -0.012             # m: strength of one push (scaled by depth and speed)
    wake_radius: float = 0.22             # m
    # --- wet deck (room.frag) and wet footprints (core/footprints.py) ---
    puddles: float = 0.55                 # 0..1: how much of the deck has standing water (more near the pool edge)
    puddle_scale: float = 1.8             # m: size of the puddles
    wet_reach: float = 1.4                # m: the deck is damp this far from the pool edge
    wet_darken: float = 0.45              # how much darker a wet tile is (Lagarde: wet = darker diffuse, brighter reflection)
    wet_reflect: float = 0.9              # strength of the room mirrored in the puddles
    print_spacing: float = 0.62           # m walked between two wet footprints
    print_life: float = 25.0              # s: a footprint dries out in this time
    feet_dry: float = 12.0                # s out of the water until the feet leave no more prints


@dataclass
class UnderwaterData:
    """G12: the head under the water (core/underwater.py, game/underwater.py, assets/shaders/underwater.glsl, basin.*, lens.frag).
    The lens PORT is a small window at the eye: a pixel is under the water when its point on the port is below the surface, so near the surface the frame splits in two."""
    fog_color: tuple = (0.07, 0.30, 0.40)       # colour the murky water turns into far away (display colour, 0..1)
    turbidity: float = 0.32                     # 1/m: how fast the view fogs up under the water (0.32: half gone at 2.2 m, almost all at 9 m)
    absorb_scale: float = 1.0                   # multiplies water.absorption on the underwater path (red goes first)
    port_half: float = 0.05                     # m: half height of the lens port; the frame is split while the surface is within this of the eye
    wobble: float = 0.0025                      # m: the waterline on the port wobbles this much (lapping water)...
    wobble_speed: float = 0.0060                # ...plus this much per m/s walked
    meniscus: float = 0.0035                    # m: thickness of the bright / dark line where the water touches the port
    zoom: float = 1.22                          # fully under: the image is magnified this much (a flat port: water bends the rays, ~1.33 for a real flat port)
    warp: float = 0.18                          # fully under: extra fisheye at the edges
    zoom_time: float = 0.35                     # s to blend the zoom in / out
    gun_fog: float = 0.6                        # m of water the gun is seen through (tints the gun blue under the water)
    snell_ripple: float = 1.0                   # how strongly the waves bend the room seen through the Snell window from below
    no_fire_text: str = 'Không thể bắn ở đây'   # shown when the trigger is pulled with the head under the water
    no_fire_time: float = 1.6                   # s the line stays


@dataclass
class GraphicsData:
    level: int = 2                # index in GRAPHICS_LEVELS at start (F2 cycles while playing)


@dataclass(frozen=True)
class MapData:
    """The pool hall (core/poolmap.py builds boxes from these numbers; NOT on the F1 panel: changing any of them means a re-bake).
    Axes: y up, z forward. The player starts on the south bank at z = -(room_z / 2 - 2.5) looking north (+z) along the pool. Windows are holes in the EAST wall (+x)."""
    room_x: float = 20.0              # interior width, west-east (m)
    room_z: float = 30.0              # interior length, south-north (m)
    ceiling: float = 4.2              # height of the ceiling underside above the deck (m)
    wall: float = 0.4                 # thickness of walls, slab and ceiling (m)
    pool_x: float = 12.0              # pool width (m); centred in the room
    pool_z: float = 24.0              # pool length (m)
    water_y: float = -0.12            # water surface (deck top is y = 0)
    pool_floor: float = -0.62         # pool bottom of the SHALLOW end: 0.5 m of water
    pool_deep: float = -2.12          # pool bottom of the DEEP end: 2.0 m of water (user 7/11/2026: "about 1.5 m deeper"; the bottom slopes, he wades until the water is chest-deep)
    slope_z: tuple = (-4.0, 6.0)      # the bottom slopes from pool_floor at z0 down to pool_deep at z1 (flat before and after)
    wade_depth: float = 1.25          # m of water at chest height: the wading slowdown reaches `SplashData.wade_slow` here (G12: deeper water is no longer blocked, he walks on the bottom)
    north_steps: bool = False         # the narrow steps at the north end (G9); off since the north end is 2 m deep: the two handrails stay as a pool ladder
    steps: int = 3                    # steps down into the pool at the south end (full width); the rise is the SHALLOW depth / (steps + 1)
    step_depth: float = 0.45          # tread depth of the south steps (m)
    north_steps_x: tuple = (-3.0, -0.6)   # x range of the narrow steps at the north end (the ladder handrails stand on its two sides)
    window_sill: float = 0.45         # window bottom above the deck (m)
    window_top: float = 3.75          # window top above the deck (m)
    window_z: tuple = (-10.0, -3.5, 3.5, 10.0)    # centres of the windows along the east wall (m)
    window_width: float = 4.0         # m
    column_x: float = -8.0            # centre of the columns on the west bank
    column_z: tuple = (-6.0, 6.0)
    column_size: float = 1.2          # square column, full height (m)
    stair_x: tuple = (4.5, 9.5)       # x range of the flight of stairs on the north bank (rises toward +z, ends in a landing against the north wall)
    stair_count: int = 4
    stair_rise: float = 0.17
    stair_tread: float = 0.35
    rail_radius: float = 0.028        # handrail tube radius (m)
    ladder_width: float = 0.60        # G14: distance between the two ladder rails (centre to centre), centred on the middle of north_steps_x
    ladder_standoff: float = 0.10     # the rails' centre line stands this far in front of the north pool wall (so the ladder hugs the wall down to the floor)
    ladder_rungs: int = 5             # steps between the rails under the water: evenly from 0.30 m under the surface to 0.10 m above the floor
    rung_radius: float = 0.020        # m
    wall_albedo: tuple = (0.74, 0.66, 0.50)       # tile colour of walls, ceiling and columns (linear)
    floor_albedo: tuple = (0.80, 0.75, 0.64)      # tile colour of the deck, steps and pool wall
    rail_albedo: tuple = (0.62, 0.64, 0.66)       # stainless steel
    wall_tile: float = 0.10           # mosaic tile size on walls and ceiling (m)
    floor_tile: float = 0.30          # tile size on the deck (m)
    # --- bake (core/lightbake.py) ---
    texel: float = 0.08               # lightmap texel size (m)
    coarse: float = 0.40              # texel size of the bounce light (it is smooth, so it is sampled sparsely and stretched)
    sun_samples: int = 8              # shadow rays per texel over the sun disc (soft edge of the patches)
    sun_radius: float = 0.012         # angular radius of the sun disc (rad); wider than the real 0.0047 so the penumbra shows
    bounce_rays: int = 384            # cosine-weighted rays per coarse texel (a small bright patch is hit by few rays, so fewer rays show as blotches)
    bounce_gain: float = 1.5          # extra for the bounces after the second (not simulated): a real tiled hall glows from its many bounces
    fill: float = 0.04                # irradiance added everywhere (sky coloured): a corner no ray reaches light from is never pitch black in a real room
    lightmap_max: float = 4.0         # irradiance that maps to 255 in the 8-bit lightmap (stored with gamma 2)
    # --- reflection capture (game/pool_capture.py) ---
    probe: tuple = (0.0, 1.3, 0.0)    # where the room is captured from (above the water, mid-room)
    reflect_size: int = 512           # side of one cube face (px); the atlas is 3 x 2 faces


@dataclass
class LensData:
    """Head camera lens (assets/shaders/lens.frag, math in core/lens.py + core/exposure.py), drawn AFTER the world and gun are composited."""
    fisheye: float = 0.25                 # fisheye distortion: 0 = flat image; the center is magnified (1 + fisheye) times
    fisheye_ads: float = 0.16             # less distortion when fully aimed
    chroma: float = 0.012                 # color fringing: the distortion difference between the red and blue channels, growing toward the edges
    smear: float = 0.030                  # blur at the edges when still (fraction of frame)
    smear_motion: float = 0.00022         # extra blur per deg/s of turning
    smear_start: float = 0.50             # radius where the blur starts (0 at center .. 1 at the horizontal edge)
    rolling_shutter: float = 0.00011      # rolling shutter: top and bottom rows shift sideways with turn speed (fraction of frame per deg/s)
    vignette_start: float = 0.78          # radius where darkening starts (unit 1 = horizontal edge)
    vignette_end: float = 1.14            # radius of full darkness; the frame corners go black like Bodycam photos
    fringe: float = 0.55                  # orange fringe at the edge of the corner darkening (light leaking past the lens rim)
    noise: float = 0.024                  # sensor noise, stronger in dark areas (G9: 0.030 -> 0.024)
    bloom: float = 0.45                   # bright areas bloom outward; 0 = off (cheaper)
    bloom_threshold: float = 0.72         # only brightness above this blooms
    contrast: float = 1.10                # > 1: darker darks, brighter brights
    saturation: float = 0.88              # 1 = keep color, 0 = grayscale (G9: 0.70 -> 0.88, the pool hall is warm and rich: user chose 'between Bodycam and the photo')
    tint: tuple = (1.0, 0.99, 0.95)       # the sickly yellow cast of cheap cameras (G9: eased from 0.93)
    auto_exposure: float = 0.55           # 0 = fixed exposure, 1 = fully compensated for the brightness of the scene
    exposure_key: float = 0.70            # local brightness that corresponds to exposure 1
    exposure_min: float = 0.55
    exposure_max: float = 2.2
    # ALL camera shake (head bob, steps, jump / landing, shots, reload beats, idle drift, the reload glance) moves the WHOLE lens frame (image + dark rim + distortion
    # centre) instead of the world camera: the rotation part becomes a shift / tilt of the frame, the position part is turned into an angle at `shake_pos_ref`.
    shake_scale: float = 1.0              # multiplies the whole frame motion (0 = steady frame)
    overscan: float = 0.22                # the world + gun are drawn this much wider than shown and the lens crops the middle: the frame can shift this far (x0.9, soft) without showing black. Larger = softer image
    shake_pos_ref: float = 0.5            # m: a head shift of x metres moves the frame like a turn of atan(x / shake_pos_ref)
    shake_glance: float = 0.45            # the reload glance (~18 deg down on the M4) moves the frame by this share of a real turn: ~1/8 of the frame height (user choice 'medium')


@dataclass(frozen=True)
class SoundCue:
    """One sound tied to a clip frame: plays when the clip reaches `frame` (absolute frame on the glb timeline, like Clip.swap)."""
    frame: int
    sound: str                            # group name in assets/sounds/foley (tools/build/prep_*.py): file <sound>_<number>.wav
    volume: float = 1.0                   # multiplies AudioData.reload_volume


# M4 sound beats, measured with tools/measure/g5_reload_probe.py (distance of magazine / bolt / catch from the ready pose, frame by frame).
M4_SOUND_CUES = {
    # Reload (1..110): magazine catch pressed at 26, magazine leaves its seat from 27 (6 cm away, then 15 cm at 29, 30 cm at 31), new magazine slides in 49..60, seats at 61 (= Clip.swap),
    # bolt/catch taps lightly at 74..76, magazine settles a bit more at 83
    # User-supplied sound (AudioData.sound_files), three impacts in the original file: (1) magazine catch, (2) magazine slides in then seats, (3) bolt.
    # NORMAL RELOAD (a round still in the chamber) has only the FIRST TWO impacts: catch at 26, magazine slides in 57..60 (very quiet), seats at 61. No old synthesized sound remains.
    'reload': (SoundCue(26, 'mag_release', 0.9), SoundCue(57, 'mag_in', 0.7), SoundCue(61, 'mag_seat', 1.0)),
    # Reload_Empty (111..224): bolt locked back. Magazine leaves from 137, new magazine seats at 172 (= Clip.swap), BOLT RELEASES forward at 190 (bolt 7.0 -> 4.4 -> 3.0 cm),
    # bolt fully home at 197..199, magazine settles more at 201
    # EMPTY RELOAD: runs all three impacts (adds the bolt release forward at 190).
    'reload_empty': (SoundCue(136, 'mag_release', 0.9), SoundCue(168, 'mag_in', 0.7), SoundCue(172, 'mag_seat', 1.0), SoundCue(190, 'bolt_release', 1.0)),
    # Draw (269..299): gun starts rising at 270, fastest 272..280, nearly still from 284, fully settled at ~287
    'draw': (SoundCue(271, 'draw_a', 0.8), SoundCue(285, 'draw_b', 0.6)),
}


# Glock 17 sound beats (absolute frames on the glb timeline, like M4_SOUND_CUES). The user's own recordings (8/11/2026, tools/build/prep_glock_audio.py) replace the first two and the last reload
# beats; each file starts `lead` whole frames BEFORE its main transient (glock_release 6, glock_magout 2, glock_seat 2), so  cue frame = animation event frame - lead.
# Animation events, measured with the bounding-box centre of Mag1 / Mag2 / Slide and the left-hand joint on every frame (the pack keys many parts every 2nd frame):
#   Reload (1..84): left hand pulls the old magazine (Mag1, the one drawn until Clip.swap) from f21 (first move), it clears the well at f27 (6.9 cm in one step), stops fully out (18 cm) at f29;
#     the spare magazine (Mag2) bottoms out at f44 but is drawn only from the swap frame 45, which is when the player sees it seated (the gun jolts at f46); the old magazine is stowed f57-59
#   ReloadEmpty (107..197): the same moves 107 frames later: pull from f129, clears the well f133-134, out at f135 (f136 = 18.0 cm), spare seated at f151 (= Clip.swap), SLIDE RELEASE at f164 (slide jumps forward)
# Beats: release = soft button click + the clack of the magazine sliding free (click 4.7 frames before the clack, two small rattles after it); magout = the old magazine comes clear (loud double thump);
# seat = the new magazine slams home; glock_slide = the old ElevenLabs slide release cut to its first beat (the file had an extra settle beat 0.34 s later: user 8/11/2026). The old mag_in slide-in is gone (the seat file starts with its own soft slide-in 2 frames before the slam). tests/test_glock_audio.py checks this table against the files.
GLOCK_SOUND_CUES = {
    'reload': (SoundCue(20, 'glock_release', 0.65), SoundCue(27, 'glock_magout', 0.95), SoundCue(43, 'glock_seat', 1.0)),      # clack f26, thump f29, slam f45
    'reload_empty': (SoundCue(126, 'glock_release', 0.65), SoundCue(133, 'glock_magout', 0.95), SoundCue(149, 'glock_seat', 1.0),     # clack f132, thump f135, slam f151
                     SoundCue(164, 'glock_slide', 1.0)),
    'draw': (SoundCue(214, 'pistol_draw', 0.8), SoundCue(230, 'pistol_draw_settle', 0.6)),
    'holster': (SoundCue(200, 'pistol_holster', 0.8),),
}
GLOCK_SOUND_FILES = {
    'glock_release': 'glock_release', 'glock_magout': 'glock_magout', 'glock_seat': 'glock_seat',
    'glock_slide': 'glock_slide', 'pistol_draw': 'el_pistol_draw',
    'pistol_draw_settle': 'el_pistol_draw_settle', 'pistol_holster': 'el_pistol_holster', 'dry': 'el_pistol_dry',
}

# Glock 17: semi-auto, heavy and firm (CoD pistol feel). Viewmodel = the ready-made animation pack assets/guns/glock17.glb (hands + Glock, rigid parts on the pack's own rig).
# All clips share one timeline of 30 fps frames, like the M4 pack; a clip of N frames wraps frame N to 0, so the last usable frame is N - 1.
GLOCK = GunData(
    name='Glock 17',
    glb='assets/guns/glock17.glb',
    credit='Glock 17: FPS animation pack glock17.glb (author not recorded)',
    clips={
        'reload': Clip('Reload', 1, 84, swap=45, settle=70),
        'reload_empty': Clip('ReloadEmpty', 107, 197, swap=151, settle=180),
        'fire': Clip('Fire', 86, 105),
        'holster': Clip('Holster', 198, 211),
        'draw': Clip('Draw', 212, 245, settle=233),
    },
    eye_joint='FPS_Camera_j_02',
    ready_pose=('Draw', 245),
    locked_pose=('ReloadEmpty', 107),
    mag_nodes=('Mag2_*-parent', 'Mag1_*-parent'),            # the pack seats Mag2 in Idle / Draw / Fire / Holster and Mag1 in Reload / ReloadEmpty
    fire_clips=('fire',),
    # same material table as the M4 (the gun body has no specular in the file, so the numbers are set by hand)
    materials={'Glock_D': (1.0, 1.0, 1.0, 1.0), 'Bullet_9mm_D': (1.5, 1.6, 1.4, 1.0), 'Glove_D': (0.22, 0.4, 0.35, 0.42), 'Hand_D': (0.08, 0.3, 0.15, 1.0)},
    sound_cues=GLOCK_SOUND_CUES,
    sound_files=GLOCK_SOUND_FILES,
    # heavy and firm: bigger kick, slower cycle, semi-auto, 17 rounds
    rpm=420.0, magazine=17, reserve=85, full_auto=False, muzzle_velocity=375.0, ads_time=0.16,
    recoil=RecoilData(up=1.6, up_noise=0.35, right_noise=0.45, right_walk=0.10, camera_share=0.35, recovery=0.45, recovery_time=0.22),
    kick=GunKickData(omega=30.0, zeta=0.5, peak=(0.0, 0.007, 0.0, 2.2, 0.0, 0.0), random=(0.003, 0.002, 0.0, 0.5, 0.4, 1.8),
                     back_peak=-0.050, back_random=0.004, back_omega=16.0, back_zeta=0.7, back_ads_scale=1.15),
    # 8/11/2026: the user's F1 numbers were baked into the class defaults for the M4 only; the Glock keeps the numbers it had before
    accuracy=AccuracyData(stand=0.03, walk=0.03, air=0.03, crouch_multiplier=1.0, ads=0.03, ads_move=0.03),
    reload=ReloadData(view_pose=(0.07, 0.105, -0.02, 0.0, 0.0, 2.5)),
    head=HeadCamData(body_omega=7.0, glance_out_lead=0.42, glance_out_time=0.70, gaze_hand_weight=0.65, gaze_time=0.30, gaze_jitter=0.15),
    shot_sound=('assets/sounds/glock_shot_0.wav',),    # the user's recording (8/11/2026) as it is, no pitch-shifted copies (they dulled it): only the small random pitch below varies it
    shot_pitch_variation=0.02,
    shot_pool=4,
    hip_offset=(0.0, 0.0, 0.15),           # push the whole viewmodel forward a little: the pack's hands sit close to the eye
    sway=SwayData(wall_pose=(0.0, -0.404, 0.173, 65.0, 0.0, 0.0)),     # G14 High Ready: the pitch turns the gun about the eye and the Glock sits farther out, so the shift is bigger than the M4's
    ads_eye_relief=0.38,                   # was 0.50: at 0.5 m the 2 mm front post was only a few pixels wide (user could not see it); 0.38 makes the sights ~30% larger. Tunable on F1
    shake=ShakeData(reload_beats={'reload': ((29, 'mag_out'), (45, 'seat')), 'reload_empty': ((135, 'mag_out'), (151, 'seat'), (164, 'bolt'))}),
    # measured with tools/measure/g8_measure.py (camera frame at rest, hip_offset not included)
    # rear point = the middle of the rear NOTCH (blade tops -0.0191, notch floor -0.0214: 2.3 mm deep), front point = top of the front post (-0.0199). The first version put the rear point 3.5 mm under the
    # blade tops, i.e. 1.2 mm BELOW the notch floor: the line of sight went through the slide and the front sight was hidden behind it (user report 7/11/2026)
    ads_sights=((0.0612, -0.0203, 0.2502), (0.0612, -0.0199, 0.4209)),
    muzzle=(0.0612, -0.0410, 0.4278),
    # pistol: a smaller puff; the ejection port is on the top right of the slide, ~2/3 of the way forward (estimated from the slide bounds)
    smoke=SmokeData(puffs=4, speed=7.0, size=0.04, growth=0.35, opacity=0.34, life=0.85, ejection_port=(0.072, -0.016, 0.35)),
)

GUNS = {'m4': M4, 'glock': GLOCK}


@dataclass
class AudioData:
    """Foley: metal sounds when reloading / drawing the gun (timed to the animation frames) and footsteps on tiles (timed by distance travelled). Sounds built with the tools/build/prep_*.py scripts.
    Volume is lower than the gunshot (GunData.shot_volume 0.8) so it does not mask the shot."""
    folder: str = 'assets/sounds/foley'
    pool: int = 2                         # rotating playback copies per file: a later sound does not cut off the tail of the previous one
    # logical sound name -> real file group in folder (<group>_<number>.wav): el_* = sounds generated with ElevenLabs (tools/build/prep_elevenlabs.py from assets/sounds/source/elevenlabs), boot_step = the user's
    # footstep (tools/build/prep_pool_audio.py), glock_* = the user's Glock reload beats (tools/build/prep_glock_audio.py). The synthesized and user_* sounds and their tools were deleted 8/11/2026: every name needs a line here
    sound_files: dict = field(default_factory=lambda: {
        'mag_release': 'el_mag_release', 'mag_in': 'el_mag_in', 'mag_seat': 'el_mag_seat',
        'bolt_tick': 'el_bolt', 'bolt_release': 'el_bolt',
        'draw_a': 'el_draw_a', 'draw_b': 'el_draw_b', 'settle': 'el_settle',
        'step_walk': 'boot_step', 'step_run': 'boot_step',      # the user's boot-on-brick recording (8/11/2026, tools/build/prep_pool_audio.py): ONE step, impact on the file's first sample so it lands on the bob's lowest point
        'land': 'el_land', 'jump': 'el_jump',
        'dry': 'el_dry', 'hit_hard': 'el_hit_hard'})
    # multiplies the pitch when playing a logical name (running shares the walking file, slightly higher)
    pitch_scale: dict = field(default_factory=lambda: {'step_run': 1.06})
    # multiplies the volume when playing a logical name: a level trim for a recording that is quieter than the old sounds at equal volume. The boot-on-brick step (8/11/2026) is short and sharp, 6.5 dB lower in RMS
    # than the old steps, which the user found too quiet: x2.3 brings it back to the old loudness (+0.6 dB) while step_volume and the tests that compare gains keep their meaning. Peak 0.85 x 0.30 x 2.3 x 1.25 x 1.1 stays < 1
    volume_scale: dict = field(default_factory=lambda: {'step_walk': 2.3, 'step_run': 2.3})
    # reload / draw
    cues: dict = field(default_factory=lambda: dict(M4_SOUND_CUES))   # clip key (GunData.clips) -> the SoundCues; real time = (frame - clip.start) / 30 / clip speed
    reload_volume: float = 0.5
    cancel_sound: str = 'settle'          # hand slides back to the ready pose when reloading is cancelled (only if at least one sound from that reload has played)
    cancel_delay: float = 0.06            # s after the cancel
    cancel_volume: float = 0.6
    # footsteps: EACH TIME the gun reaches the lowest point of the bob (Sway.phase crosses step_bob_phase and step_bob_phase + pi, i.e. two steps per bob cycle), one sound plays.
    # So the footstep rhythm matches the gun sway rhythm at any speed (bob_rate / bob_sprint_rate / bob_stride of SwayData). The stride values below are used only when there is NO sway (tests, fallback).
    step_bob_phase: float = 2.356         # rad (= 3 pi / 4): bob phase when the gun is lowest = foot touches the ground (y bob = sin(2 phase) is at its minimum)
    step_stride_walk: float = 0.75        # m per step
    step_stride_sprint: float = 1.0
    step_stride_crouch: float = 0.5
    step_start_phase: float = 0.5         # 0..1: the first step after standing still comes early (half a stride)
    step_min_speed: float = 0.5           # m/s: slower than this does not count as walking
    step_volume: float = 0.30
    step_sprint_multiplier: float = 1.25
    step_crouch_multiplier: float = 0.35
    step_pitch_variation: float = 0.05    # +- random pitch ratio
    step_volume_variation: float = 0.10   # +- random volume ratio
    foot_pitch: float = 0.02              # left foot lower, right foot higher by this much (alternating)
    foot_pan: float = 0.15                # left / right channel pan (-1..1)
    # landing / jumping
    land_min_speed: float = 2.0           # m/s: falling slower than this counts as just a footstep
    land_reference_speed: float = 6.4     # fall speed for the reference volume (jumping in place and coming down)
    land_volume: float = 0.50
    land_gain_range: tuple = (0.45, 1.3)  # multiplies volume by fall speed / reference speed, clamped to this range
    jump_volume: float = 0.25
    # the game has no HUD, so the hit sound is the main feedback. Sound travels from the hit point to the ear: it arrives late by the speed of sound and fades with distance
    hit_hard_volume: float = 0.50
    hit_reference_distance: float = 45.0  # m: at this distance the volume is half
    hit_pitch_variation: float = 0.05     # +- random pitch ratio
    speed_of_sound: float = 343.0         # m/s
    dry_volume: float = 0.55              # trigger pulled with no rounds left
    # --- G10 water sounds (user's choice 7/11/2026: ONE wading sound for every step, one for jumping in, one room tone; the other drafts were removed). Groups in `folder`:
    # wade_* and water_land_* (OPTIONAL: a missing group is silent). The single wading recording is calibrated by depth and speed: a deep slosh at chest depth, higher and
    # lighter in the shallows, quicker and a little louder when running ---
    wade_volume: float = 0.30             # one step at chest depth (the recording is 1.48x as loud as a tile step at equal volume: 0.30 -> a fuller sound, ~1.3x a tile step; tools/build/prep_water_audio.py prints the ratio)
    wade_deep_ref: float = 1.25           # m of water that counts as 'chest depth' (= MapData.wade_depth)
    wade_shallow_gain: float = 0.50       # volume share of a step in ankle-deep water (it grows linearly with depth up to 1)
    wade_pitch_shallow: float = 1.30      # playback rate in ankle-deep water (higher = lighter splash)
    wade_pitch_deep: float = 1.00         # playback rate at chest depth (the recording as it is)
    wade_run_pitch: float = 1.25          # extra rate when running (shorter, quicker splash: steps come faster)
    wade_run_gain: float = 1.15           # extra volume when running
    water_land_volume: float = 0.85       # jumping / falling into the water (scales with the fall speed like the tile landing)
    ambience_file: str = 'assets/sounds/pool_ambience.wav'    # looping room tone of the pool hall (silent if the file is missing); the user's 'Tranquil indoor swim (narrow)' since 8/11/2026, tools/build/prep_pool_audio.py
    ambience_volume: float = 0.30
    # G12 under the water (tools/build/prep_underwater.py; the ElevenLabs drafts were dropped by the user 7/11/2026): every foley sound has a muffled twin in `folder_under` (the Foley swaps to it while
    # the eye is under the surface), the room tone is cross-faded with an underwater tone. A missing file / folder is silent / unchanged. No separate sound for going under / coming up (user's choice).
    folder_under: str = 'assets/sounds/foley_under'
    under_ambience_file: str = 'assets/sounds/under_ambience.wav'   # looping tone with the head under the water (replaces the room tone while under)
    under_ambience_volume: float = 0.45
    under_fade: float = 0.25                                         # s: cross-fade between the room tone and the underwater tone


@dataclass
class GameParams:
    player: PlayerParams = field(default_factory=PlayerParams)
    gun: GunData = field(default_factory=lambda: M4)
    feedback: FeedbackParams = field(default_factory=FeedbackParams)
    look: LookData = field(default_factory=LookData)
    audio: AudioData = field(default_factory=AudioData)
    lens: LensData = field(default_factory=LensData)
    water: WaterData = field(default_factory=WaterData)
    graphics: GraphicsData = field(default_factory=GraphicsData)
    splash: SplashData = field(default_factory=SplashData)
    underwater: UnderwaterData = field(default_factory=UnderwaterData)
