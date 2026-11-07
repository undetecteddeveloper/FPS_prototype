#version 140
// Pool water. The surface is a flat quad; only its SLOPE is computed and tilts the normal:
//   - graphics level Low (G9): ambient ripples + analytic rings where bullets landed (mirror of core/waves.py), dark mirror body;
//   - Mid / High (G10): the GPU wave simulation (game/water_sim.py) + faint ambient ripples, and the water is CLEAR: the refracted view ray is traced against the basin
//     (its box from inside + the step boxes; core/poolmap.py `basin_boxes`) and the tiled bottom is shaded there: baked room ambient, sun caustics, absorption on the way.
//   - G11: the caustics come from a texture drawn every frame by the light-mesh pass (game/caustics.py); the small ripples that focus the light there (pool_waves.glsl)
//     also bend the view of the tiles and, a little, the reflection.
// The reflection is the room captured once into a 3 x 2 atlas (game/pool_capture.py), looked up with a box-projected ray (mirror of core/cubemap.py). Fresnel mixes the two.
// G12, the camera at / under the surface (underwater.glsl): seen from BELOW, the surface shows the room squeezed into Snell's window (refracted, the same atlas) and outside it
// a mirror of the basin (total internal reflection); a wet pixel of the split frame seen from above already travels in the water (no refraction, underwater fog).
// RING_SLOTS and STEP_SLOTS are defined by the loader.
uniform vec4 water_look;           // x ripple strength, y ripple scale, z ripple speed, w reflection strength
uniform vec4 water_deep;            // rgb deep body colour, a = Fresnel F0
uniform vec4 water_shallow;         // rgb shallow body colour, a = how far the shallows reach (m)
uniform vec4 water_rect;            // pool: x0, x1, z0, z1
uniform vec4 water_impact;          // ring: speed, wavelength, width, life
uniform vec4 water_impact2;         // ring: strength, reach, tan(half face fov), -
uniform vec4 water_rings[RING_SLOTS];   // x, z, t0, amp
uniform vec3 water_time;            // x = clock (s), y = number of live rings (G13: they are packed first, game/water.py)
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
// --- G10 ---
uniform sampler2D water_sim_a;      // simulated height (r, metres); the latest of the two is `water_sim_pick.x`
uniform sampler2D water_sim_b;
uniform vec4 water_sim_pick;        // x = 0: A is the latest, 1: B; y = cell size (m)
uniform vec4 water_steps_lo[STEP_SLOTS];
uniform vec4 water_steps_hi[STEP_SLOTS];
uniform vec4 water_glint;           // x strength, y power, z simulated slope weight, w -

#include "light_common.glsl"
#include "sun_window.glsl"
#include "cube_reflect.glsl"
#include "pool_waves.glsl"
#include "basin_common.glsl"
#include "underwater.glsl"

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

// --- simulated height field ---
vec2 sim_uv(vec2 xz) {
    return (xz - water_rect.xz) / (water_rect.yw - water_rect.xz);
}

float sim_h(vec2 uv) {
    return water_sim_pick.x < 0.5 ? texture(water_sim_a, uv).r : texture(water_sim_b, uv).r;
}

// (slope x, slope z, laplacian) of the simulated surface at a world point
vec3 sim_slope(vec2 xz) {
    vec2 uv = sim_uv(xz);
    vec2 texel = 1.0 / vec2(textureSize(water_sim_a, 0));
    float c = sim_h(uv);
    float l = sim_h(uv - vec2(texel.x, 0.0)), r = sim_h(uv + vec2(texel.x, 0.0));
    float d = sim_h(uv - vec2(0.0, texel.y)), u = sim_h(uv + vec2(0.0, texel.y));
    vec2 cell = (water_rect.yw - water_rect.xz) * texel;
    return vec3((r - l) / (2.0 * cell.x), (u - d) / (2.0 * cell.y), (l + r + d + u - 4.0 * c) / (cell.x * cell.y));
}

// --- the basin under the water ---
vec3 safe_dir(vec3 d) {
    return mix(d, vec3(1e-6), lessThan(abs(d), vec3(1e-6)));
}

