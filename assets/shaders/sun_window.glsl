// SHARED (room.frag, water.frag): does the sun reach a point, and the sunlit dusty air between the eye and a pixel (G10). Include AFTER light_common.glsl.
// The sun is fixed and only comes in through the rectangular holes in the east wall: a point is sunlit iff its ray toward the sun passes inside a hole at both the inner
// and the outer wall face (mirror of core/poolmap.py `sun_visible`; tests/test_graphics.py checks it against a ray cast on every box).
uniform vec4 look_windows[4];       // z0, z1, y0, y1 of each window hole
uniform vec4 look_window_wall;      // x = inner wall face, y = outer wall face, z = number of windows, w = soft edge (m)
uniform vec4 look_shaft;            // x = density (1/m), y = anisotropy g, z = samples per pixel (0 = off), w = dust 0..1
uniform vec4 look_shaft2;           // x = range (m), y = clock (s), zw unused

float window_inside(vec2 q, vec4 w, float e) {
    vec2 a = smoothstep(vec2(w.x, w.z) - e, vec2(w.x, w.z) + e, q);
    vec2 b = 1.0 - smoothstep(vec2(w.y, w.w) - e, vec2(w.y, w.w) + e, q);
    return a.x * a.y * b.x * b.y;
}

float sun_visible(vec3 p) {
    vec3 s = look_sun_dir;
    if (s.x <= 1e-4 || p.x > look_window_wall.x) return 0.0;
    vec2 qa = p.zy + s.zy * ((look_window_wall.x - p.x) / s.x);
    vec2 qb = p.zy + s.zy * ((look_window_wall.y - p.x) / s.x);
    float best = 0.0;
    for (int i = 0; i < 4; i++) {
        if (float(i) >= look_window_wall.z) break;
        best = max(best, window_inside(qa, look_windows[i], look_window_wall.w) * window_inside(qb, look_windows[i], look_window_wall.w));
    }
    return best;
}

float hash31(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
}

float value_noise(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = mix(mix(hash31(i), hash31(i + vec3(1, 0, 0)), f.x), mix(hash31(i + vec3(0, 1, 0)), hash31(i + vec3(1, 1, 0)), f.x), f.y);
    float b = mix(mix(hash31(i + vec3(0, 0, 1)), hash31(i + vec3(1, 0, 1)), f.x), mix(hash31(i + vec3(0, 1, 1)), hash31(i + vec3(1, 1, 1)), f.x), f.y);
    return mix(a, b, f.z);
}

// single scattering of the sun by the air on the segment eye -> p (linear light, before the tone curve). No transmittance: indoors the air is thin.
vec3 sun_shaft(vec3 eye, vec3 p) {
    float n = look_shaft.z;
    if (n < 0.5 || look_shaft.x <= 0.0) return vec3(0.0);
    vec3 d = p - eye;
    float len = min(length(d), look_shaft2.x);
    vec3 dir = normalize(d);
    float g = look_shaft.y;
    float c = dot(dir, look_sun_dir);
    float phase = (1.0 - g * g) / (12.566 * pow(max(1.0 + g * g - 2.0 * g * c, 1e-3), 1.5));
    float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));      // interleaved gradient noise: the steps do not show as bands
    vec3 drift = vec3(0.07, 0.015, 0.05) * look_shaft2.y;
    float sum = 0.0;
    for (int i = 0; i < 32; i++) {
        if (float(i) >= n) break;
        vec3 q = eye + dir * (len * (float(i) + jitter) / n);
        float lit = sun_visible(q);
        if (lit > 0.0) {
            float dust = mix(1.0, 0.25 + 1.5 * value_noise(q * 1.7 + drift), look_shaft.w);
            sum += lit * dust;
        }
    }
    return look_sun_color * (look_shaft.x * phase * len * sum / n);
}
