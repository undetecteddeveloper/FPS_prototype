#version 140
// Pool hall surface: colour = tile albedo x BAKED irradiance (lightmap: sun patches, bounce, sky through the windows; core/lightbake.py) + the muzzle flash, then the shared tone curve.
// Tiles come from two procedural textures (tools/build/make_surface_textures.py): a colour multiplier (glaze, grit, grout) and a RELIEF (R height, G / B normal x / y) of a few tiles that repeats;
// they are laid by the metric coordinates, so grout joints fall on multiples of the tile size and line up across neighbouring faces; a little brightness change from tile to tile is added here.
// Surface detail (F2 'Chi tiết bề mặt', look_surface.x): 0 colour only, 1 + normal map (a fixed key light because the baked light has no direction, and the muzzle flash), 2 + parallax occlusion
// (the grout really looks sunk in; only within ~11 m, fading out). With POOL_LITE the relief code is compiled out (the graphics level is Low = flat).
// Every custom uniform has the look_ / room_ prefix (see world.frag for why).
uniform sampler2D room_lightmap;
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
uniform vec4 room_params;           // x = irradiance that is 255 in the lightmap (stored with gamma 2)
uniform vec2 look_flash_world;      // multiplies the muzzle-flash brightness onto the world, falloff

uniform vec4 room_quality;          // x = wet deck on (graphics level), yzw unused
uniform vec4 room_wet;              // x puddles 0..1, y puddle size (m), z damp reach from the pool edge (m), w reflection strength
uniform vec4 room_wet2;             // x darkening of a wet tile, y footprint life (s)
uniform vec4 room_pool;             // pool rectangle x0, x1, z0, z1 (the deck around it gets wet)
uniform vec4 room_prints[24];       // wet footprints: x, z, t0, yaw + 10 * round(strength * 100) (core/footprints.py)
uniform sampler2D room_tile_color;  // deck tile: 2 x 2 tiles of 30 cm (colour multiplier / TILE_GAIN)
uniform sampler2D room_tile_relief;
uniform sampler2D room_wall_color;  // wall / ceiling mosaic: 4 x 4 tiles of 10 cm
uniform sampler2D room_wall_relief;
uniform vec4 look_surface;          // x surface detail 0 / 1 / 2, y depth of the deck joints (m), z of the wall joints (m), w normal-map strength
// G13: with POOL_LITE (wet deck, shafts and surface relief off, as on level Low; core/graphics.py lite_room) the wet and relief code is compiled out; see basin_common.glsl
#ifdef POOL_LITE
#define Q_WET false
#define Q_SURFACE false
#define Q_PARALLAX false
#else
#define Q_WET (room_quality.x > 0.5)
#define Q_SURFACE (look_surface.x > 0.5)
#define Q_PARALLAX (look_surface.x > 1.5)
#endif
const float TILE_GAIN = 1.25;       // tools/build/make_surface_textures.py TILE_GAIN: the colour PNG holds the multiplier / 1.25

#include "light_common.glsl"
#include "sun_window.glsl"
#include "cube_reflect.glsl"
#include "underwater.glsl"

in vec4 vertex_color;
in vec2 metric;
in vec2 lightmap_uv;
in vec3 world_pos;
out vec4 frag_color;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

float value_noise2(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1, 0)), f.x), mix(hash21(i + vec2(0, 1)), hash21(i + vec2(1, 1)), f.x), f.y);
}

