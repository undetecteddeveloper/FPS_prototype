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

#ifndef SUN_WINDOW_VERTEX                // a vertex shader only needs sun_visible (gl_FragCoord below exists only in fragment shaders)
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

// narrow [t.x, t.y] to the t where lo <= a + b t <= hi (mirror of core/poolmap.py _clip)
vec2 clip_span(vec2 t, float a, float b, float lo, float hi) {
    if (abs(b) < 1e-6) return (a >= lo && a <= hi) ? t : vec2(1.0, 0.0);
    float ta = (lo - a) / b, tb = (hi - a) / b;
    return vec2(max(t.x, min(ta, tb)), min(t.y, max(ta, tb)));
}

// single scattering of the sun by the air on the segment eye -> p (linear light, before the tone curve). No transmittance: indoors the air is thin.
// EXACT, not marched (mirror of core/poolmap.py `sunlit_segments`; tests/test_graphics.py): a beam is a window hole pushed along the sun, and the projection of a point along
// the sun onto a wall plane is linear in the point, so each window cuts one interval [t0, t1] out of the ray. Only the dust needs samples: look_shaft.z per lit interval.
// (Marching 16 steps x 4 windows per pixel cost 7 ms per frame here; this costs a few dozen instructions.)
vec3 sun_shaft(vec3 eye, vec3 p) {
    float samples = look_shaft.z;
    vec3 s = look_sun_dir;
    if (samples < 0.5 || look_shaft.x <= 0.0 || s.x <= 1e-4) return vec3(0.0);
    vec3 d = p - eye;
    float len = min(length(d), look_shaft2.x);
    vec3 dir = normalize(d);
    float g = look_shaft.y;
    float c = dot(dir, s);
    float phase = (1.0 - g * g) / (12.566 * pow(max(1.0 + g * g - 2.0 * g * c, 1e-3), 1.5));
    vec3 drift = vec3(0.07, 0.015, 0.05) * look_shaft2.y;
    vec2 bz = dir.zy - s.zy * (dir.x / s.x);                                  // how the projection moves per metre along the ray (same for both wall faces)
    float lit = 0.0;
    for (int i = 0; i < 4; i++) {
        if (float(i) >= look_window_wall.z) break;
        vec4 w = look_windows[i];
        vec2 t = vec2(0.0, len);
        if (abs(dir.x) > 1e-6) {
            float tw = (look_window_wall.x - eye.x) / dir.x;                     // inside the room
            t = dir.x > 0.0 ? vec2(t.x, min(t.y, tw)) : vec2(max(t.x, tw), t.y);
        } else if (eye.x > look_window_wall.x) continue;
        for (int k = 0; k < 2; k++) {
            float x = k == 0 ? look_window_wall.x : look_window_wall.y;
            vec2 a = eye.zy + s.zy * ((x - eye.x) / s.x);
            t = clip_span(t, a.x, bz.x, w.x, w.y);
            t = clip_span(t, a.y, bz.y, w.z, w.w);
        }
        if (t.y <= t.x) continue;
        float dust = 0.0;                                                      // the dusty air is uneven: a few noise samples inside the lit piece
        for (int j = 0; j < 4; j++) {
            if (float(j) >= samples) break;
            vec3 q = eye + dir * mix(t.x, t.y, (float(j) + 0.5) / samples);
            dust += mix(1.0, 0.25 + 1.5 * value_noise(q * 1.7 + drift), look_shaft.w);
        }
        lit += (t.y - t.x) * dust / samples;
    }
    return look_sun_color * (look_shaft.x * phase * lit);
}
#endif
