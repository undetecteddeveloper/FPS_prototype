#version 140
// Caustic pass (G11, math in core/caustics.py): one triangle strip per row of the light mesh (instanced: gl_InstanceID = row). Every vertex is a point of the water surface;
// the sunlight is refracted there by the ripples + the simulated waves and dropped onto the pool bottom. gl_Position = where it lands (in the caustic texture),
// `flat_pos` = where it lands on flat water; the fragment shader turns the ratio of the two areas into brightness.
in vec4 p3d_Vertex;                 // x = column (0 .. cols - 1), y = 0 / 1 (this row / the next)
uniform vec4 caus_grid;             // x0, z0 of the mesh, step x, step z (m)
uniform vec4 caus_domain;           // x0, x1, z0, z1 of the texture (m)
uniform vec4 caus_params;           // x water level (m), y weight of the simulated waves, z clock (s), w -
uniform vec3 caus_sun;              // unit vector toward the sun
uniform vec4 water_rect;            // pool (and simulation) rect: x0, x1, z0, z1
uniform vec4 water_ramp;            // z0, z1, y at z0, y at z1
uniform sampler2D water_sim_a;
uniform sampler2D water_sim_b;
uniform vec4 water_sim_pick;        // x = 0: A is the latest, 1: B
uniform vec4 caus_sim_on;           // x = 1 when a simulation runs (else its textures are 1 x 1 placeholders)

#include "pool_waves.glsl"

out vec2 flat_pos;

const float ETA = 1.0 / 1.333;

float bottom_y(float z) {
    float k = clamp((z - water_ramp.x) / (water_ramp.y - water_ramp.x), 0.0, 1.0);
    return mix(water_ramp.z, water_ramp.w, k);
}

vec2 drop(vec3 p, vec3 r) {
    float down = max(-r.y, 1e-4);
    float s = (p.y - bottom_y(p.z)) / down;
    for (int i = 0; i < 3; i++) s = (p.y - bottom_y(p.z + s * r.z)) / down;
    return p.xz + s * r.xz;
}

float sim_h(vec2 uv) {
    return water_sim_pick.x < 0.5 ? textureLod(water_sim_a, uv, 0.0).r : textureLod(water_sim_b, uv, 0.0).r;
}

void main() {
    vec2 xz = caus_grid.xy + vec2(p3d_Vertex.x, float(gl_InstanceID) + p3d_Vertex.y) * caus_grid.zw;
    float t = caus_params.z;
    vec3 w = pool_wave(xz, t);
    if (caus_sim_on.x > 0.5) {
        vec2 size = water_rect.yw - water_rect.xz;
        vec2 uv = (xz - water_rect.xz) / size;
        vec2 texel = 1.0 / vec2(textureSize(water_sim_a, 0));
        vec2 cell = size * texel;
        float c = sim_h(uv);
        float l = sim_h(uv - vec2(texel.x, 0.0)), r = sim_h(uv + vec2(texel.x, 0.0));
        float d = sim_h(uv - vec2(0.0, texel.y)), u = sim_h(uv + vec2(0.0, texel.y));
        w += caus_params.y * vec3(c, (r - l) / (2.0 * cell.x), (u - d) / (2.0 * cell.y));
    }
    vec3 n = normalize(vec3(-w.y, 1.0, -w.z));
    vec3 ray = refract(-caus_sun, n, ETA);
    vec3 ray0 = refract(-caus_sun, vec3(0.0, 1.0, 0.0), ETA);
    vec2 landed = drop(vec3(xz.x, caus_params.x + w.x, xz.y), ray);
    flat_pos = drop(vec3(xz.x, caus_params.x, xz.y), ray0);
    gl_Position = vec4((landed - caus_domain.xz) / (caus_domain.yw - caus_domain.xz) * 2.0 - 1.0, 0.0, 1.0);
}
