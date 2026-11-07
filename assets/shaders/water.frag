#version 140
// Pool water: a dark mirror. The surface is flat; only its SLOPE is computed (ambient ripples + rings where bullets landed, mirrors core/waves.py) and tilts the normal, which bends the reflection.
// The reflection is the room captured once into a 3 x 2 atlas (game/pool_capture.py), looked up with a box-projected ray (parallax corrected, mirrors core/cubemap.py).
// Colour = Fresnel mix of the mirrored room and a dark body colour (teal in the shallows), then the shared tone curve is already applied to the body; the capture is already tone-mapped.
// RING_SLOTS is defined by the loader (WaterData.ripple_slots).
uniform sampler2D water_reflect;
uniform vec3 water_axes[18];        // per cube face f: [3f] forward, [3f + 1] right, [3f + 2] up
uniform vec4 water_box_lo;          // the room box (xyz) the reflected ray is intersected with
uniform vec4 water_box_hi;
uniform vec4 water_probe;           // where the room was captured from (xyz)
uniform vec4 water_look;            // x ripple strength, y ripple scale, z ripple speed, w reflection strength
uniform vec4 water_deep;            // rgb deep body colour, a = Fresnel F0
uniform vec4 water_shallow;         // rgb shallow body colour, a = how far the shallows reach (m)
uniform vec4 water_rect;            // pool: x0, x1, z0, z1
uniform vec4 water_impact;          // ring: speed, wavelength, width, life
uniform vec4 water_impact2;         // ring: strength, reach, tan(half face fov), -
uniform vec4 water_rings[RING_SLOTS];   // x, z, t0, amp
uniform vec3 water_time;            // x = clock (s)
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)

#include "light_common.glsl"

in vec3 world_pos;
out vec4 frag_color;

const float TWO_PI = 6.2831853;
// (direction angle, wavelength, slope weight, speed factor): the same table as core/waves.py AMBIENT
const vec4 AMBIENT[5] = vec4[5](vec4(0.35, 2.10, 1.00, 1.0), vec4(1.90, 1.30, 0.80, 0.8), vec4(-0.90, 0.70, 0.60, 1.2), vec4(2.70, 0.42, 0.45, 1.5), vec4(-2.20, 0.27, 0.30, 1.8));
const float AMBIENT_WEIGHT = 3.15;

vec2 ambient_slope(vec2 p, float t) {
    vec2 s = vec2(0.0);
    for (int i = 0; i < 5; i++) {
        vec4 a = AMBIENT[i];
        float k = TWO_PI / (a.y * water_look.y);
        float omega = water_look.z * a.w * sqrt(9.81 * k) * 0.35;
        vec2 d = vec2(cos(a.x), sin(a.x));
        s += water_look.x * a.z / AMBIENT_WEIGHT * cos(k * dot(p, d) - omega * t) * d;
    }
    return s;
}

vec2 ring_slope(vec2 p, vec4 ring, float t) {
    float age = t - ring.z;
    if (age < 0.0 || age >= water_impact.w) return vec2(0.0);
    vec2 d = p - ring.xy;
    float r = length(d);
    if (r < 1e-6) return vec2(0.0);
    float front = water_impact.x * age;
    float q = (r - front) / water_impact.z;
    float fade = 1.0 - age / water_impact.w;
    fade *= fade;
    float s = ring.w * water_impact2.x * exp(-q * q) * cos(TWO_PI / water_impact.y * (r - front)) * exp(-r / water_impact2.y) * fade;
    s *= r / (r + 0.05);
    return s * d / r;
}

// where the reflected ray lands on the room box, seen from the capture probe
vec3 box_project(vec3 p, vec3 r) {
    r = mix(r, vec3(1e-5), lessThan(abs(r), vec3(1e-5)));
    vec3 t = max((water_box_hi.xyz - p) / r, (water_box_lo.xyz - p) / r);       // per axis: the distance at which the ray leaves the box
    return p + r * min(min(t.x, t.y), t.z) - water_probe.xyz;
}

vec2 cube_uv(vec3 d) {
    int best = 0;
    float best_dot = -2.0;
    for (int f = 0; f < 6; f++) {
        float x = dot(d, water_axes[f * 3]);
        if (x > best_dot) { best_dot = x; best = f; }
    }
    vec3 fw = water_axes[best * 3], rt = water_axes[best * 3 + 1], up = water_axes[best * 3 + 2];
    vec2 uv = 0.5 + 0.5 * vec2(dot(d, rt), dot(d, up)) / (dot(d, fw) * water_impact2.z);
    return vec2((float(best % 3) + uv.x) / 3.0, (float(best / 3) + uv.y) / 2.0);
}

void main() {
    float t = water_time.x;
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 v = to_cam / dist;

    vec2 slope = ambient_slope(world_pos.xz, t);
    for (int i = 0; i < RING_SLOTS; i++) slope += ring_slope(world_pos.xz, water_rings[i], t);
    vec3 n = normalize(vec3(-slope.x, 1.0, -slope.y));

    vec3 r = reflect(-v, n);
    r = normalize(vec3(r.x, max(r.y, 0.03), r.z));                                   // a ripple tilted past the horizon must not mirror the floor
    vec3 mirrored = texture(water_reflect, cube_uv(box_project(world_pos, r))).rgb * water_look.w;

    float f0 = water_deep.a;
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - max(dot(n, v), 0.0), 5.0);

    float edge = min(min(world_pos.x - water_rect.x, water_rect.y - world_pos.x), min(world_pos.z - water_rect.z, water_rect.w - world_pos.z));
    float shallow = exp(-max(edge, 0.0) / max(water_shallow.a, 0.05));
    vec3 body = tonemap(mix(water_deep.rgb, water_shallow.rgb, shallow));

    vec3 color = mix(body, mirrored, fresnel);
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(mix(color, look_fog.rgb, fog), 1.0);
}
