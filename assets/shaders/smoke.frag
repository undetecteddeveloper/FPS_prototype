#version 140
// Gun smoke puff: soft round edge, a few wisps (cheap sines rotated per puff, no texture), lit by the same sun / sky and tone curve as the world (light_common.glsl),
// blended into the haze with distance. Cheap on purpose (integrated graphics): a puff that covers a big part of the view fades out by its angular size,
// a puff meeting the ground fades out at y = 0 (soft contact, no depth texture), and nearly transparent pixels are discarded.
uniform vec3 smoke_color;
uniform vec4 smoke_fog;         // rgb = haze colour, a = density (exp)
uniform vec2 smoke_fill;        // radius / distance where the fade starts, where it is gone

#include "light_common.glsl"

in vec2 v_corner;
in vec3 v_puff;
in vec3 v_world;
in vec2 v_wisp;                 // G13: rotation and light moved to smoke.vert (same values; the per-pixel cos / sin / light cost ~0.2 ms while firing)
flat in vec3 v_lit;
#ifdef SMOKE_LITE
in vec4 v_col;                  // G13 'Khói súng: Đơn giản' (level Low): colour, haze and size fade come from the corners (smoke.vert); -0.38 ms per frame while firing
#endif
out vec4 frag_color;

void main() {
    float r2 = dot(v_corner, v_corner);
    if (r2 >= 1.0) discard;
    float soft = 1.0 - r2;
    soft *= soft;
    vec2 q = v_wisp;
    float wisp = 0.72 + 0.28 * sin(q.x * 5.1 + v_puff.z * 17.0) * sin(q.y * 4.3 + v_puff.z * 9.0);
    float ground = smoothstep(0.0, 0.12, v_world.y);
#ifdef SMOKE_LITE
    float a = v_puff.y * soft * wisp * v_col.a * ground;
    if (a < 0.004) discard;
    frag_color = vec4(v_col.rgb, a);
#else
    float dist = length(v_world - look_camera_pos);
    float fill = 1.0 - smoothstep(smoke_fill.x, smoke_fill.y, v_puff.x / max(dist, 1e-3));
    float a = v_puff.y * soft * wisp * fill * ground;
    if (a < 0.004) discard;
    float shade = mix(0.78, 1.0, v_corner.y * 0.5 + 0.5);              // the sunlit top of a puff is brighter than its underside: gives the cloud some volume
    vec3 col = tonemap(v_lit * shade);
    float fog = clamp(1.0 - exp(-smoke_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(mix(col, smoke_fog.rgb, fog), a);
#endif
}
