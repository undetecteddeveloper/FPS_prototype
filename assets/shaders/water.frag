#version 140
// Pool water. The surface is a flat quad; only its SLOPE is computed and tilts the normal:
//   - graphics level Low (G9): ambient ripples + analytic rings where bullets landed (mirror of core/waves.py), dark mirror body;
//   - Mid / High (G10): the GPU wave simulation (game/water_sim.py) + faint ambient ripples, and the water is CLEAR: the refracted view ray is traced against the basin
//     (its box from inside + the step boxes; core/poolmap.py `basin_boxes`) and the tiled bottom is shaded there: baked room ambient, sun caustics, absorption on the way.
//   - G11: the caustics come from a texture drawn every frame by the light-mesh pass (game/caustics.py); the small ripples that focus the light there (pool_waves.glsl)
//     also bend the view of the tiles and, a little, the reflection.
// The reflection is the room captured once into a 3 x 2 atlas (game/pool_capture.py), looked up with a box-projected ray (mirror of core/cubemap.py). Fresnel mixes the two.
// RING_SLOTS and STEP_SLOTS are defined by the loader.
uniform vec4 water_look;           // x ripple strength, y ripple scale, z ripple speed, w reflection strength
uniform vec4 water_deep;            // rgb deep body colour, a = Fresnel F0
uniform vec4 water_shallow;         // rgb shallow body colour, a = how far the shallows reach (m)
uniform vec4 water_rect;            // pool: x0, x1, z0, z1
uniform vec4 water_impact;          // ring: speed, wavelength, width, life
uniform vec4 water_impact2;         // ring: strength, reach, tan(half face fov), -
uniform vec4 water_rings[RING_SLOTS];   // x, z, t0, amp
uniform vec3 water_time;            // x = clock (s)
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
// --- G10 ---
uniform vec4 water_quality;         // x wave simulation, y see the bottom, z caustics, w sun sparkle (0 / 1 each; graphics level, F2)
uniform sampler2D water_sim_a;      // simulated height (r, metres); the latest of the two is `water_sim_pick.x`
uniform sampler2D water_sim_b;
uniform vec4 water_sim_pick;        // x = 0: A is the latest, 1: B; y = cell size (m)
uniform vec4 water_basin_lo;        // the water volume: (x0, floor, z0)
uniform vec4 water_basin_hi;        //                    (x1, surface, z1)
uniform vec4 water_ramp;            // the sloping bottom: z0, z1, y at z0, y at z1 (shallow shelf before z0, deep floor after z1; core/poolmap.py PoolMap.ramp)
uniform vec4 water_steps_lo[STEP_SLOTS];
uniform vec4 water_steps_hi[STEP_SLOTS];
uniform vec4 water_basin;           // rgb basin tile colour, a = tile size (m)
uniform vec4 water_absorb;          // rgb absorption (1/m), a = basin light (multiplies the baked ambient)
uniform vec4 water_caustic;         // x sun strength, y sky share, z share of the pattern on the walls, w peak (the brightest the lines get)
uniform vec4 water_caustic2;        // x how white the bright lines turn, y ripples bending the view of the bottom, z ripples in the reflection, w -
uniform sampler2D water_caus_tex;   // brightness of the focused sunlight on the bottom (1 = flat water), over `water_caus_domain` (x0, x1, z0, z1)
uniform vec4 water_caus_domain;
uniform vec4 water_glint;           // x strength, y power, z simulated slope weight, w -
uniform sampler2D water_amb_up;     // baked room ambient on the floor plan (core/poolmap.py AmbientGrid): up- and down-facing irradiance at gun height
uniform sampler2D water_amb_down;
uniform vec4 water_amb_grid;        // x0, z0, step (m), -

#include "light_common.glsl"
#include "sun_window.glsl"
#include "cube_reflect.glsl"
#include "pool_waves.glsl"

in vec3 world_pos;
out vec4 frag_color;

const float TWO_PI = 6.2831853;
const float ETA = 1.0 / 1.333;
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

// height of the pool bottom at z (shelf / ramp / deep floor; steps ignored)
float bottom_y(float z) {
    float k = clamp((z - water_ramp.x) / (water_ramp.y - water_ramp.x), 0.0, 1.0);
    return mix(water_ramp.z, water_ramp.w, k);
}

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

// tile pattern (same as room.frag): 1 on a tile, darker in the grout; fades to the average when a pixel covers a tile
float tile_shade(vec2 p, float size) {
    vec2 q = p / size;
    vec2 cell = floor(q);
    vec2 edge = min(fract(q), 1.0 - fract(q));
    vec2 fw = max(fwidth(q), vec2(1e-5));
    vec2 line = 1.0 - smoothstep(vec2(0.06) - fw, vec2(0.06) + fw, edge);
    float grout = max(line.x, line.y);
    float blur = clamp(max(fw.x, fw.y) * 2.0, 0.0, 1.0);
    grout = mix(grout, 1.0 - 0.88 * 0.88, blur);
    float tone = 1.0 + (hash21(cell) - 0.5) * 0.12 * (1.0 - blur);
    return mix(tone, 0.62, grout);
}

// focused sunlight at a point of the bottom or a wall: the texture is laid out where the light lands on the floor, so a point is looked up where the FLAT refracted sun ray
// through it reaches the floor (a wall point: further along the ray, beyond the wall; the domain reaches there). Mipmaps average the cells far away.
float caustic_at(vec3 hit, vec3 sun_w) {
    vec3 q = hit + sun_w * ((bottom_y(hit.z) - hit.y) / min(sun_w.y, -0.05));
    return texture(water_caus_tex, (q.xz - water_caus_domain.xz) / (water_caus_domain.yw - water_caus_domain.xz)).r;
}

