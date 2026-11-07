// SHARED (water.frag, caustics.vert): the pool's small ripples, a narrow band of travelling sines. The table comes from Python (core/caustics.py wave_table / pack), the same
// arrays are given to both shaders, so the ripples that bend the view of the tiles are the ones that focus the sunlight on them.
uniform vec4 wave_a[16];            // dir x, dir z, k (rad/m), amplitude (m)
uniform vec4 wave_b[16];            // omega (rad/s), phase, -, -

// (h, dh/dx, dh/dz) at the plan point p (m), time t (s): mirror of core/caustics.py `surface`
vec3 pool_wave(vec2 p, float t) {
    vec3 s = vec3(0.0);
    for (int i = 0; i < 16; i++) {
        vec4 a = wave_a[i];
        float arg = a.z * dot(p, a.xy) - wave_b[i].x * t + wave_b[i].y;
        s.x += a.w * sin(arg);
        s.yz += a.w * a.z * cos(arg) * a.xy;
    }
    return s;
}
