"""Combat loop: trigger -> shot -> bullet flight -> hit test -> feedback (impact sound, bullet hole).

Bullets start at the eye position, along the direction the BARREL points (`aim_source`, see core/freeaim.py), plus a very small mechanical spread.
Each shot: take the CURRENT spread -> fire -> random recoil kick (part into the camera, the rest makes the gun drift), gun kick.
Each frame every bullet advances a segment and is hit-tested over the whole segment (swept), independent of FPS.
"""
import math
import random
from dataclasses import dataclass

from ursina import color, held_keys, mouse

from fps.core.ballistics import advance, distance_between, first_hit
from fps.core.broadphase import BoxIndex
from fps.core.freeaim import FreeAim
from fps.core.handling import Handling, Phase
from fps.core.movement import MoveState
from fps.core.recoil import CameraRecoil, GunKick
from fps.core.spread import Accuracy, random_in_cone
from fps.game.decals import HoleDecals
from fps.core.weapon import Weapon
from fps.weapon_data import GameParams

DUST_TINT = color.rgba(1.0, 0.96, 0.90, 1.0)       # a slightly warm cast on the hole atlas (alpha comes from the texture and the hole's age)
MAX_BULLET_STEP = 1.0 / 120.0      # s: largest hit-test step of a bullet (chord error g*dt^2/8 = 0.15 mm)


class Bullet:
    __slots__ = ('origin', 'pos', 'vel', 'age', 'alive', 'end_pos', 'quiet')

    def __init__(self, origin, vel, quiet: bool = False):
        self.quiet = quiet               # a pellet after the first of a shotgun shot: it still makes its hole, but the impact sound is the first pellet's only
        self.origin = origin
        self.pos = origin
        self.vel = vel
        self.age = 0.0
        self.alive = True                # False when it hit something or expired; `end_pos` is the end point (for the tracer)
        self.end_pos = origin


@dataclass
class Impact:
    """Most recent impact (for the HUD and read-back checks)."""
    point: tuple
    normal: tuple
    distance: float         # bullet path length from the eye to the hit point
    owner: object           # the Entity of the ground
    origin: tuple


@dataclass
class ShotInfo:
    """Most recent shot (for the HUD and read-back checks)."""
    view_dir: tuple         # view direction at the shot (cone centre)
    direction: tuple        # direction the bullet actually travels
    spread: float           # cone half-angle (degrees) used
    state: MoveState


