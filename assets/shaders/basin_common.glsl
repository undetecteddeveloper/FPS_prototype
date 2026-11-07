// SHARED (water.frag, basin.frag): how a point of the pool basin (floor, slope, steps, walls under the water) is lit. G10 shaded it only at the end of a refracted ray
// traced from the surface; G12 also draws the basin as real geometry (basin.frag) for the camera under the water, with the SAME shading, so both views agree.
// Include AFTER light_common.glsl and sun_window.glsl. The water node owns these inputs; the basin node is its child and inherits them.
uniform vec4 water_quality;         // x wave simulation, y see the bottom, z caustics, w sun sparkle (0 / 1 each; graphics level, F2)
uniform vec4 water_basin_lo;        // the water volume: (x0, floor, z0)
uniform vec4 water_basin_hi;        //                    (x1, surface, z1)
uniform vec4 water_ramp;            // the sloping bottom: z0, z1, y at z0, y at z1 (shallow shelf before z0, deep floor after z1; core/poolmap.py PoolMap.ramp)
uniform vec4 water_basin;           // rgb basin tile colour, a = tile size (m)
uniform vec4 water_absorb;          // rgb absorption (1/m), a = basin light (multiplies the baked ambient)
uniform vec4 water_caustic;         // x sun strength, y sky share, z share of the pattern on the walls, w peak (the brightest the lines get)
uniform vec4 water_caustic2;        // x how white the bright lines turn, y ripples bending the view of the bottom, z ripples in the reflection, w -
uniform sampler2D water_caus_tex;   // brightness of the focused sunlight on the bottom (1 = flat water), over `water_caus_domain` (x0, x1, z0, z1)
uniform vec4 water_caus_domain;
uniform sampler2D water_amb_up;     // baked room ambient on the floor plan (core/poolmap.py AmbientGrid): up- and down-facing irradiance at gun height
uniform sampler2D water_amb_down;
uniform vec4 water_amb_grid;        // x0, z0, step (m), -

const float ETA = 1.0 / 1.333;

// G13: a node whose graphics flags are all those of level Low is drawn by a build with POOL_LITE defined (game/water.py, game/underwater.py; core/graphics.py
// lite_water / lite_basin): the switched-off features become compile-time false, so their code is not in the shader at all. Same picture; on Intel an unused branch
// still costs registers (narrower SIMD), measured 0.5-1 ms per frame at 1080p. Without POOL_LITE the F2 flags decide per frame, as before.
#ifdef POOL_LITE
#define Q_SIM false
#define Q_BOTTOM false
#define Q_CAUS false
#define Q_GLINT false
#define Q_FULL_UNDER false
#else
#define Q_SIM (water_quality.x > 0.5)
#define Q_BOTTOM (water_quality.y > 0.5)
#define Q_CAUS (water_quality.z > 0.5)
#define Q_GLINT (water_quality.w > 0.5)
#define Q_FULL_UNDER (look_under3.x > 0.5)
#endif

// height of the pool bottom at z (shelf / ramp / deep floor; steps ignored)
float bottom_y(float z) {
    float k = clamp((z - water_ramp.x) / (water_ramp.y - water_ramp.x), 0.0, 1.0);
    return mix(water_ramp.z, water_ramp.w, k);
}

float basin_hash(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

// tile pattern (same as room.frag): 1 on a tile, darker in the grout; fades to the average when a pixel covers a tile
float basin_tile_shade(vec2 p, float size) {
    vec2 q = p / size;
    vec2 cell = floor(q);
    vec2 edge = min(fract(q), 1.0 - fract(q));
    vec2 fw = max(fwidth(q), vec2(1e-5));
    vec2 line = 1.0 - smoothstep(vec2(0.06) - fw, vec2(0.06) + fw, edge);
    float grout = max(line.x, line.y);
    float blur = clamp(max(fw.x, fw.y) * 2.0, 0.0, 1.0);
    grout = mix(grout, 1.0 - 0.88 * 0.88, blur);
    float tone = 1.0 + (basin_hash(cell) - 0.5) * 0.12 * (1.0 - blur);
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

// linear radiance leaving the basin point `hit` (face normal `n`, toward the water): tiles x (baked room ambient through the water + refracted sun, caustics).
// `caustics` = use the caustic texture (graphics level).
vec3 shade_basin(vec3 hit, vec3 n, bool caustics) {
    vec2 metric = abs(n.y) > 0.5 ? hit.xz : (abs(n.x) > 0.5 ? hit.zy : hit.xy);
    vec3 albedo = water_basin.rgb * basin_tile_shade(metric, water_basin.a);

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
    if (caustics && Q_CAUS) {
        float c = caustic_at(hit, sun_w);
        c /= 1.0 + max(c - 1.0, 0.0) / water_caustic.w;                                // the brightest lines saturate softly instead of blowing out
        c = mix(1.0, c, n.y > 0.5 ? 1.0 : water_caustic.z);                             // walls: fainter (an approximation, see caustic_at)
        float top = max(max(albedo.r, albedo.g), albedo.b);
        sun_albedo = mix(albedo, vec3(top), water_caustic2.x * clamp((c - 1.0) / 3.0, 0.0, 1.0));   // a photo burns the bright lines to white
        sky *= mix(1.0, c, water_caustic.y);
        sun *= c * water_caustic.x;
    }
    return albedo * sky + sun_albedo * sun;
}

// G13, 'Dưới nước: Đơn giản' (level Low): the basin seen in the mirror of the surface from below (total internal reflection), without tracing the basin boxes.
// At that range the underwater fog covers most of it: the basin's average tile colour under the baked ambient, at the distance where the mirrored ray reaches the
// floor plane under the surface point (the fog uses `dist`). The full trace cost ~3.6 ms per frame at 1440 x 810 looking up from the deep end (G13).
vec3 basin_mirror_simple(vec3 p, vec3 r, out float dist) {
    dist = min((p.y - bottom_y(p.z)) / max(-r.y, 0.05), 40.0);
    vec3 hit = p + r * dist;
    return water_basin.rgb * 0.914 * grid_ambient(water_amb_up, hit.xz) * water_absorb.a;     // 0.914 = the tile pattern's average (basin_tile_shade)
}
