#version 140
// Bullet hole on a wall / floor, drawn as a decal over the baked surface. The atlas holds 2 x 2 different holes (`hole_color` RGBA, `hole_relief` R = height with 1 = the surface,
// G / B = normal x / y; tools/build/make_surface_textures.py). Surface detail (graphics F2 'Chi tiết bề mặt'), switched by a uniform, no recompile:
//   0 flat: the colour image only (it already has the dark bore / pale rim painted in);
//   1 normal map: the crater is shaded by its relief (a fixed key light for the baked, directionless wall light + the muzzle flash);
//   2 parallax occlusion mapping: the crater really looks sunk in when seen at an angle (the bore wall slides over the floor of the crater).
// Light: where the wall's baked lightmap is known (the pool hall) the hole gets the SAME irradiance as the wall behind it, so a hole in the shade is dark and one in a sun patch is lit;
// without it (flat map) the world formula of world.frag. The hole fades out over the last part of its life (core/holes.py `fade_alpha`).
uniform sampler2D hole_color;
uniform sampler2D hole_relief;
uniform sampler2D room_lightmap;
uniform vec4 room_params;           // x = irradiance that is 255 in the lightmap (stored with gamma 2)
uniform vec4 hole_time;             // x clock (s, wrapped at 4096), y life (s), z fade (s), w unused
uniform vec4 hole_quality;          // x surface detail 0 / 1 / 2, y depth of the crater (share of the decal width), z normal strength, w parallax steps
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
uniform vec2 look_flash_world;      // multiplies the muzzle-flash brightness onto the world, falloff

#include "light_common.glsl"
#include "underwater.glsl"

in vec2 v_uv;
in vec4 v_color;
in vec3 world_pos;
in vec2 lightmap_uv;
in vec4 v_hole;
out vec4 frag_color;

const vec2 CELLS = vec2(2.0, 2.0);

// cell bounds in the atlas (uv of the lower-left corner; `cell` counts from v = 0, left to right)
vec2 cell_origin(float cell) {
    return vec2(mod(cell, CELLS.x), floor(cell / CELLS.x)) / CELLS;
}

void main() {
    float age = mod(hole_time.x - v_hole.x, 4096.0);
    float fade = hole_time.z <= 0.0 ? 1.0 : 1.0 - smoothstep(hole_time.y - hole_time.z, hole_time.y, age);
    if (age >= hole_time.y || v_color.a * fade <= 0.003) discard;

    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    vec3 V = to_cam / max(dist, 1e-4);
    vec3 N = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    if (dot(N, V) < 0.0) N = -N;

    // the tangent frame of the atlas uv on the surface (T along +u, B along +v)
    vec3 dp1 = dFdx(world_pos), dp2 = dFdy(world_pos);
    vec2 du1 = dFdx(v_uv), du2 = dFdy(v_uv);
    vec3 dp2p = cross(dp2, N), dp1p = cross(N, dp1);
    vec3 T = dp2p * du1.x + dp1p * du2.x;
    vec3 B = dp2p * du1.y + dp1p * du2.y;
    float tb = max(dot(T, T), dot(B, B));
    T = tb > 1e-20 ? T * inversesqrt(tb) : vec3(1.0, 0.0, 0.0);
    B = tb > 1e-20 ? B * inversesqrt(tb) : vec3(0.0, 1.0, 0.0);

    vec2 uv = v_uv;
    int detail = int(hole_quality.x + 0.5);
    vec2 o = cell_origin(v_hole.y);
    if (detail >= 2) {                                          // parallax occlusion mapping: march the view ray down through the height field
        vec2 vt = vec2(dot(V, T), dot(V, B));
        float vz = max(dot(V, N), 0.25);
        // a full depth of `hole_quality.y` x the decal width, in atlas uv: one cell is 1 / CELLS of the atlas
        vec2 shift = vt / vz * hole_quality.y / CELLS;
        float steps = hole_quality.w;
        float layer = 1.0 / steps;
        float depth = 0.0;
        vec2 cur = v_uv;
        float h = texture(hole_relief, cur).r;
        float prev_h = h, prev_depth = 0.0;
        for (int i = 0; i < 16; i++) {
            if (float(i) >= steps || depth >= 1.0 - h) break;
            prev_h = h;
            prev_depth = depth;
            cur -= shift * layer;
            depth += layer;
            h = texture(hole_relief, cur).r;
        }
        float after = (1.0 - h) - depth;                        // <= 0: the ray is under the surface at the last step
        float before = (1.0 - prev_h) - prev_depth;             // >= 0: it was above it one step earlier
        float w = clamp(after / min(after - before, -1e-5), 0.0, 1.0);        // linear refinement between the last two steps
        uv = mix(cur, cur + shift * layer, w);
        vec2 lo = o + 0.5 / 512.0, hi = o + 1.0 / CELLS - 0.5 / 512.0;
        uv = clamp(uv, lo, hi);                                 // never read the neighbouring hole
    }

    vec4 col = texture(hole_color, uv) * v_color;
    float alpha = col.a * fade;
    if (alpha <= 0.003) discard;

    vec3 relief = texture(hole_relief, uv).rgb;
    vec3 n = N;
    if (detail >= 1) {
        vec2 nxy = (relief.gb * 2.0 - 1.0) * hole_quality.z;
        n = normalize(T * nxy.x + B * nxy.y + N * sqrt(max(1.0 - dot(nxy, nxy), 0.05)));
    }

    vec3 base = col.rgb;
    vec3 lit;
    if (lightmap_uv.x >= 0.0) {
        vec3 irradiance = pow(texture(room_lightmap, lightmap_uv).rgb, vec3(2.0)) * room_params.x;
        lit = base * irradiance;
        if (detail >= 1) {                                      // the baked light has no direction: a fixed key light from above makes the relief read, only changing what the flat wall would get
            vec3 key = normalize(vec3(0.35, 0.85, 0.25));
            lit *= clamp(1.0 + 0.9 * (dot(n, key) - dot(N, key)), 0.35, 1.6);
            lit *= mix(1.0, 0.45 + 0.55 * relief.r, 0.9);       // the deeper, the more shut in: cavity darkening
        }
    } else {
        lit = base * (ambient_at(n) + look_sun_color * max(dot(n, look_sun_dir), 0.0));
    }
    if (look_flash_color.r > 0.0) lit += base * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;

    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);
    vec3 color = tonemap(lit);
    frag_color = vec4(pixel_wet() ? under_fog(color, dist) : mix(color, look_fog.rgb, fog), alpha);
}