class Combat:
    def __init__(self, params: GameParams, player, static_boxes: list, rng: random.Random = None,
                 audio=None, fx=None, shake=None):
        self.gun = params.gun
        self.fb = params.feedback
        self.player = player
        self.set_static_boxes(static_boxes)
        self.dynamic_boxes = []                    # G18: boxes that come and go (doors of the Backrooms level): always tested, never indexed
        self.rng = rng or random.Random()
        self.audio = audio                         # GunAudio or None (muted)
        self.fx = fx                               # Effects (muzzle flash, tracer) or None
        self.foley = None                          # Foley (impact and dry-fire sounds) or None; Game assigns it after building
        self.viewmodel = None                      # Viewmodel (plays the shot clip) or None; Game assigns it after building
        self.shake = shake                         # core.shake.Shake (image-only shake, does not change bullet direction) or None
        self.weapon = Weapon(self.gun)
        self.handling = Handling(self.gun, self.weapon)     # draw / reload
        self.reload_requested = False                       # just pressed R
        self.accuracy = Accuracy(self.gun.accuracy)
        self.recoil = CameraRecoil(self.gun.recoil, self.rng)
        self.gun_kick = GunKick(self.gun.kick, self.rng)
        self.free_aim = FreeAim(self.gun.free_aim)
        self.aim_source = None                     # function returning the barrel direction (world); None = centre of screen
        self.spread_now = self.accuracy.angle(player.state, player.ads_amount)   # for the dynamic crosshair
        self.last_shot = None
        self.decals = HoleDecals(self.fb)
        self.bullets = []
        self.pressed = False                       # just pulled the trigger (mouse-press event, used for semi-auto)
        self.require_locked_mouse = True           # do not fire once the player released the mouse with Esc
        self.last_impact = None
        self.shots_fired = 0
        self.frame_dt = 1.0 / 60.0                 # length of the frame being processed
        self.underwater = False                    # G12: the head is under the water (Game sets it each frame): the trigger does nothing
        self.on_blocked = None                     # callable(reason) when the trigger is pulled where it cannot fire: 'water' (head under the water) or 'wall' (High Ready, G14); Game shows a small line
        self.blocked_pulls = 0                     # how many trigger pulls were refused under the water / at a wall (for the checks)
        self.wall_blocked = False                  # G14: the gun is raised to High Ready (core/weaponcol.py; Game sets it each frame): the trigger does nothing, reloading still works

    def set_gun(self, gun, audio, fx, shake, viewmodel, foley, ammo=None):
        """Weapon switch: everything that belongs to the gun is rebuilt (rounds, draw/reload handling, spread, recoil, kick, free aim). Bullets in flight and holes stay.
        `ammo` = (mag, reserve, auto) remembered for this gun, or None for a fresh one."""
        self.gun = gun
        self.audio, self.fx, self.shake, self.viewmodel, self.foley = audio, fx, shake, viewmodel, foley
        self.weapon = Weapon(gun)
        if ammo is not None:
            self.weapon.mag, self.weapon.reserve, self.weapon.auto = ammo
        self.handling = Handling(gun, self.weapon)
        self.accuracy = Accuracy(gun.accuracy)
        self.recoil = CameraRecoil(gun.recoil, self.rng)
        self.gun_kick = GunKick(gun.kick, self.rng)
        self.free_aim.d = gun.free_aim              # keep the free-aim state (rest pose, drift): the new gun comes up where the old one was pointing
        self.reload_requested = False
        self.pressed = False

    def request_reload(self):
        """R key. Takes effect on the next frame if reloading is possible (see `_update_handling`)."""
        self.reload_requested = True

    def _update_handling(self, trigger: bool, mouse_ok: bool, real_dt: float):
        """Reload: advance the clip, sprint cancels the reload, start reloading (R key, or pull the trigger when the mag is empty)."""
        h, r = self.handling, self.gun.reload
        h.update(real_dt)
        if self.shake:
            self.shake.watch_reload(h.key, h.frame, 30.0 * h.speed)    # shake beats of the reload clip (mag seated, bolt); if the reload is cancelled, beats not reached yet are dropped
        sprinting = r.sprint_cancels and self.player.sprint_amount > 0
        if h.phase is Phase.RELOAD and sprinting:
            h.cancel()
        # a tube-magazine gun: a fresh click while the shells go in stops the reload and fires with the rounds already loaded (a click where the trigger is locked does nothing)
        elif (h.phase is Phase.RELOAD and self.gun.shell_reload and r.interrupt_fire and mouse_ok and self.pressed and self.weapon.mag > 0
              and not self.underwater and not self.wall_blocked):
            h.cancel()
        wants = self.reload_requested or (mouse_ok and (trigger or self.pressed) and self.weapon.mag == 0)
        self.reload_requested = False
        if wants and not sprinting:                    # no reload while sprinting: a sprint pose not yet fully lowered still counts as sprinting
            h.start_reload()
        self.player.ads_blocked = h.busy
        self.player.reloading = h.phase is Phase.RELOAD      # only a real reload narrows the free-aim zone; drawing / holstering keeps the Bodycam aim

    # --- per frame ---
    def update(self, dt: float, real_dt: float = None):
        """`dt` is clamped to 50 ms for physics; `real_dt` is the true frame time (the reload clip runs on the Panda clock)."""
        self.frame_dt = dt
        self.decals.update(dt if real_dt is None else real_dt)       # holes age on the true frame time: they live 1.5 s of the clock, not of the clamped physics step
        self._step_bullets(dt)           # old bullets advance first, new ones are spawned after (they already advanced to the end of the frame)

        mouse_ok = (mouse.locked or not self.require_locked_mouse) and not self.player.ui_open       # debug panel (F1) open: the mouse belongs to the panel
        trigger = bool(held_keys['left mouse']) and mouse_ok
        self._update_handling(trigger, mouse_ok, dt if real_dt is None else real_dt)
        # lowering the gun after a sprint (sprint-to-fire), or reloading / drawing, cannot fire yet
        ready = mouse_ok and self.player.can_fire and self.handling.can_fire and not self.underwater and not self.wall_blocked
        if (self.underwater or self.wall_blocked) and mouse_ok and self.pressed:      # G12: under the water the press is dropped (it must not fire on surfacing); G14 the same at a wall
            self.pressed = False
            self.blocked_pulls += 1
            if self.on_blocked:
                self.on_blocked('water' if self.underwater else 'wall')
        held = trigger and ready
        pressed = self.pressed and ready
        if pressed and self.foley and self.weapon.out_of_ammo:
            self.foley.on_dry_fire()
        if ready or not trigger or self.handling.busy:
            self.pressed = False                       # still holding the trigger while the gun is not ready because of sprinting: remember the press to fire when ready (dropped when reloading)
        self.accuracy.update(dt)
        ages = self.weapon.update(dt, held, pressed)
        if ages:
            origin, view_dir = self.player.aim_ray()
            if self.aim_source is not None:
                view_dir = self.aim_source()
            for age in ages:
                state, ads = self.player.state, self.player.ads_amount
                spread = self.accuracy.angle(state, ads)
                direction = random_in_cone(view_dir, spread, self.rng)
                self.last_shot = ShotInfo(view_dir, direction, spread, state)
                self._fire(origin, direction, age)
                self.accuracy.on_shot()
                gun_up, gun_right = self.recoil.on_shot(self.recoil.posture_scale(ads, self.player.crouching))
                self.free_aim.on_shot(gun_up, gun_right)
                self.gun_kick.on_shot(ads, age)
                if self.shake:
                    self.shake.on_shot(age)
                if self.audio:
                    self.audio.play_shot()
                if self.viewmodel:
                    self.viewmodel.on_shot(self.weapon.mag == 0)
        up, right = self.recoil.step(dt)
        if up or right:
            self.player.kick_view(up, right)       # after shooting: this shot already followed the view direction before the kick
        self.gun_kick.update(dt)
        self.free_aim.update(dt, self.player.turn_rate(dt))
        if self.shake:
            self.shake.update(dt)          # after all shake events of the frame (shots with an age, reload beats): handled at the right moment
        if self.fx:
            self.fx.update(dt)
        self.spread_now = self.accuracy.angle(self.player.state, self.player.ads_amount)

    def set_static_boxes(self, boxes: list):
        """The map's boxes [(lo, hi, owner)] bullets hit, with a floor-plan grid (G18): each bullet step tests only the boxes near it."""
        self.static_boxes = boxes
        self.box_index = BoxIndex(boxes)

    def _boxes(self) -> list:
        """Boxes bullets hit (whole list; `_advance` asks the grid for the few near each step)."""
        return self.static_boxes

    def _candidates(self, p0, p1) -> list:
        near = self.box_index.segment(p0, p1)
        return near + self.dynamic_boxes if self.dynamic_boxes else near

    def _fire(self, origin, direction, age: float):
        """One shot: `pellets` projectiles (1 for a rifle / pistol). The pattern is random within `pellet_spread` around `direction`; the first pellet drives the muzzle flash, the smoke and the
        sound, the next `pellet_tracers - 1` only get a tracer streak."""
        g = self.gun
        speed = g.muzzle_velocity
        count = max(1, g.pellets)
        self.shots_fired += 1
        boxes = self._boxes()
        for i in range(count):
            d = direction if count == 1 else random_in_cone(direction, g.pellet_spread, self.rng, g.pellet_center_bias)
            bullet = Bullet(origin, tuple(c * speed for c in d), quiet=i > 0)
            if self.fx:
                if i == 0:
                    self.fx.on_shot(bullet, self.player.ads_amount)
                elif i < g.pellet_tracers:
                    self.fx.on_pellet(bullet)
            # the bullet is spawned at time (end of frame - age) and then advances itself to the end of the frame
            if self._advance(bullet, age, boxes):
                self.bullets.append(bullet)

    def _step_bullets(self, dt: float):
        if not self.bullets:
            return
        boxes = self._boxes()
        self.bullets = [b for b in self.bullets if self._advance(b, dt, boxes)]

    def _advance(self, bullet: Bullet, dt: float, boxes: list) -> bool:
        """Advance the bullet by dt seconds. Returns False if the bullet is gone (it hit something or expired).

        A long frame is split into steps <= MAX_BULLET_STEP: the hit point of each step is found on the chord, so the error is at most g*dt^2/8 versus
        the true arc; a 40 ms hitch (e.g. the first frame that shows the muzzle flash) gives 2-3 mm error at 10 m without splitting."""
        steps = max(1, math.ceil(dt / MAX_BULLET_STEP - 1e-9))
        step = dt / steps
        for _ in range(steps):
            new_pos, new_vel = advance(bullet.pos, bullet.vel, self.gun.bullet_gravity, step, self.gun.bullet_drag)
            hit = first_hit(bullet.pos, new_pos, self._candidates(bullet.pos, new_pos), ground_y=None)       # the ground is a finite slab among the boxes, not an infinite plane
            if hit:
                bullet.alive, bullet.end_pos = False, hit.point
                self._on_hit(bullet, hit)
                return False
            bullet.pos, bullet.vel = new_pos, new_vel
        bullet.age += dt
        if bullet.age >= self.gun.bullet_lifetime:
            bullet.alive, bullet.end_pos = False, bullet.pos
            return False
        return True

    # --- feedback ---
    def _on_hit(self, bullet: Bullet, hit):
        distance = distance_between(bullet.origin, hit.point)
        self.last_impact = Impact(hit.point, hit.normal, distance, hit.owner, bullet.origin)
        if getattr(hit.owner, 'is_water', False):
            hit.owner.splash(hit.point, distance)        # water: a ring spreads (and a splash sound if it has one); no bullet hole, no dust sound
            return
        if self.foley and not bullet.quiet:
            self.foley.on_impact(distance)
        self.decals.add(hit.point, hit.normal, distance, tint=DUST_TINT)
