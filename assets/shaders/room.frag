#version 140
// Pool hall surface: colour = tile albedo x BAKED irradiance (lightmap: sun patches, bounce, sky through the windows; core/lightbake.py) + the muzzle flash, then the shared tone curve.
// Tiles are drawn here from metric coordinates (no texture): grout lines anti-aliased by the pixel footprint, a little brightness change from tile to tile.
// Every custom uniform has the look_ / room_ prefix (see world.frag for why).
uniform sampler2D room_lightmap;
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
uniform vec4 room_params;           // x = irradiance that is 255 in the lightmap (stored with gamma 2)
uniform vec2 look_flash_world;      // multiplies the muzzle-flash brightness onto the world, falloff

#include "light_common.glsl"

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

void main() {
    vec3 irradiance = pow(texture(room_lightmap, lightmap_uv).rgb, vec3(2.0)) * room_params.x;
    float tile = vertex_color.a;
    vec3 albedo = vertex_color.rgb * (tile > 0.0 ? tile_shade(metric, tile) : 1.0);
    vec3 lit = albedo * irradiance;

    if (look_flash_color.r > 0.0) {
        vec3 to_cam = look_camera_pos - world_pos;
        vec3 n = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
        if (dot(n, to_cam) < 0.0) n = -n;
        lit += albedo * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;
    }
    float dist = length(look_camera_pos - world_pos);
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    frag_color = vec4(mix(tonemap(lit), look_fog.rgb, fog), 1.0);
}
