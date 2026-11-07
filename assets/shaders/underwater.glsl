// SHARED (room.frag, water.frag, basin.frag, viewmodel.frag, lens.frag), G12: is a render pixel under the water, and the underwater fog. Mirror of core/underwater.py.
// The lens port is a small window at the eye; the port point of the render pixel at ndc (x, y) is h = c + a x + b y - wobble(x) metres above the water: wet when h < 0.
// FrameLight binds these on render and on the gun; the lens quad gets its own copy of the same PTAs.
uniform vec4 look_under;        // a, b, c (m), wobble amplitude (m)
uniform vec4 look_under2;       // x = 1 when some pixel can be wet (otherwise every test is skipped), y = clock (s), z = 2 / buffer width, w = 2 / buffer height
uniform vec4 look_under_fog;    // rgb = colour far away in the water (display), a = turbidity (1/m)
uniform vec4 look_under_abs;    // rgb = absorption (1/m) on the underwater path, a = 1 when the eye is under the surface
uniform vec4 look_under3;       // x = full quality (caustics on the basin, waves in the Snell window), y = waves in the Snell window, z = m of water in front of the gun, w = -

// (spatial frequency, angular speed, weight): same table as core/underwater.py WOBBLE
float under_wobble(float x) {
    float t = look_under2.y;
    return look_under.w * (0.6 * sin(9.0 * x + 2.6 * t) + 0.4 * sin(21.0 * x - 3.9 * t));
}

float port_h(vec2 ndc) {
    return look_under.z + look_under.x * ndc.x + look_under.y * ndc.y - under_wobble(ndc.x);
}

// display-space fog of a path of d metres through the water (mirror of core/underwater.py `fog`)
vec3 under_fog(vec3 c, float d) {
    vec3 t = exp(-(look_under_abs.rgb + look_under_fog.a) * max(d, 0.0));
    return c * t + look_under_fog.rgb * (1.0 - t);
}

#ifndef UNDER_NO_FRAGCOORD
bool pixel_wet() {
    if (look_under2.x < 0.5) return false;
    return port_h(gl_FragCoord.xy * look_under2.zw - 1.0) < 0.0;
}
#endif
