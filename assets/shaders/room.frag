#version 140
// Pool hall surface: colour = tile albedo x BAKED irradiance (lightmap: sun patches, bounce, sky through the windows; core/lightbake.py) + the muzzle flash, then the shared tone curve.
// Tiles are drawn here from metric coordinates (no texture): grout lines anti-aliased by the pixel footprint, a little brightness change from tile to tile.
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

// 1 on a tile, GROUT_DARK in the grout. `size` metres per tile. When a pixel covers a whole tile the pattern fades to its average so it never shimmers.
const float GROUT_HALF = 0.06;      // half the grout width, as a share of the tile
const float GROUT_DARK = 0.58;
float tile_shade(vec2 p, float size) {
    vec2 q = p / size;
    vec2 cell = floor(q);
    vec2 edge = min(fract(q), 1.0 - fract(q));                      // distance to the nearest tile edge, in tiles
    vec2 fw = max(fwidth(q), vec2(1e-5));
    vec2 line = 1.0 - smoothstep(vec2(GROUT_HALF) - fw, vec2(GROUT_HALF) + fw, edge);
    float grout = max(line.x, line.y);
    float blur = clamp(max(fw.x, fw.y) * 2.0, 0.0, 1.0);
    float average = 1.0 - (1.0 - 2.0 * GROUT_HALF) * (1.0 - 2.0 * GROUT_HALF);
    grout = mix(grout, average, blur);
    float tone = 1.0 + (hash21(cell) - 0.5) * 0.16 * (1.0 - blur);
    return mix(tone, GROUT_DARK, grout);
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

void main() {
    vec3 irradiance = pow(texture(room_lightmap, lightmap_uv).rgb, vec3(2.0)) * room_params.x;
    float tile = vertex_color.a;
    vec3 albedo = vertex_color.rgb * (tile > 0.0 ? tile_shade(metric, tile) : 1.0);
    vec3 n_face = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    float wet = 0.0, puddle = 0.0;
    if (room_quality.x > 0.5 && abs(n_face.y) > 0.9 && abs(world_pos.y) < 0.01) {      // the deck top only
        wet = deck_wetness(world_pos.xz, look_shaft2.y, puddle);
        albedo *= 1.0 - room_wet2.x * wet;                                            // wet tiles are darker (water fills the pores)
    }
    vec3 lit = albedo * irradiance;

    if (look_flash_color.r > 0.0) {
        vec3 to_cam = look_camera_pos - world_pos;
        vec3 n = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
        if (dot(n, to_cam) < 0.0) n = -n;
        lit += albedo * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;
    }
    bool under = pixel_wet();                                       // G12: this pixel looks through the water (the camera at / under the surface)
    if (!under) lit += sun_shaft(look_camera_pos, world_pos);       // the sunlit dusty air between the eye and this pixel (G10; 0 samples on graphics level Low)
    float dist = length(look_camera_pos - world_pos);
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    vec3 color = tonemap(lit);
    if (wet > 0.0) {                                                                  // a wet floor mirrors the room (a puddle almost like a mirror; damp tiles a faint sheen)
        vec3 v = normalize(look_camera_pos - world_pos);
        vec2 ripple = (vec2(value_noise2(world_pos.xz * 9.0), value_noise2(world_pos.xz * 9.0 + 5.0)) - 0.5) * 0.04 * (1.0 - puddle);
        vec3 n = normalize(vec3(ripple.x, 1.0, ripple.y));
        vec3 r = reflect(-v, n);
        r.y = max(r.y, 0.02);
        float fres = 0.02 + 0.98 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
        float k = fres * room_wet.w * mix(0.35 * wet, 1.0, puddle);
        color = mix(color, room_reflection(world_pos, r), clamp(k, 0.0, 1.0));
    }
    frag_color = vec4(under ? under_fog(color, dist) : mix(color, look_fog.rgb, fog), 1.0);
}
