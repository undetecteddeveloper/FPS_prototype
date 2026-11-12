#version 140
// G18 enemies (capsules) and door leaves. Lit by the BAKED ambient light where they stand (game/enemies.py samples the floor's AmbientGrid each frame, like the gun),
// plus the muzzle flash; the shared tone curve, haze and underwater fog of the room. Enemies have two eyes on the front that flare during the wind-up (the telegraph)
// and turn white for a moment when a bullet hits. A dead one dissolves (dithered discard) while it sinks.
uniform vec4 look_fog;
uniform vec2 look_flash_world;
uniform vec4 enemy_color;          // rgb albedo (linear), a = 1: draw the eyes (enemies), 0: a door
uniform vec4 enemy_shape;          // radius, height, eye height, -
uniform vec4 enemy_state;          // x hit flash 0..1, y wind-up glow 0..1, z visible share 1..0 (dissolve), w -
uniform vec4 enemy_amb_up;         // baked ambient light at its spot (up-facing surfaces)
uniform vec4 enemy_amb_down;

#include "light_common.glsl"
#include "underwater.glsl"

in vec3 world_pos;
in vec3 world_n;
in vec3 local_pos;
out vec4 frag_color;

float hash12(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    if (enemy_state.z < 0.999 && hash12(floor(gl_FragCoord.xy)) > enemy_state.z) discard;
    vec3 n = normalize(world_n);
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 V = to_cam / max(dist, 1e-4);
    if (dot(n, V) < 0.0) n = -n;
    vec3 amb = mix(enemy_amb_down.rgb, enemy_amb_up.rgb, n.y * 0.5 + 0.5);
    float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0);
    vec3 lit = enemy_color.rgb * amb * (1.0 + 0.35 * rim);
    if (look_flash_color.r > 0.0) lit += enemy_color.rgb * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;
    vec3 color = tonemap(lit);
    if (enemy_color.a > 0.5) {
        float r = enemy_shape.x;
        vec2 side = vec2(abs(local_pos.x) - r * 0.32, local_pos.y - enemy_shape.z);
        float eye = (1.0 - smoothstep(r * 0.10, r * 0.16, length(side))) * step(r * 0.55, local_pos.z);
        vec3 glow = mix(vec3(0.55, 0.50, 0.42), vec3(1.6, 0.18, 0.08), enemy_state.y);
        color = mix(color, glow, eye * (0.55 + 0.45 * enemy_state.y));
    }
    color = mix(color, vec3(0.95, 0.92, 0.88), enemy_state.x * 0.75);
    bool under = pixel_wet();
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(under ? under_fog(color, dist) : mix(color, look_fog.rgb, fog), 1.0);
}
