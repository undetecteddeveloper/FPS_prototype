// Ánh sáng DÙNG CHUNG cho thế giới (world.frag) và súng + tay (viewmodel.frag): cùng đèn trần, cùng bóng, cùng tia lửa, cùng đường tông.
// Súng không có đèn riêng nên đi vào chỗ tối là súng tối theo. `lamp_att` phải khớp core/exposure.py (test_lighting kiểm con số).
uniform sampler2DShadow look_shadow_atlas;
uniform vec3 look_camera_pos;
uniform vec3 look_frame;            // x = phơi sáng hiện tại (đổi mỗi khung)
uniform vec4 look_lamp;             // x, y, z đèn đầu, khoảng cách giữa hai đèn
uniform vec4 look_lamp2;            // số đèn, bán kính tắt hẳn, khoảng cách nửa độ rọi, cường độ
uniform vec3 look_lamp_color;
uniform vec3 look_lamp_cone;        // cos góc nón rọi đủ sáng, cos góc nón ngoài, phần sáng lọt ra ngoài nón
uniform vec3 look_ambient_up;
uniform vec3 look_ambient_down;
uniform vec3 look_bounce;           // màu ánh dội giả từ vũng sáng trên sàn, tính cho mỗi đơn vị độ sáng đèn
uniform vec4 look_shadow;           // chế độ (0 tắt, 1 thật, 2 giả), bias hằng (m), bias theo khoảng cách (m/m), độ phát sáng
uniform vec4 look_shadow_grid;      // số cột ô, số hàng ô, 1/rộng atlas, 1/cao atlas
uniform vec4 look_shadow_lod;       // cách camera dưới x: 4 mẫu bóng, dưới y: 1 mẫu, xa hơn: không lấy; z = số đèn mỗi bên cần xét
uniform mat4 look_face_mat[5];      // vector đèn->điểm sang clip của mặt +x, -x, -y, +z, -z
uniform vec3 look_flash_pos;        // tia lửa đầu nòng, toạ độ thế giới (đổi mỗi khung lúc bắn)
uniform vec3 look_flash_color;      // đen = tắt

// ACES xấp xỉ (Narkowicz): vùng tối bị ép xuống đen, vùng sáng cháy trắng nhanh, đúng chất camera giá rẻ
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

// bóng thật: một đèn, vector đèn -> điểm v. `taps`: 4 mẫu (gần camera, bóng mềm) hoặc 1 mẫu (lọc song tuyến của phần cứng)
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

// Cộng ánh sáng của các đèn gần lên một điểm. `dist` = cách camera (chọn mức chi tiết của bóng); `shininess` <= 0 thì khỏi tính vệt bóng.
// Đèn nào đóng góp quá nhỏ thì bỏ qua luôn bản đồ bóng: vùng tối giữa hai đèn vì thế cũng là vùng rẻ nhất.
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
        // ánh sáng dội giả: vũng sáng trên sàn dưới đèn hắt lại lên tường / trần gần đó (không hướng, không bóng), giảm theo khoảng cách tới đèn; đèn tắt thì ánh dội cũng mất
        bounce += look_lamp2.w * win * win / (1.0 + d2 / (4.0 * ref2));
        float ndl = dot(n, L);
        if (ndl <= 0.0 || L.y <= 0.0) continue;                    // quay lưng với đèn, hoặc ở trên mép chóa (chóa che)
        float att = lamp_att(d2, d, L.y);
        float amount = att * ndl;
        if (amount < 0.006) continue;
        float sh = want_shadow ? lamp_shadow(k, p + n * (look_shadow.y + look_shadow.z * d) - lp, soft) : 1.0;
        light += amount * sh;
        if (shininess > 0.0) spec += att * sh * pow(max(dot(n, normalize(L + v_dir)), 0.0), shininess);
    }
    return light;
}

// tia lửa đầu nòng: đèn điểm không bóng. `falloff`: 1 / (1 + falloff * d^2)
vec3 flash_light(vec3 p, vec3 n, float falloff) {
    vec3 f = look_flash_pos - p;
    float d2 = dot(f, f);
    float ndl = max(dot(n, f / sqrt(max(d2, 1e-6))), 0.0);
    return look_flash_color * ndl / (1.0 + falloff * d2);
}