// how wet the deck is here: 0 dry .. 1 standing water (puddles, the damp band along the pool edge, wet footprints)
float deck_wetness(vec2 p, float t, out float puddle) {
    vec2 d = max(vec2(room_pool.x - p.x, room_pool.z - p.y), vec2(p.x - room_pool.y, p.y - room_pool.w));
    float out_dist = length(max(d, 0.0));                                          // distance to the pool rectangle (0 inside)
    float edge = exp(-out_dist / max(room_wet.z, 0.05));
    float n = value_noise2(p / room_wet.y) * 0.65 + value_noise2(p / room_wet.y * 2.7 + 17.0) * 0.35;
    puddle = smoothstep(0.62, 0.70, n * room_wet.x * 1.4 + edge * 0.35) * clamp(room_wet.x * 2.0, 0.0, 1.0);
    float damp = max(edge * 0.8, puddle);
    for (int i = 0; i < 24; i++) {
        vec4 f = room_prints[i];
        float age = t - f.z;
        if (age < 0.0 || age > room_wet2.y) continue;
        float s = floor(f.w / 10.0);
        float yaw = f.w - s * 10.0;
        vec2 q = p - f.xy;
        vec2 local = vec2(cos(yaw) * q.x - sin(yaw) * q.y, sin(yaw) * q.x + cos(yaw) * q.y);   // y along the walking direction
        float sole = length(local / vec2(0.055, 0.12));                                         // a foot: ellipse 11 x 24 cm
        float shape = 1.0 - smoothstep(0.75, 1.0, sole);
        damp = max(damp, shape * s / 100.0 * (1.0 - age / room_wet2.y));
    }
    return clamp(damp, 0.0, 1.0);
}

// the height of the tile texture at `uv` (texture units), with explicit gradients so the sampling is legal inside branches
float tile_height(bool is_floor, vec2 uv, vec2 gx, vec2 gy) {
    return is_floor ? textureGrad(room_tile_relief, uv, gx, gy).r : textureGrad(room_wall_relief, uv, gx, gy).r;
}

