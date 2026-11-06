// SHARED lighting for the world (world.frag) and the rifle + hands (viewmodel.frag): same ceiling lamps, same shadows, same muzzle flash, same tone curve.
// The rifle has no lamp of its own, so it darkens when it moves into a dark place. `lamp_att` must match core/exposure.py (test_lighting checks the numbers).
uniform sampler2DShadow look_shadow_atlas;
uniform vec3 look_camera_pos;
uniform vec3 look_frame;            // x = current exposure (changes every frame)
uniform vec4 look_lamp;             // x, y, z of the first lamp, distance between two lamps
uniform vec4 look_lamp2;            // lamp count, radius where it fully cuts off, distance at half illuminance, intensity
uniform vec3 look_lamp_color;
uniform vec3 look_lamp_cone;        // cos of the full-bright cone angle, cos of the outer cone angle, fraction of light leaking outside the cone
uniform vec3 look_ambient_up;
uniform vec3 look_ambient_down;
uniform vec3 look_bounce;           // fake bounce colour from the light pool on the floor, per unit of lamp brightness
uniform vec4 look_shadow;           // mode (0 off, 1 real, 2 fake), constant bias (m), distance-dependent bias (m/m), emissive strength
uniform vec4 look_shadow_grid;      // number of grid columns, number of grid rows, 1/atlas width, 1/atlas height
uniform vec4 look_shadow_lod;       // closer to the camera than x: 4 shadow samples, closer than y: 1 sample, farther: none; z = number of lamps per side to check
uniform mat4 look_face_mat[5];      // lamp-to-point vector into clip space for faces +x, -x, -y, +z, -z
uniform vec3 look_flash_pos;        // muzzle flash, world coordinates (changes every frame while firing)
uniform vec3 look_flash_color;      // black = off

// ACES approximation (Narkowicz): dark areas are pushed to black, bright areas blow out to white quickly, matching the look of a cheap camera
vec3 tonemap(vec3 c) {
    c *= look_frame.x;
    return clamp((c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14), 0.0, 1.0);
}

float lamp_att(float d2, float d, float cos_down) {
    float x = d / look_lamp2.y;
    float x2 = x * x;
    float win = 1.0 - x2 * x2;
    float cone = mix(look_lamp_cone.z, 1.0, smoothstep(look_lamp_cone.y, look_lamp_cone.x, cos_down));
    return look_lamp2.w * cone * win * win / (1.0 + d2 / (look_lamp2.z * look_lamp2.z));
}

// real shadow: one lamp, lamp -> point vector v. `taps`: 4 samples (near the camera, soft shadow) or 1 sample (the hardware's bilinear filtering)
float lamp_shadow(float lamp, vec3 v, bool soft) {
    vec3 a = abs(v);
    int f;
    if (a.x >= a.y && a.x >= a.z) f = v.x > 0.0 ? 0 : 1;
    else if (a.y >= a.z) { if (v.y > 0.0) return 1.0; f = 2; }
    else f = v.z > 0.0 ? 3 : 4;
    vec4 c = look_face_mat[f] * vec4(v, 1.0);
    vec3 ndc = c.xyz / c.w;
    float ref = ndc.z * 0.5 + 0.5;
    if (ref >= 1.0) return 1.0;
    float tile = lamp * 5.0 + float(f);
    float col = mod(tile, look_shadow_grid.x);
    float row = floor(tile / look_shadow_grid.x + 1e-4);
    vec2 uv = (vec2(col, row) + ndc.xy * 0.5 + 0.5) / look_shadow_grid.xy;
    if (!soft) return texture(look_shadow_atlas, vec3(uv, ref));
    vec2 t = look_shadow_grid.zw;
    float s = texture(look_shadow_atlas, vec3(uv + vec2(-0.5, -0.5) * t, ref));
    s += texture(look_shadow_atlas, vec3(uv + vec2(0.5, -0.5) * t, ref));
    s += texture(look_shadow_atlas, vec3(uv + vec2(-0.5, 0.5) * t, ref));
    s += texture(look_shadow_atlas, vec3(uv + vec2(0.5, 0.5) * t, ref));
    return s * 0.25;
}

// Adds the light of the nearby lamps to one point. `dist` = distance from the camera (selects the shadow detail level); `shininess` <= 0 skips the specular highlight.
// A lamp that contributes too little skips its shadow map entirely: the dark area between two lamps is therefore also the cheapest.
float gather_lamps(vec3 p, vec3 n, vec3 v_dir, float dist, float shininess, out float spec, out float bounce) {
    int mode = int(look_shadow.x + 0.5);
    float count = look_lamp2.x, R = look_lamp2.y, ref2 = look_lamp2.z * look_lamp2.z;
    float kc = floor((p.z - look_lamp.z) / look_lamp.w + 0.5);
    int reach = int(look_shadow_lod.z + 0.5);
    bool want_shadow = mode == 1 && dist < look_shadow_lod.y;
    bool soft = dist < look_shadow_lod.x;
    float light = 0.0;
    spec = 0.0;
    bounce = 0.0;
    for (int j = -reach; j <= reach; j++) {
        float k = kc + float(j);
        if (k < 0.0 || k > count - 1.0) continue;
        vec3 lp = vec3(look_lamp.x, look_lamp.y, look_lamp.z + k * look_lamp.w);
        vec3 L = lp - p;
        float d2 = dot(L, L);
        if (d2 >= R * R) continue;
        float d = sqrt(d2);
        L /= d;
        float x = d / R;
        float win = 1.0 - x * x * x * x;
        // fake bounce light: the light pool on the floor under the lamp is reflected back onto nearby walls and ceiling (no direction, no shadow), falling off with distance to the lamp; when the lamp is off the bounce is gone too
        bounce += look_lamp2.w * win * win / (1.0 + d2 / (4.0 * ref2));
        float ndl = dot(n, L);
        if (ndl <= 0.0 || L.y <= 0.0) continue;                    // facing away from the lamp, or above the rim of the reflector (the reflector shades it)
        float att = lamp_att(d2, d, L.y);
        float amount = att * ndl;
        if (amount < 0.006) continue;
        float sh = want_shadow ? lamp_shadow(k, p + n * (look_shadow.y + look_shadow.z * d) - lp, soft) : 1.0;
        light += amount * sh;
        if (shininess > 0.0) spec += att * sh * pow(max(dot(n, normalize(L + v_dir)), 0.0), shininess);
    }
    return light;
}

// muzzle flash: point light without shadow. `falloff`: 1 / (1 + falloff * d^2)
vec3 flash_light(vec3 p, vec3 n, float falloff) {
    vec3 f = look_flash_pos - p;
    float d2 = dot(f, f);
    float ndl = max(dot(n, f / sqrt(max(d2, 1e-6))), 0.0);
    return look_flash_color * ndl / (1.0 + falloff * d2);
}
