#version 140
// World: one slab of ground under a sun (light_common.glsl, shared with the gun), muzzle flash, earth noise drawn in world coordinates, haze blending into the sky colour.
// Normals come from position derivatives (the mesh needs no normals). Every custom uniform has the look_ prefix (the default inputs of the shader
// Ursina, such as fog_color set on each object, would override the input with the same name set on render).
uniform sampler2D p3d_Texture0;
uniform sampler2D look_detail_tex;
uniform vec4 p3d_ColorScale;
uniform vec4 look_fog;              // rgb = haze colour, a = density (exp)
uniform float look_detail_strength;
uniform float look_material;        // 0 default (bullet holes), 1 ground
uniform vec4 look_grid;             // ground grid: strength, spacing (m), a heavy line every this many lines, half width of a thin line (m)
uniform vec2 look_flash_world;      // multiplies the muzzle-flash brightness onto the world, falloff

#include "light_common.glsl"

in vec2 uvs;
in vec4 vertex_color;
in vec3 world_pos;
out vec4 frag_color;

// dry earth: blotches at two scales (metres) so no tiling shows; fades out with distance (far away the noise only shimmers)
vec3 earth(vec3 base, vec3 p_w, float dist) {
    float fade = 1.0 - smoothstep(40.0, 160.0, dist);
    float coarse = texture(look_detail_tex, p_w.xz * 0.043 + 0.37).r;
    float fine = texture(look_detail_tex, p_w.xz * 0.21).r;
    float n = (coarse * 0.6 + fine * 0.4) - 0.5;
    return base * (1.0 + n * look_detail_strength * fade * 1.4);
}

// Lines of a square grid on the ground (p = ground coordinates in m): 1 on a line, 0 between. The line is `half_w` m from its centre on each side, anti-aliased by the pixel size;
// once a pixel covers a large part of a cell the lines blur into their average coverage instead of shimmering.
float grid_lines(vec2 p, float spacing, float half_w) {
    vec2 fw = max(fwidth(p), vec2(1e-5));                              // metres per pixel
    vec2 d = abs(fract(p / spacing + 0.5) - 0.5) * spacing;            // metres to the nearest line, per axis
    vec2 line = 1.0 - smoothstep(vec2(half_w) - fw, vec2(half_w) + fw, d);
    float t = clamp(max(fw.x, fw.y) / (spacing * 0.5), 0.0, 1.0);
    line = mix(line, vec2(min(2.0 * half_w / spacing, 1.0)), t);
    return max(line.x, line.y);
}

void main() {
    vec4 base = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    int mat = int(look_material + 0.5);
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);

    vec3 n = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    if (dot(n, to_cam) < 0.0) n = -n;

    if (mat == 1) {
        base.rgb = earth(base.rgb, world_pos, dist);
        if (look_grid.x > 0.0) {
            vec2 gp = world_pos.xz + 0.5 * look_grid.y * look_grid.z;      // shifted so the spawn point sits in the middle of a big square, not on a heavy line
            float minor = grid_lines(gp, look_grid.y, look_grid.w);
            float major = grid_lines(gp, look_grid.y * look_grid.z, look_grid.w * 2.0);
            base.rgb *= 1.0 - look_grid.x * max(minor * 0.55, major);
        }
    }

    vec3 lit = base.rgb * (ambient_at(n) + look_sun_color * max(dot(n, look_sun_dir), 0.0));
    if (look_flash_color.r > 0.0) lit += base.rgb * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;

    frag_color = vec4(mix(tonemap(lit), look_fog.rgb, fog), base.a);
}
