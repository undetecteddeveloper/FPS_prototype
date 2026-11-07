#version 140
// One step of the pool's wave simulation (mirror of core/watersim.py `step` + `impulse`). Texel = one grid cell; r = height now, g = height one step ago (metres).
// Neighbours outside the grid are clamped to the edge cell: zero slope at the border = a reflecting pool wall.
// IMPULSE_SLOTS is defined by the loader.
uniform sampler2D sim_prev;          // the latest state (the other ping-pong texture)
uniform vec4 sim_params;             // x = coef (speed dt / cell)^2, y = damping per step, z = 1 to apply the impulses in this pass, w = 1 to reset the field to rest
uniform vec4 sim_rect;               // pool: x0, x1, z0, z1 (metres)
uniform vec4 sim_impulses[IMPULSE_SLOTS];   // x, z, radius (m), amount (m); amount 0 = unused slot

out vec4 frag_color;

void main() {
    if (sim_params.w > 0.5) { frag_color = vec4(0.0); return; }
    ivec2 size = textureSize(sim_prev, 0);
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 hi = size - 1;
    vec2 c = texelFetch(sim_prev, p, 0).rg;
    float l = texelFetch(sim_prev, clamp(p + ivec2(-1, 0), ivec2(0), hi), 0).r;
    float r = texelFetch(sim_prev, clamp(p + ivec2(1, 0), ivec2(0), hi), 0).r;
    float d = texelFetch(sim_prev, clamp(p + ivec2(0, -1), ivec2(0), hi), 0).r;
    float u = texelFetch(sim_prev, clamp(p + ivec2(0, 1), ivec2(0), hi), 0).r;
    float h = c.r + (c.r - c.g) * sim_params.y + sim_params.x * (l + r + d + u - 4.0 * c.r);
    float push = 0.0;                // a DISPLACEMENT: added to both time levels, so it gives no velocity of its own (a push added to `now` only kept accelerating: 1 cm became 9 cm)
    if (sim_params.z > 0.5) {
        vec2 world = vec2(mix(sim_rect.x, sim_rect.y, (float(p.x) + 0.5) / float(size.x)), mix(sim_rect.z, sim_rect.w, (float(p.y) + 0.5) / float(size.y)));
        for (int i = 0; i < IMPULSE_SLOTS; i++) {
            vec4 k = sim_impulses[i];
            if (k.w == 0.0) continue;
            vec2 dd = world - k.xy;
            push += k.w * exp(-dot(dd, dd) / max(k.z * k.z, 1e-8));
        }
    }
    frag_color = vec4(clamp(h + push, -0.2, 0.2), c.r + push, 0.0, 1.0);
}