// nearest hit of the ray o + t d (o inside the water): the basin box from inside, or a step box from outside. Returns t; `n` = the face normal (toward the water)
float trace_basin(vec3 o, vec3 d, out vec3 n) {
    vec3 inv = 1.0 / safe_dir(d);
    vec3 ta = (water_basin_lo.xyz - o) * inv, tb = (water_basin_hi.xyz - o) * inv;
    vec3 tout = max(ta, tb);
    float t = min(min(tout.x, tout.y), tout.z);
    n = t == tout.x ? vec3(-sign(d.x), 0.0, 0.0) : (t == tout.y ? vec3(0.0, -sign(d.y), 0.0) : vec3(0.0, 0.0, -sign(d.z)));
    for (int i = 0; i < STEP_SLOTS; i++) {
        vec3 a = (water_steps_lo[i].xyz - o) * inv, b = (water_steps_hi[i].xyz - o) * inv;
        vec3 tin3 = min(a, b), tout3 = max(a, b);
        float tin = max(max(tin3.x, tin3.y), tin3.z);
        float tfar = min(min(tout3.x, tout3.y), tout3.z);
        if (tin <= tfar && tin > 0.0 && tin < t) {
            t = tin;
            n = tin == tin3.x ? vec3(-sign(d.x), 0.0, 0.0) : (tin == tin3.y ? vec3(0.0, -sign(d.y), 0.0) : vec3(0.0, 0.0, -sign(d.z)));
        }
    }
    // the sloping bottom between the shallow shelf and the deep end: the plane y = y0 + k (z - z0), only between z0 and z1
    float k = (water_ramp.w - water_ramp.z) / (water_ramp.y - water_ramp.x);
    float denom = d.y - k * d.z;
    if (abs(denom) > 1e-6) {
        float tr = (water_ramp.z + k * (o.z - water_ramp.x) - o.y) / denom;
        float zr = o.z + tr * d.z;
        if (tr > 0.0 && tr < t && zr >= water_ramp.x && zr <= water_ramp.y) {
            t = tr;
            n = normalize(vec3(0.0, 1.0, -k));
        }
    }
    return max(t, 0.0);
}

// linear radiance of the basin hit by the ray p + t d from inside the water (no water on the way); `dist` = the distance to it
vec3 basin_hit(vec3 p, vec3 d, out float dist) {
    vec3 n;
    dist = trace_basin(p, d, n);
    return shade_basin(p + d * dist, n, true);
}

// linear radiance coming up through the surface along the refracted ray (seen from above: the clear-water absorption and blue scattering on the way)
vec3 see_bottom(vec3 p, vec3 d) {
    float dist;
    vec3 bottom = basin_hit(p, d, dist);
    vec3 through = exp(-water_absorb.rgb * dist);
    return bottom * through + water_shallow.rgb * (1.0 - through);                   // what the water scatters on the way (blue)
}

// G12: the surface seen from under the water (display colour, before the fog of the path eye -> surface). `dir` = eye -> surface (upward), `n` = surface normal (up)
vec3 underside(vec3 p, vec3 dir, vec3 n) {
    vec3 nd = -n;                                                                   // toward the water
    vec3 r = reflect(dir, nd);
    r.y = min(r.y, -0.03);                                                           // a ripple must not send the mirror ray back up through the surface
    float dr;
    vec3 mirror = Q_FULL_UNDER ? tonemap(basin_hit(p, normalize(r), dr)) : tonemap(basin_mirror_simple(p, normalize(r), dr));   // outside Snell's window: the pool itself (total internal reflection)
    mirror = under_fog(mirror, dr);
    vec3 t = refract(dir, nd, 1.333);
    if (dot(t, t) < 1e-6) return mirror;
    float cos_t = max(t.y, 0.0);                                                     // Schlick on the air side (n1 > n2)
    float f = 0.02 + 0.98 * pow(1.0 - cos_t, 5.0);
    return mix(room_reflection(p, normalize(t)) * water_look.w, mirror, f);
}

