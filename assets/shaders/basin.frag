#version 140
// G12: the pool basin (floor, slope, steps, walls under the surface) seen by a camera under the water. Lit exactly like the bottom seen through the surface from above
// (basin_common.glsl shade_basin: baked room ambient, refracted sun, caustics), then the underwater fog of the path to the eye (underwater.glsl).
// A dry pixel (the upper part of the port while the eye dips just under) would see the room above the water: the captured room atlas along the view ray.
// The node is a child of the water node and inherits all water_* inputs.
#include "light_common.glsl"
#include "sun_window.glsl"
#include "cube_reflect.glsl"
#include "basin_common.glsl"
#include "underwater.glsl"

uniform vec4 water_shallow;        // rgb = what the clear water scatters on the way (blue)

in vec3 world_pos;
in vec3 world_normal;
out vec4 frag_color;

void main() {
    vec3 to_eye = look_camera_pos - world_pos;
    float dist = length(to_eye);
    if (!pixel_wet()) {
        vec3 dir = -to_eye / max(dist, 1e-4);
        if (look_under_abs.a > 0.5 && dir.y > -0.05) {              // eye under, port top dry: the room above the surface
            frag_color = vec4(room_reflection(look_camera_pos, dir), 1.0);
            return;
        }
        vec3 through = exp(-water_absorb.rgb * dist);               // seen from just above (rare: a gap at the pool edge): clear water
        frag_color = vec4(tonemap(shade_basin(world_pos, normalize(world_normal), true) * through + water_shallow.rgb * (1.0 - through)), 1.0);
        return;
    }
    vec3 c = tonemap(shade_basin(world_pos, normalize(world_normal), Q_FULL_UNDER));
    frag_color = vec4(under_fog(c, dist), 1.0);
}
