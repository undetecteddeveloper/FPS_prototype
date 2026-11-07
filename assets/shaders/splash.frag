#version 140
// Water droplets: a soft bright streak; lit by the room's ambient around the player and, inside a sun beam, by the sun (drops glint gold in the beams).
uniform vec4 look_fog;

#include "light_common.glsl"
#include "underwater.glsl"

in vec2 uv;
in float alpha;
in float sunlit;
out vec4 frag_color;

void main() {
    float r = length(uv);
    float a = alpha * (1.0 - smoothstep(0.35, 1.0, r));
    if (a < 0.01) discard;
    vec3 light = look_ambient_up * 1.6 + look_sun_color * (sunlit * 1.4);
    if (pixel_wet()) discard;                       // G12: air particles are not seen through the water
    frag_color = vec4(tonemap(light * 0.85), a * 0.75);
}
