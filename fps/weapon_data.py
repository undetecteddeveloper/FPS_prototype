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
    fov: float = 96.0                     # horizontal FOV of the image BEFORE the lens; the fisheye lens magnifies the center ~1.25x, so the center looks like ~83 degrees and the edges show more
    mouse_sensitivity: float = 45.0       # degrees turned when the mouse moves the full window HEIGHT (independent of resolution)
    pitch_limit: float = 89.0
    moving_speed_threshold: float = 0.5   # above this counts as "moving"
    ads_look_multiplier: float = 0.7      # multiplier on mouse sensitivity when fully aimed
    sprint_blocks_fire: bool = True       # pulling the trigger while sprinting: stop sprinting, lower the gun, then fire (sprint-to-fire). False: fire straight from the sprint pose
    land_dip_per_speed: float = 0.006     # m the camera dips per m/s of landing speed (falling at 6.4 m/s dips ~4 cm)
    land_dip_omega: float = 18.0          # rad/s
    land_dip_zeta: float = 0.5


@dataclass(frozen=True)
class Clip:
    """One animation segment of the glb. Frames are counted at 30 fps on the file's shared timeline."""
    anim: str
    start: int
    end: int       # LAST valid frame (frame N of a clip with N frames is wrapped to 0, so N itself is not used)
    swap: int = None   # frame where the new magazine seats (measured with tools/measure/g5_reload_probe.py); reload clips only
    settle: int = None  # frame where the gun, magazine and bolt are back in place: the rest of the clip is only the hand re-folding its fingers (the reload view is switched off at this frame)

    @property
    def duration(self) -> float:
        return (self.end - self.start) / 30.0

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
    so the state-based cone was removed: every state is ~2 MOA. The fields stay so they can be tuned on the F1 panel (and the selftest measures spread)."""
    stand: float = 0.03
    walk: float = 0.03
    sprint: float = 0.03
    air: float = 0.03                     # jump / fall
    crouch_multiplier: float = 1.0        # multiplier on the base when crouching
    ads: float = 0.03                     # aiming, standing still
    ads_move: float = 0.03                # aiming, moving
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
    back_peak: float = -0.030             # m: peak of ONE single shot; negative = back toward the eye
    back_random: float = 0.003            # m: ± random per shot
    back_omega: float = 18.0              # rad/s (period ~0.35 s)
    back_zeta: float = 0.7
    back_ads_scale: float = 1.15          # when fully aimed the push-back is multiplied by this (1.3 = 30% MORE push-back than at the hip; visual only: the camera and bullet direction do not change)
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
    # sprint pose (gun lowered, muzzle angled); blended by player.sprint_amount
    sprint_pose: tuple = (-0.01, -0.012, 0.02, -7.0, -16.0, 10.0)
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
    view_pose: tuple = (0.07, 0.105, -0.02, 0.0, 0.0, 2.5)
    view_blend: float = 0.25


@dataclass
class ViewLightData:
    """Gun + hand materials (assets/shaders/viewmodel.*). NO separate light: the gun receives the same ceiling lamps, shadows, ambient light and muzzle flash as the world."""
    specular: float = 0.55                # metallic sheen of the gun body (highlights from the ceiling lamps)
    gloss: float = 26.0                   # how concentrated the highlight is on the gun body
    env: float = 0.35                     # faint environment reflection (multiplied by the local ambient light: it vanishes in dark spots)
    normal_strength: float = 1.0          # strength of the normal map
    albedo: float = 1.25                  # multiplies the texture color: the gun texture is very dark and would lose all detail through the harsh tone curve
    sleeve_color: tuple = (0.060, 0.062, 0.058)   # sleeve color covering the forearm skin (the asset is bare skin with twisted texture)


@dataclass
class FlashData:
    """Muzzle flash (drawn in the gun scene): a star facing the camera + two crossed planes along the barrel + a point light that lights the gun and hand.
    Each shot is randomly rotated and resized slightly; it lives `life` seconds then fades (at 750 RPM the shots overlap into a continuous flicker)."""
    life: float = 0.055                   # s
    size: float = 0.21                    # m: star diameter (in the gun scene; muzzle is 0.73 m from the eye)
    size_jitter: float = 0.25             # +- random size ratio per shot
    length: float = 0.20                  # m: length of the two crossed planes along the barrel
    width: float = 0.07                   # m: width of the two crossed planes
    forward: float = 0.025                # m: nudged forward of the muzzle so it is not buried in the flash hider
    color: tuple = (1.0, 0.86, 0.52)
    ads_scale: float = 0.35               # when fully aimed, the flash is only this size (so it does not hide the sights)
    light_color: tuple = (1.0, 0.62, 0.28)
    light_power: float = 1.5              # multiplies the light color at its brightest
    light_attenuation: tuple = (1.0, 0.0, 40.0)   # constant, linear, and quadratic (per meter) terms: lit up to ~0.3 m around the muzzle
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
    body_omega: float = 7.0               # rad/s: body spring: smaller = the body arrives later
    body_zeta: float = 0.75
    # footsteps when WALKING (same phase as Sway.phase, i.e. same rhythm as the footstep sounds). Bodycam-style sway: visible but not nauseating
    step_y: float = 0.020                 # m: bob (the -2 cm trough lands exactly when the foot touches the ground; the peak is lower because the trough is sharp)
    step_x: float = 0.010                 # m: sideways sway with the supporting leg
    step_roll: float = 1.1                # deg: left-right roll with the step rhythm
    step_pitch: float = 0.7               # deg: nod with each step
    step_yaw: float = 0.4                 # deg: head turns with the shoulders
    step_sharp: float = 0.6               # 0 = sine bob; 1 = sharp trough like a stomp
    step_crouch: float = 0.55             # crouch-walking: multiplies the step amplitude + hand shake
    step_min_speed: float = 1.5           # m/s: below this the amplitude shrinks to 0
    step_blend: float = 8.0               # 1/s: amplitude slides to the new level
    # sprinting: its own amplitude set (blended smoothly with the walk set by `sprint_blend`)
    sprint_y: float = 0.030
    sprint_x: float = 0.016
    sprint_roll: float = 2.6              # deg: strong left-right roll with the step rhythm
    sprint_pitch: float = 1.3
    sprint_yaw: float = 0.9
    sprint_lean: float = 1.5              # deg: extra forward lean (added to move_pitch by speed)
    sprint_blend: float = 5.0             # 1/s
    # high-frequency hand / machine vibration: smooth noise, grows with speed, strongest when sprinting
    jitter_angle: float = 0.5             # deg (pitch; yaw x0.8; roll x1.2) when sprinting
    jitter_pos: float = 0.0015            # m
    jitter_walk: float = 0.3              # walking: this much remains
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
    glance_in_time: float = 0.32          # s to fully tilt down
    glance_out_lead: float = 0.25         # s BEFORE Clip.settle the head starts to come up (at the same time the reload view fades out)
    glance_out_time: float = 0.38         # s to fully come up: back to 0 about 0.5 s before the gun is ready to fire
    glance_cancel_time: float = 0.2       # s: when reloading is cancelled the head comes back within this time
    glance_drift: float = 1.0             # deg: the eye drifts slightly while looking
    glance_drift_freq: float = 0.5        # Hz
    glance_seat_nod: float = 1.2          # deg: small nod when the magazine seats (Clip.swap)
    glance_follow: float = 1.0            # the gun follows the glance part (sign flipped): 1 = the gun stays still relative to the body and moves up to the middle of the frame on screen


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
        'draw': Clip('Draw', 269, 299),
    },
    # measured from the model's peaks (tools/measure/g4_ads_align.py): center of the rear aperture and top of the front post
    ads_sights=((0.0678, -0.0074, 0.1556), (0.0678, -0.0069, 0.5622)),
    muzzle=(0.0677, -0.0752, 0.7326),
    shot_sound=('assets/sounds/el_shot_0.wav', 'assets/sounds/el_shot_1.wav', 'assets/sounds/el_shot_2.wav'),
)


@dataclass
class FeedbackParams:
    """Feedback on bullet hits: bullet holes."""
    hole_base_size: float = 0.05          # m; a real 5.56 mm hole is too small to see, so it is enlarged
    hole_size_per_meter: float = 0.002    # holes grow with distance (150 m: ~0.35 m)
    max_holes: int = 200                  # past this, the oldest hole is reused


@dataclass
class LookData:
    """Visual look of the world (shader assets/shaders/world.*) and the screen overlay. Directions are in world space (y up, z forward).
    A flat slab of plain white ground under an open sky: one sun (no shadows) plus a flat ambient term; distant ground sinks into the fog."""
    sun_dir: tuple = (0.35, 0.80, -0.30)      # direction TOWARD the sun (normalized in code)
    sun_color: tuple = (1.45, 1.45, 1.45)     # sunlight colour x intensity (neutral white, so the white ground stays white)
    ambient_up: tuple = (0.33, 0.34, 0.36)    # sky light on upward-facing surfaces (the ground)
    ambient_down: tuple = (0.11, 0.11, 0.11)  # light bounced from the ground onto downward-facing surfaces
    exposure: float = 1.0                     # multiplies the auto exposure (LensData); the ACES tone curve is shared by the world and the gun
    fog_color: tuple = (0.50, 0.57, 0.66)     # haze, also the sky colour behind the far edge of the ground
    fog_density: float = 0.0040               # exp: ~33% at 100 m, ~55% at 200 m
    ground_color: tuple = (1.0, 1.0, 1.0)     # pure white ground (decided by the user)
    detail_strength: float = 0.0              # strength of the noise on the ground (0 = plain, one flat colour)
    # a thin grid on the ground: on a plain white floor there is nothing to show that the player is moving
    grid_strength: float = 0.85               # how dark the lines are (0 = no grid)
    grid_spacing: float = 2.0                 # m between two thin lines
    grid_major: int = 5                       # every this many lines one is drawn heavier (5 x 2 m = a 10 m square)
    grid_width: float = 0.03                  # m: half the width of a thin line (a heavy line is twice as wide)


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
    noise: float = 0.030                  # sensor noise, stronger in dark areas
    bloom: float = 0.45                   # bright areas bloom outward; 0 = off (cheaper)
    bloom_threshold: float = 0.72         # only brightness above this blooms
    contrast: float = 1.10                # > 1: darker darks, brighter brights
    saturation: float = 0.70              # 1 = keep color, 0 = grayscale
    tint: tuple = (1.0, 1.0, 0.93)        # the sickly yellow cast of cheap cameras
    auto_exposure: float = 0.55           # 0 = fixed exposure, 1 = fully compensated for the brightness of the scene
    exposure_key: float = 0.70            # local brightness that corresponds to exposure 1
    exposure_min: float = 0.55
    exposure_max: float = 2.2


@dataclass(frozen=True)
class SoundCue:
    """One sound tied to a clip frame: plays when the clip reaches `frame` (absolute frame on the glb timeline, like Clip.swap)."""
    frame: int
    sound: str                            # group name in assets/sounds/foley (tools/build/prep_foley.py): file <sound>_<number>.wav
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


# Glock 17 sound beats (absolute frames on the glb timeline, like M4_SOUND_CUES), measured by posing every 2nd frame and tracking the magazines and the slide
# (the old magazine = node Mag1, the spare = Mag2; Mag2 ends up seated in the gun and the 'done' event snaps back to the Idle pose, which has Mag1 seated):
#   Reload (1..84): release press ~19 (Mag1 starts leaving), old magazine 20 cm out at 29, spare magazine seated at 45 (= Clip.swap)
#   ReloadEmpty (107..197): slide locked back; release ~126, old magazine out at 135, spare magazine seated at 151 (= Clip.swap), SLIDE RELEASE at 164-165 (slide jumps forward)
GLOCK_SOUND_CUES = {
    'reload': (SoundCue(19, 'pistol_mag_release', 1.0), SoundCue(29, 'pistol_mag_drop', 0.6), SoundCue(42, 'pistol_mag_in', 0.8), SoundCue(45, 'pistol_mag_seat', 1.0)),
    'reload_empty': (SoundCue(126, 'pistol_mag_release', 1.0), SoundCue(135, 'pistol_mag_drop', 0.6), SoundCue(148, 'pistol_mag_in', 0.8), SoundCue(151, 'pistol_mag_seat', 1.0),
                     SoundCue(164, 'pistol_slide_release', 1.0)),
    'draw': (SoundCue(214, 'pistol_draw', 0.8), SoundCue(230, 'pistol_draw_settle', 0.6)),
    'holster': (SoundCue(200, 'pistol_holster', 0.8),),
}
GLOCK_SOUND_FILES = {
    'pistol_mag_release': 'el_pistol_mag_release', 'pistol_mag_drop': 'el_pistol_mag_drop', 'pistol_mag_in': 'el_pistol_mag_in',
    'pistol_mag_seat': 'el_pistol_mag_seat', 'pistol_slide_release': 'el_pistol_slide_release', 'pistol_draw': 'el_pistol_draw',
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
        'draw': Clip('Draw', 212, 245),
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
                     back_peak=-0.050, back_random=0.004, back_omega=16.0, back_zeta=0.7),
    shot_sound=('assets/sounds/el_pistol_shot_0.wav', 'assets/sounds/el_pistol_shot_1.wav', 'assets/sounds/el_pistol_shot_2.wav'),
    shot_pool=4,
    hip_offset=(0.0, 0.0, 0.15),           # push the whole viewmodel forward a little: the pack's hands sit close to the eye
    ads_eye_relief=0.50,
    shake=ShakeData(reload_beats={'reload': ((29, 'mag_out'), (45, 'seat')), 'reload_empty': ((135, 'mag_out'), (151, 'seat'), (164, 'bolt'))}),
    # measured with tools/measure/g8_measure.py (camera frame at rest, hip_offset not included)
    ads_sights=((0.0612, -0.0226, 0.2502), (0.0612, -0.0199, 0.4209)),
    muzzle=(0.0612, -0.0410, 0.4278),
)

GUNS = {'m4': M4, 'glock': GLOCK}


@dataclass
class AudioData:
    """Foley: metal sounds when reloading / drawing the gun (timed to the animation frames) and footsteps on tiles (timed by distance travelled). Sounds built with tools/build/prep_foley.py.
    Volume is lower than the gunshot (GunData.shot_volume 0.8) so it does not mask the shot."""
    folder: str = 'assets/sounds/foley'
    pool: int = 2                         # rotating playback copies per file: a later sound does not cut off the tail of the previous one
    # logical sound name -> real file group in folder (<group>_<number>.wav). Default uses sounds generated with ElevenLabs (tools/build/prep_elevenlabs.py from assets/sounds/source/elevenlabs).
    # To go back to the user-supplied sounds used earlier: change el_* to user_* (mag_release, mag_in, mag_seat, bolt, step). Deleting one line falls back to the synthesized sound for that name (tools/build/prep_foley.py).
    sound_files: dict = field(default_factory=lambda: {
        'mag_release': 'el_mag_release', 'mag_in': 'el_mag_in', 'mag_seat': 'el_mag_seat',
        'bolt_tick': 'el_bolt', 'bolt_release': 'el_bolt',
        'draw_a': 'el_draw_a', 'draw_b': 'el_draw_b', 'settle': 'el_settle',
        'step_walk': 'el_step', 'step_run': 'el_step', 'land': 'el_land', 'jump': 'el_jump',
        'dry': 'el_dry', 'hit_hard': 'el_hit_hard', 'breath': 'el_breath'})
    # multiplies the pitch when playing a logical name (running shares the walking file, slightly higher)
    pitch_scale: dict = field(default_factory=lambda: {'step_run': 1.06})
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
    # breathing while still (core/breath.py): one breath per breathing cycle of the sway (SwayData.breath_freq), on the same clock as the gun's bob
    breath_volume: float = 0.35
    breath_min_idle: float = 0.5          # if bob (walking / running) takes more than half, a new breath does not start
    breath_ads_scale: float = 0.5         # fully aimed: reduced to this (holding breath)


@dataclass
class GameParams:
    player: PlayerParams = field(default_factory=PlayerParams)
    gun: GunData = field(default_factory=lambda: M4)
    feedback: FeedbackParams = field(default_factory=FeedbackParams)
    look: LookData = field(default_factory=LookData)
    audio: AudioData = field(default_factory=AudioData)
    lens: LensData = field(default_factory=LensData)