vec3 grid_ambient(sampler2D tex, vec2 xz) {
    vec2 size = vec2(textureSize(tex, 0));
    vec2 uv = ((xz - water_amb_grid.xy) / water_amb_grid.z + 0.5) / size;
    return texture(tex, uv).rgb;
}

// linear radiance coming up through the surface along the refracted ray
vec3 see_bottom(vec3 p, vec3 d) {
    vec3 n;
    float dist = trace_basin(p, d, n);
    vec3 hit = p + d * dist;
    vec2 metric = abs(n.y) > 0.5 ? hit.xz : (abs(n.x) > 0.5 ? hit.zy : hit.xy);
    vec3 albedo = water_basin.rgb * tile_shade(metric, water_basin.a);

    vec3 up = grid_ambient(water_amb_up, hit.xz), down = grid_ambient(water_amb_down, hit.xz);
    vec3 sky = (n.y > 0.5 ? up : 0.5 * (up + down)) * water_absorb.a;
    float wall = min(min(hit.x - water_basin_lo.x, water_basin_hi.x - hit.x), min(hit.z - water_basin_lo.z, water_basin_hi.z - hit.z));
    float corner = n.y > 0.5 ? wall : hit.y - bottom_y(hit.z);
    sky *= 1.0 - 0.45 * exp(-max(corner, 0.0) / 0.25);                              // the corners where floor meets wall get less light

    // sunlight: refracted at the surface, it reached `hit` from the surface point `entry`; lit there only if the sun comes in through a window
    vec3 sun_w = refract(-look_sun_dir, vec3(0.0, 1.0, 0.0), ETA);
    float s = (water_basin_hi.y - hit.y) / max(-sun_w.y, 0.05);
    vec3 entry = hit - sun_w * s;
    float lit = sun_visible(entry);
    float cos_in = max(look_sun_dir.y, 0.0);
    float transmit = 1.0 - (0.02 + 0.98 * pow(1.0 - cos_in, 5.0));                  // Fresnel on the way in (the low sun loses about half)
    vec3 sun = look_sun_color * (lit * transmit * max(dot(n, -sun_w), 0.0)) * exp(-water_absorb.rgb * s);

    vec3 sun_albedo = albedo;
    if (water_quality.z > 0.5) {
        float c = caustic_at(hit, sun_w);
        c /= 1.0 + max(c - 1.0, 0.0) / water_caustic.w;                                // the brightest lines saturate softly instead of blowing out
        c = mix(1.0, c, n.y > 0.5 ? 1.0 : water_caustic.z);                             // walls: fainter (an approximation, see caustic_at)
        float top = max(max(albedo.r, albedo.g), albedo.b);
        sun_albedo = mix(albedo, vec3(top), water_caustic2.x * clamp((c - 1.0) / 3.0, 0.0, 1.0));   // a photo burns the bright lines to white
        sky *= mix(1.0, c, water_caustic.y);
        sun *= c * water_caustic.x;
    }
    vec3 bottom = albedo * sky + sun_albedo * sun;
    vec3 through = exp(-water_absorb.rgb * dist);
    return bottom * through + water_shallow.rgb * (1.0 - through);                   // what the water scatters on the way (blue)
}

void main() {
    float t = water_time.x;
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 v = to_cam / dist;

    vec2 slope = ambient_slope(world_pos.xz, t);
    if (water_quality.x > 0.5) {
        vec3 s = sim_slope(world_pos.xz);
        slope = slope * 0.5 + s.xy * water_glint.z;
    } else {
        for (int i = 0; i < RING_SLOTS; i++) slope += ring_slope(world_pos.xz, water_rings[i], t);
    }
    vec2 ripple = water_quality.y > 0.5 && water_caustic2.y + water_caustic2.z > 0.0 ? pool_wave(world_pos.xz, t).yz : vec2(0.0);   // the small ripples (G11), the ones that make the caustics
    ripple *= 1.0 - smoothstep(0.01, 0.05, length(fwidth(world_pos.xz)));             // far away a pixel covers several ripples: they would only sparkle
    vec2 s_top = slope + ripple * water_caustic2.z, s_under = slope + ripple * water_caustic2.y;
    vec3 n = normalize(vec3(-s_top.x, 1.0, -s_top.y));                                 // reflection, Fresnel, sparkle
    vec3 n_under = normalize(vec3(-s_under.x, 1.0, -s_under.y));                       // the view into the water

    vec3 r = reflect(-v, n);
    r = normalize(vec3(r.x, max(r.y, 0.03), r.z));                                   // a ripple tilted past the horizon must not mirror the floor
    vec3 mirrored = room_reflection(world_pos, r) * water_look.w;

    float f0 = water_deep.a;
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - max(dot(n, v), 0.0), 5.0);

    vec3 body;
    if (water_quality.y > 0.5) {
        vec3 d = refract(-v, n_under, ETA);
        body = tonemap(see_bottom(world_pos, d));
    } else {
        float edge = min(min(world_pos.x - water_rect.x, water_rect.y - world_pos.x), min(world_pos.z - water_rect.z, water_rect.w - world_pos.z));
        float shallow = exp(-max(edge, 0.0) / max(water_shallow.a, 0.05));
        body = tonemap(mix(water_deep.rgb, water_shallow.rgb, shallow));
    }
    vec3 color = mix(body, mirrored, fresnel);

    if (water_quality.w > 0.5) {                                                    // the sun's sparkle: a mirror image of the sun on the wave facets, only where the sun reaches the water
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
