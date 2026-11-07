// SHARED (water.frag, room.frag wet floor, viewmodel.frag gun): the room captured once into a 3 x 2 atlas (game/pool_capture.py), looked up with a box-projected ray
// (parallax corrected; mirror of core/cubemap.py). The capture is already tone-mapped: mix it AFTER the tone curve. PoolHall.bind_reflection sets these inputs.
uniform sampler2D water_reflect;
uniform vec3 water_axes[18];        // per cube face f: [3f] forward, [3f + 1] right, [3f + 2] up
uniform vec4 water_box_lo;          // the room box (xyz) the reflected ray is intersected with
uniform vec4 water_box_hi;
uniform vec4 water_probe;           // where the room was captured from (xyz)
uniform vec4 cube_params;           // x = tan(half the face fov)

vec3 box_project(vec3 p, vec3 r) {
    r = mix(r, vec3(1e-5), lessThan(abs(r), vec3(1e-5)));
    vec3 t = max((water_box_hi.xyz - p) / r, (water_box_lo.xyz - p) / r);       // per axis: the distance at which the ray leaves the box
    return p + r * min(min(t.x, t.y), t.z) - water_probe.xyz;
}

vec2 cube_uv(vec3 d) {
    int best = 0;
    float best_dot = -2.0;
    for (int f = 0; f < 6; f++) {
        float x = dot(d, water_axes[f * 3]);
        if (x > best_dot) { best_dot = x; best = f; }
    }
    vec3 fw = water_axes[best * 3], rt = water_axes[best * 3 + 1], up = water_axes[best * 3 + 2];
    vec2 uv = 0.5 + 0.5 * vec2(dot(d, rt), dot(d, up)) / (dot(d, fw) * cube_params.x);
    return vec2((float(best % 3) + uv.x) / 3.0, (float(best / 3) + uv.y) / 2.0);
}

// the room seen from p along direction r (tone-mapped colour)
vec3 room_reflection(vec3 p, vec3 r) {
    return texture(water_reflect, cube_uv(box_project(p, r))).rgb;
}
