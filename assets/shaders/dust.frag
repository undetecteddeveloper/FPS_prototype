#version 140
// Dust mote: a soft dot of sunlight, added on top of the scene.
#include "light_common.glsl"
#include "underwater.glsl"

in vec2 uv;
in float glow;
out vec4 frag_color;

void main() {
    float a = glow * (1.0 - smoothstep(0.2, 1.0, length(uv)));
    if (a < 0.003) discard;
    if (pixel_wet()) discard;                       // G12: air particles are not seen through the water
    frag_color = vec4(tonemap(look_sun_color * 0.9) * a, 1.0);
}