void main() {
    float t = water_time.x;
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 v = to_cam / dist;

    vec2 slope = ambient_slope(world_pos.xz, t);
    if (Q_SIM) {
        vec3 s = sim_slope(world_pos.xz);
        slope = slope * 0.5 + s.xy * water_glint.z;
    } else {
        for (int i = 0; i < RING_SLOTS; i++) {                                           // only the live rings (an empty loop over 12 dead ones cost 0.5-0.8 ms per frame)
            if (float(i) >= water_time.y) break;
            slope += ring_slope(world_pos.xz, water_rings[i], t);
        }
    }
    vec2 ripple = Q_BOTTOM && water_caustic2.y + water_caustic2.z > 0.0 ? pool_wave(world_pos.xz, t).yz : vec2(0.0);   // the small ripples (G11), the ones that make the caustics
    ripple *= 1.0 - smoothstep(0.01, 0.05, length(fwidth(world_pos.xz)));             // far away a pixel covers several ripples: they would only sparkle
    vec2 s_top = slope + ripple * water_caustic2.z, s_under = slope + ripple * water_caustic2.y;
    vec3 n = normalize(vec3(-s_top.x, 1.0, -s_top.y));                                 // reflection, Fresnel, sparkle
    vec3 n_under = normalize(vec3(-s_under.x, 1.0, -s_under.y));                       // the view into the water

    // G12: the camera under the surface, or a wet pixel of the split frame
    // G13: two more lite builds fix what the frame already knows (game/water.py `set_view`, from game/underwater.py): VIEW_DRY = no pixel can be wet,
    // VIEW_UNDER = every pixel is wet and the eye is below the surface plane. The branch that is then never taken (the basin trace of the split frame) is not
    // compiled in: fewer registers, measured -0.54 ms per frame looking up from the deep end at 1440 x 810. Same picture as the plain lite build.
#if defined(VIEW_UNDER)
    bool below = true;
    bool wet = true;
#elif defined(VIEW_DRY)
    bool below = look_camera_pos.y < world_pos.y;
    bool wet = false;
#else
    bool below = look_camera_pos.y < world_pos.y;
    bool wet = pixel_wet();
#endif
    if (below || wet) {
        vec3 dir = -v;
        vec3 c;
        if (below && wet) {                                                          // looking up from under the water: Snell's window
            vec2 s_snell = Q_FULL_UNDER ? slope + ripple * look_under3.y : vec2(0.0);
            c = underside(world_pos, dir, normalize(vec3(-s_snell.x, 1.0, -s_snell.y)));
        } else if (below) {                                                          // the dry (upper) part of the port while the eye dips just under: the room straight on
            c = room_reflection(world_pos, dir) * water_look.w;
        } else {                                                                     // eye just above, port bottom in the water: the ray goes on through the water unbent
            float db;
            c = under_fog(tonemap(basin_hit(world_pos, dir, db)), db);
        }
        frag_color = vec4(wet ? under_fog(c, dist) : c, 1.0);
        return;
    }

    vec3 r = reflect(-v, n);
    r = normalize(vec3(r.x, max(r.y, 0.03), r.z));                                   // a ripple tilted past the horizon must not mirror the floor
    vec3 mirrored = room_reflection(world_pos, r) * water_look.w;

    float f0 = water_deep.a;
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - max(dot(n, v), 0.0), 5.0);

    vec3 body;
    if (Q_BOTTOM) {
        vec3 d = refract(-v, n_under, ETA);
        body = tonemap(see_bottom(world_pos, d));
    } else {
        float edge = min(min(world_pos.x - water_rect.x, water_rect.y - world_pos.x), min(world_pos.z - water_rect.z, water_rect.w - world_pos.z));
        float shallow = exp(-max(edge, 0.0) / max(water_shallow.a, 0.05));
        body = tonemap(mix(water_deep.rgb, water_shallow.rgb, shallow));
    }
    vec3 color = mix(body, mirrored, fresnel);

    if (Q_GLINT) {                                                                  // the sun's sparkle: a mirror image of the sun on the wave facets, only where the sun reaches the water
        float lit = sun_visible(world_pos);
        if (lit > 0.0) {
            float g = pow(max(dot(r, look_sun_dir), 0.0), water_glint.y) * water_glint.x * fresnel * lit;
            color = 1.0 - (1.0 - color) * (1.0 - tonemap(look_sun_color * g));
        }
    }
    vec3 shaft = sun_shaft(look_camera_pos, world_pos);
    color = 1.0 - (1.0 - color) * (1.0 - tonemap(shaft));
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(mix(color, look_fog.rgb, fog), 1.0);
}
