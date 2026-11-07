#version 140
// Dust motes (game/dust.py): positions come from a random seed and the clock only (no CPU work per frame). The motes fill a box around the eye and wrap at its sides,
// so they stay fixed in the world (parallax is right) while the player walks. A mote shows only inside a sun beam (sun_window.glsl), where it glints.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform vec3 dust_right;            // camera axes (world), shared PTAs of FrameLight
uniform vec3 dust_up;
uniform vec4 dust_params;           // x radius (m), y brightness, z box size (m), w clock (s)
in vec4 p3d_Vertex;
in vec2 corner;
in vec4 seed;                       // 0..1 random per mote

#include "light_common.glsl"
#define SUN_WINDOW_VERTEX
#include "sun_window.glsl"

out vec2 uv;
out float glow;

void main() {
    float t = dust_params.w, box = dust_params.z;
    vec3 drift = vec3(0.030, 0.006, 0.020) * t
               + 0.06 * vec3(sin(t * 0.31 + seed.w * 6.283), sin(t * 0.23 + seed.x * 6.283), cos(t * 0.27 + seed.y * 6.283));
    vec3 origin = look_camera_pos - 0.5 * box;
    vec3 p = origin + mod(seed.xyz * box + drift - origin, box);
    vec3 d = p - look_camera_pos;
    float dist = length(d);
    float edge = max(max(abs(d.x), abs(d.y)), abs(d.z));
    float fade = (1.0 - smoothstep(0.32 * box, 0.5 * box, edge)) * smoothstep(0.15, 0.5, dist);      // no popping at the box sides, none right at the eye
    glow = sun_visible(p) * fade * dust_params.y;
    if (glow < 0.005) {                                         // in the shade: invisible, so no quad at all (saves fill)
        gl_Position = vec4(0.0, 0.0, -2.0, 1.0);
        uv = vec2(0.0);
        return;
    }
    float r = max(dust_params.x, dist * 0.0011);                // never thinner than about one pixel (no shimmering)
    glow *= (dust_params.x / r) * (dust_params.x / r);          // same light spread over a bigger dot
    vec3 q = p + (dust_right * corner.x + dust_up * corner.y) * r;
    gl_Position = p3d_ModelViewProjectionMatrix * vec4(q, 1.0);
    uv = corner;
}
