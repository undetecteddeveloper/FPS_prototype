"""Sky dome with drifting clouds: one sphere around the camera, drawn first (background bin, no depth), coloured by assets/shaders/sky.vert|frag.

The dome ignores the camera position (the vertex shader applies only the camera rotation), so it never needs to follow the player; the only per-frame input is the clock that moves the clouds.
"""
from panda3d.core import OmniBoundingVolume
from ursina import Entity

from fps.game.shaders import load_glsl

CLOUD_CLOCK_SPEED = 1.0          # multiplies the drift of the clouds (1 = a slow drift: a full noise tile takes ~3 minutes)


class Sky:
    def __init__(self):
        self.entity = Entity(model='sphere', scale=10.0, add_to_scene_entities=False)
        e = self.entity
        e.setShader(load_glsl('sky'), 1)
        e.set_two_sided(True)
        e.set_depth_write(False)
        e.set_depth_test(False)
        e.set_light_off()
        e.set_bin('background', 0)
        for geom in e.find_all_matches('**/+GeomNode'):         # the vertex shader moves it: never cull it
            geom.node().set_bounds(OmniBoundingVolume())
            geom.node().set_final(True)
        self.clock = 0.0
        e.set_shader_input('sky_time', 0.0)

    def update(self, dt: float):
        self.clock += dt * CLOUD_CLOCK_SPEED
        self.entity.set_shader_input('sky_time', float(self.clock))
