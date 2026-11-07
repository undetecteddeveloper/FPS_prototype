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
out vec4 frag_color;

void main() {
    float r2 = dot(v_corner, v_corner);
    if (r2 >= 1.0) discard;
    float soft = 1.0 - r2;
    soft *= soft;
    float s = v_puff.z * 6.2831;
    vec2 q = mat2(cos(s), -sin(s), sin(s), cos(s)) * v_corner;
    float wisp = 0.72 + 0.28 * sin(q.x * 5.1 + v_puff.z * 17.0) * sin(q.y * 4.3 + v_puff.z * 9.0);
    float dist = length(v_world - look_camera_pos);
    float fill = 1.0 - smoothstep(smoke_fill.x, smoke_fill.y, v_puff.x / max(dist, 1e-3));
    float ground = smoothstep(0.0, 0.12, v_world.y);
    float a = v_puff.y * soft * wisp * fill * ground;
    if (a < 0.004) discard;
    vec3 light = ambient_at(vec3(0.0, 1.0, 0.0)) + look_sun_color * (0.45 + 0.4 * max(look_sun_dir.y, 0.0));
    float shade = mix(0.78, 1.0, v_corner.y * 0.5 + 0.5);              // the sunlit top of a puff is brighter than its underside: gives the cloud some volume
    vec3 col = tonemap(smoke_color * light * shade);
    float fog = clamp(1.0 - exp(-smoke_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(mix(col, smoke_fog.rgb, fog), a);
}