void main() {
    vec3 irradiance = pow(texture(room_lightmap, lightmap_uv).rgb, vec3(2.0)) * room_params.x;
    float tile = vertex_color.a;
    vec3 n_face = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 V = to_cam / max(dist, 1e-4);
    vec3 Ng = dot(n_face, V) < 0.0 ? -n_face : n_face;                 // the surface normal turned toward the viewer
    vec3 albedo = vertex_color.rgb;
    vec3 n_p = Ng;                                                      // the shading normal (the tile relief bends it)
    vec3 Tt = vec3(1.0, 0.0, 0.0), Bt = vec3(0.0, 0.0, 1.0);
    vec2 tn = vec2(0.0);                                                // the relief's normal xy: the wet floor's mirror breaks along the joints
    float bump_gain = 1.0;
    if (tile > 0.0) {
        bool is_floor = tile > 0.2;
        float period = tile * (is_floor ? 2.0 : 4.0);                   // metres covered by one texture
        vec2 q = metric / period;
        vec2 gx = dFdx(q), gy = dFdy(q);
        vec2 uv = q;
        float fw = max(max(abs(gx.x) + abs(gx.y), abs(gy.x) + abs(gy.y)) * (period / tile), 1e-5);   // pixel footprint in tiles
        float detail_fade = 1.0 - smoothstep(0.25, 0.8, fw);            // far away (a pixel spans a good part of a tile) the relief is only noise
        if (Q_SURFACE) {
            vec3 dp1 = dFdx(world_pos), dp2 = dFdy(world_pos);
            vec2 du1 = dFdx(metric), du2 = dFdy(metric);
            vec3 dp2p = cross(dp2, Ng), dp1p = cross(Ng, dp1);
            vec3 T = dp2p * du1.x + dp1p * du2.x;
            vec3 B = dp2p * du1.y + dp1p * du2.y;
            float m = max(dot(T, T), dot(B, B));
            if (m > 1e-20) {
                float k = inversesqrt(m);
                Tt = T * k;
                Bt = B * k;
            }
            if (Q_PARALLAX) {
                float depth_m = is_floor ? look_surface.y : look_surface.z;
                float amount = 1.0 - smoothstep(5.0, 11.0, dist);       // parallax only up close: far joints are a few pixels wide and the march only costs
                if (amount > 0.01 && depth_m > 0.0) {
                    vec2 vt = vec2(dot(V, Tt), dot(V, Bt));
                    float vz = max(dot(V, Ng), 0.2);
                    vec2 shift = vt / vz * depth_m / period * amount;   // texture units for a full depth
                    const int STEPS = 8;
                    float layer = 1.0 / float(STEPS);
                    float depth = 0.0;
                    vec2 cur = q;
                    float h = tile_height(is_floor, cur, gx, gy);
                    float prev_h = h, prev_depth = 0.0;
                    for (int i = 0; i < STEPS; i++) {
                        if (depth >= 1.0 - h) break;
                        prev_h = h;
                        prev_depth = depth;
                        cur -= shift * layer;
                        depth += layer;
                        h = tile_height(is_floor, cur, gx, gy);
                    }
                    float after = (1.0 - h) - depth;                    // <= 0: the ray is under the surface at the last step
                    float before = (1.0 - prev_h) - prev_depth;         // >= 0: it was above it one step earlier
                    float w = clamp(after / min(after - before, -1e-5), 0.0, 1.0);
                    uv = mix(cur, cur + shift * layer, w);
                }
            }
        }
        vec3 col;
        vec3 rel;
        if (is_floor) {
            col = textureGrad(room_tile_color, uv, gx, gy).rgb;
            rel = textureGrad(room_tile_relief, uv, gx, gy).rgb;
        } else {
            col = textureGrad(room_wall_color, uv, gx, gy).rgb;
            rel = textureGrad(room_wall_relief, uv, gx, gy).rgb;
        }
        vec2 cell = floor(metric / tile);
        float tone = 1.0 + (hash21(cell) - 0.5) * 0.12 * detail_fade;   // each tile a little different (the texture repeats every 2 / 4 tiles)
        albedo *= col * (TILE_GAIN * tone);
        if (Q_SURFACE) {
            tn = (rel.gb * 2.0 - 1.0) * look_surface.w * detail_fade;
            n_p = normalize(Tt * tn.x + Bt * tn.y + Ng * sqrt(max(1.0 - dot(tn, tn), 0.05)));
            vec3 key = normalize(vec3(0.35, 0.85, 0.25));               // the baked light has no direction: a fixed key light from above makes the relief read
            bump_gain = clamp(1.0 + 0.9 * (dot(n_p, key) - dot(Ng, key)), 0.5, 1.5);
        }
    }
    float wet = 0.0, puddle = 0.0;
    if (Q_WET && abs(n_face.y) > 0.9 && abs(world_pos.y) < 0.01) {      // the deck top only
        wet = deck_wetness(world_pos.xz, look_shaft2.y, puddle);
        albedo *= 1.0 - room_wet2.x * wet;                                            // wet tiles are darker (water fills the pores)
    }
    vec3 lit = albedo * irradiance * bump_gain;

    if (look_flash_color.r > 0.0) lit += albedo * flash_light(world_pos, n_p, look_flash_world.y) * look_flash_world.x;
    bool under = pixel_wet();                                       // G12: this pixel looks through the water (the camera at / under the surface)
    if (!under) lit += sun_shaft(look_camera_pos, world_pos);       // the sunlit dusty air between the eye and this pixel (G10; 0 samples on graphics level Low)
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    vec3 color = tonemap(lit);
    if (wet > 0.0) {                                                                  // a wet floor mirrors the room (a puddle almost like a mirror; damp tiles a faint sheen)
        vec3 v = V;
        vec2 ripple = (vec2(value_noise2(world_pos.xz * 9.0), value_noise2(world_pos.xz * 9.0 + 5.0)) - 0.5) * 0.04 * (1.0 - puddle);
        vec3 n = normalize(vec3(ripple.x, 1.0, ripple.y) + (Tt * tn.x + Bt * tn.y) * 0.6 * (1.0 - puddle));   // the joints break the mirror of a damp tile (a puddle fills them)
        vec3 r = reflect(-v, n);
        r.y = max(r.y, 0.02);
        float fres = 0.02 + 0.98 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
        float k = fres * room_wet.w * mix(0.35 * wet, 1.0, puddle);
        color = mix(color, room_reflection(world_pos, r), clamp(k, 0.0, 1.0));
    }
    frag_color = vec4(under ? under_fog(color, dist) : mix(color, look_fog.rgb, fog), 1.0);
}
