#version 140
// Head-camera lens, drawn once on the composited world + rifle image: fisheye (same formula as core/lens.py), colour fringing, edge blur, rolling shutter when turning, lens flare,
// colour grading, corner darkening + orange halo, sensor noise. The centre costs only 3 samples; edge blur takes extra samples only where needed.
// G12: fully under the water the picture is magnified (flat port); the waterline across the port draws a meniscus. The world shaders already fogged the underwater
// pixels (underwater.glsl). (The wet lens after surfacing, a water film + drops, was removed 8/11/2026.)
uniform sampler2D lens_scene;
uniform vec4 lens_warp;         // frame aspect, colour fringe, edge blur, blur start
uniform vec4 lens_motion;       // extra blur per deg/s, rolling shutter per deg/s, outer edge-blur radius boundary, 1 + overscan (the scene is drawn that much wider)
uniform vec4 lens_vig;          // darkening starts, fully dark, orange halo, noise
uniform vec4 lens_grade;        // contrast, saturation, flare, flare threshold
uniform vec3 lens_tint;
uniform vec3 lens_frame;        // current distortion, time, turn speed (deg/s, positive = right)
uniform vec3 lens_shake;        // frame shake (core/lens.py frame_shake): content offset dx, dy in p units, CCW roll in radians
uniform vec4 lens_water;        // G12: x zoom under the water (1 = none), y meniscus thickness (m on the port), zw unused
uniform vec4 lens_hurt;         // G18: x red frame edge 0..1 (hit / low health), y colour drained 0..1
uniform vec4 lens_lod;          // G13: x = log2(scene buffer / window): mip levels are picked in WINDOW terms, so a 75% buffer blooms over the same screen area
// G13: LENS_DRY = the build used while no waterline band can be in view (game/lens.py picks it every frame). It leaves the meniscus code out
// (an unused branch still costs registers on Intel; measured 2.78 -> 2.19 ms at 1080p). Both builds are compiled at start-up.
#define UNDER_NO_FRAGCOORD
#include "underwater.glsl"
in vec2 v_uv;
out vec4 frag_color;

float hash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * 0.1031);
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}

void main() {
    vec2 p = v_uv * 2.0 - 1.0;
    // frame shake: the whole lens frame (image, distortion centre, vignette) moves and tilts on the screen. Screen point -> lens point =
    // inverse of (rotate CCW by roll, then shift by dx, dy); the rotation is done in isotropic units (y / aspect) so it does not shear
    vec2 s = vec2(p.x - lens_shake.x, (p.y - lens_shake.y) / lens_warp.x);
    float cr = cos(lens_shake.z), sr = sin(lens_shake.z);
    s = vec2(cr * s.x + sr * s.y, cr * s.y - sr * s.x);
    p = vec2(s.x, s.y * lens_warp.x);
    vec2 q = vec2(p.x, p.y / lens_warp.x);
    float r2 = dot(q, q);
    float r = sqrt(r2);
    float k = lens_frame.x;
    float f = (1.0 + k * r2) / (1.0 + k);

    float turn = lens_frame.z;
    vec2 src = p * f / lens_water.x;                     // G12: magnified under the water
    src.x += lens_motion.y * turn * p.y;                // rolling shutter: the top and bottom rows are read at two different times
    src /= lens_motion.w;                                // overscan: the scene texture covers a wider view, the shown frame is its middle
    // G12 meniscus: where the waterline crosses the port the water bulges: the picture is pushed away from the line, a dark core with a light rim
    float men = 0.0, men_core = 0.0, men_side = 0.0;
#ifndef LENS_DRY
    if (look_under2.x > 0.5 && lens_water.y > 0.0) {
        float h = port_h(src);
        men = 1.0 - smoothstep(0.0, lens_water.y, abs(h));
        men_core = 1.0 - smoothstep(0.0, 0.4 * lens_water.y, abs(h));
        men_side = h > 0.0 ? 1.0 : 0.0;
        src.y += men * 0.012 * (h > 0.0 ? 1.0 : -1.0);
    }
#endif
    vec2 uv_g = src * 0.5 + 0.5;
    float ca = lens_warp.y * r2;
    vec2 uv_r = (src * (1.0 + ca)) * 0.5 + 0.5;
    vec2 uv_b = (src * (1.0 - ca)) * 0.5 + 0.5;
    vec3 c = vec3(texture(lens_scene, uv_r).r, texture(lens_scene, uv_g).g, texture(lens_scene, uv_b).b);

    // edge blur: along the radius when still, plus extra with turn speed. Four samples with channel offsets so the blur streaks split colour like a photo
    float amount = smoothstep(lens_warp.w, lens_motion.z, r) * (lens_warp.z + lens_motion.x * abs(turn));
    if (amount > 0.0015) {
        vec2 dir = src * amount;
        vec3 sum = c;
        for (int i = 1; i <= 4; i++) {
            float t = float(i) / 4.0;
            vec2 o = dir * t;
            sum += vec3(texture(lens_scene, uv_r + o * 0.56).r, texture(lens_scene, uv_g + o * 0.50).g, texture(lens_scene, uv_b + o * 0.44).b);
        }
        c = sum * 0.2;
    }

#ifndef LENS_DRY
    c = c * (1.0 - 0.65 * men_core) + vec3(0.30, 0.36, 0.38) * (men - men_core) * (0.4 + 0.6 * men_side);
#endif

    // flare: taken from the coarse mip levels of the image itself, bright areas spread outward
    if (lens_grade.z > 0.0) {
        vec3 b = textureLod(lens_scene, uv_g, 3.5 + lens_lod.x).rgb * 0.55 + textureLod(lens_scene, uv_g, 5.5 + lens_lod.x).rgb * 0.45;
        c += max(b - lens_grade.w, 0.0) / (1.0 - lens_grade.w) * lens_grade.z;
    }

    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = mix(vec3(l), c, lens_grade.y) * lens_tint;
    c = (c - 0.5) * lens_grade.x + 0.5;

    // outside the rendered image (shake pulls the frame edge into view, or the fisheye reaches past a corner): fade to black over a thin
    // soft band instead of the clamp smearing the edge pixels. Distance measured in isotropic units (y / aspect), band ~1.2% of the width
    vec2 outside = max(abs(src) - 1.0, 0.0) * vec2(1.0, 1.0 / lens_warp.x);
    c *= 1.0 - smoothstep(0.0, 0.025, max(outside.x, outside.y));

    float v = 1.0 - smoothstep(lens_vig.x, lens_vig.y, r);
    float band = v * (1.0 - v) * 4.0;
    c = c * v + vec3(1.0, 0.40, 0.10) * band * lens_vig.z * clamp(l, 0.0, 1.0);

    // G18 health: the colour drains and the frame edge turns red (a hit flashes it, low health keeps it); 0 = no change
    if (lens_hurt.x + lens_hurt.y > 0.0) {
        c = mix(c, vec3(dot(c, vec3(0.2126, 0.7152, 0.0722))), lens_hurt.y);
        float edge = smoothstep(0.35, 1.15, r) * lens_hurt.x;
        c = mix(c, vec3(0.45, 0.02, 0.01) + c * vec3(0.5, 0.05, 0.05), clamp(edge, 0.0, 0.9));
    }

    float n = hash(gl_FragCoord.xy + fract(lens_frame.y * 7.13) * 411.0) - 0.5;
    c += n * lens_vig.w * (1.35 - clamp(l, 0.0, 1.0));

    frag_color = vec4(c, 1.0);
}
