#version 140
// Thế giới trong phòng tập kín: đèn trần + bóng (light_common.glsl, dùng chung với súng), tia lửa đầu nòng, AO giả ở chân tường / quanh cột / dưới trần,
// vân vật liệu vẽ theo toạ độ thế giới (gạch lát sàn, bê tông đổ cốp pha, trần tấm), bụi trong phòng hoà vào tối.
// Pháp tuyến lấy từ đạo hàm vị trí (mesh không cần normal). Mọi uniform riêng có tiền tố look_ (đầu vào mặc định của shader
// Ursina như fog_color đặt trên từng vật thể sẽ đè lên đầu vào cùng tên đặt ở render).
uniform sampler2D p3d_Texture0;
uniform sampler2D look_detail_tex;
uniform vec4 p3d_ColorScale;
uniform vec4 look_fog;              // rgb = màu bụi trong phòng, a = mật độ (exp)
uniform float look_detail_strength;
uniform float look_material;        // 0 thường, 1 sàn gạch, 2 tường bê tông, 3 cột/dầm, 4 trần, 5 tự phát sáng, 6 biển
uniform vec4 look_room;             // nửa bề rộng, z tường sau, z tường cuối, chiều cao trần
uniform vec4 look_pillar;           // z cột đầu, khoảng cách cột, nửa bề rộng cột (dọc z), độ nhô cột
uniform vec2 look_flash_world;      // nhân độ sáng tia lửa lên thế giới, falloff

#include "light_common.glsl"

in vec2 uvs;
in vec4 vertex_color;
in vec3 world_pos;
out vec4 frag_color;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// Phần "đặc" (không phải rãnh) của một lưới rãnh, đã lọc hộp theo kích thước điểm ảnh: rãnh chiếm [0, g) của mỗi ô.
// Ở xa (ô nhỏ hơn điểm ảnh) kết quả tiến về giá trị trung bình 1 - g thay vì nhấp nháy (moiré).
vec2 groove_solid(vec2 p, vec2 w, vec2 g) {
    w = max(w, vec2(1e-4));
    vec2 a = p + 0.5 * w, b = p - 0.5 * w;
    vec2 ia = floor(a) * g + min(fract(a), g);
    vec2 ib = floor(b) * g + min(fract(b), g);
    return 1.0 - (ia - ib) / w;
}

// dải [y0, y1] theo một toạ độ, mép làm mềm theo điểm ảnh
float band(float y, float y0, float y1, float fw) {
    return smoothstep(y0 - fw, y0 + fw, y) * (1.0 - smoothstep(y1 - fw, y1 + fw, y));
}

// --- vật liệu ---
vec3 brick_floor(vec3 p_w, out float gloss) {
    vec2 size = vec2(0.30, 0.15);                         // gạch lát 30 x 15 cm, xếp so le theo hàng
    vec2 p = p_w.xz / size;
    vec2 w = fwidth(p);                                   // lấy trước khi so le (so le làm p.x nhảy ở mép hàng)
    float row = floor(p.y);
    p.x += 0.5 * mod(row, 2.0);
    vec2 cell = floor(p);
    vec2 s = groove_solid(p, w, vec2(0.012) / size);      // mạch vữa 1,2 cm
    float solid = s.x * s.y;
    float near = 1.0 - smoothstep(0.25, 0.8, max(w.x, w.y));      // ô gạch nhỏ hơn ~1/4 điểm ảnh: bỏ khác biệt từng viên
    float h = hash12(cell + 17.0);
    float h2 = hash12(cell * 1.7 + 3.1);
    vec3 brick = vec3(0.47, 0.30, 0.24) * (1.0 + (h - 0.5) * 0.38 * near);
    brick = mix(brick, vec3(0.43, 0.32, 0.26), step(0.82, h2) * 0.7 * near);   // vài viên nâu xám
    // mép viên gạch tối nhẹ (gờ vát), cũng mờ dần ở xa
    vec2 f = fract(p);
    float edge = min(min(f.x, 1.0 - f.x) * size.x, min(f.y, 1.0 - f.y) * size.y);
    brick *= mix(1.0, 0.82 + 0.18 * smoothstep(0.0, 0.025, edge), near);
    vec3 mortar = vec3(0.27, 0.26, 0.24);
    gloss = solid;
    return mix(mortar, brick, solid);
}

vec3 paint(vec3 concrete, float y, float fw) {
    // chân tường sơn xanh xám tới 1,1 m, một vạch vàng an toàn 1,1-1,2 m
    vec3 c = mix(concrete, vec3(0.20, 0.25, 0.29), 1.0 - smoothstep(1.1 - fw, 1.1 + fw, y));
    return mix(c, vec3(0.78, 0.58, 0.14), band(y, 1.1, 1.2, fw));
}

vec3 concrete_wall(vec3 base, vec3 p_w, vec3 n, bool panels) {
    vec2 q = abs(n.x) > 0.5 ? p_w.zy : p_w.xy;
    float blotch = texture(look_detail_tex, q * 0.17).r * 0.6 + texture(look_detail_tex, q * 0.045 + 0.31).r * 0.4;
    vec3 c = base * (0.82 + 0.36 * blotch);
    if (panels) {
        // cốp pha 2,5 x 1,25 m: mạch nối mảnh, lỗ ty giằng ở 1/4 tấm
        vec2 pp = q / vec2(2.5, 1.25);
        vec2 s = groove_solid(pp, fwidth(pp), vec2(0.008) / vec2(2.5, 1.25));
        c *= mix(0.62, 1.0, s.x * s.y);
        vec2 t = q / 0.625;
        vec2 ft = fract(t) - 0.5;
        float fw = length(fwidth(t)) * 0.625;
        float hole = 1.0 - smoothstep(0.012 - fw, 0.012 + fw, length(ft) * 0.625);
        c *= 1.0 - 0.55 * hole * (1.0 - smoothstep(0.02, 0.05, fw));
    }
    float fwy = fwidth(p_w.y);
    return paint(c, p_w.y, fwy);
}

vec3 ceiling_panels(vec3 base, vec3 p_w) {
    vec2 pp = p_w.xz / 1.25;
    vec2 s = groove_solid(pp, fwidth(pp), vec2(0.02) / 1.25);
    float blotch = texture(look_detail_tex, p_w.xz * 0.13).r;
    return base * (0.85 + 0.3 * blotch) * mix(0.55, 1.0, s.x * s.y);
}

// --- AO giả: tối dần ở chân tường, quanh cột, dưới trần, sát dầm ---
float fake_ao(vec3 p, vec3 n) {
    float W = look_room.x;
    float dx = W - abs(p.x);                                       // tới mặt tường bên
    float dzw = min(p.z - look_room.y, look_room.z - p.z);         // tới tường sau / tường cuối
    float kp = floor((p.z - look_pillar.x) / look_pillar.y + 0.5);
    float dpz = abs(p.z - (look_pillar.x + kp * look_pillar.y)) - look_pillar.z;   // tới mép cột gần nhất (dọc z)
    float ao = 1.0;
    if (n.y > 0.5) {                                               // sàn
        ao *= mix(0.45, 1.0, smoothstep(0.0, 1.1, dx));
        ao *= mix(0.45, 1.0, smoothstep(0.0, 1.1, dzw));
        vec2 d = vec2(dx - look_pillar.w, dpz);
        float sd = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
        ao *= mix(0.55, 1.0, smoothstep(0.0, 0.8, sd));
    } else if (n.y < -0.5) {                                       // trần, đáy dầm
        ao *= mix(0.5, 1.0, smoothstep(0.0, 1.4, dx));
        ao *= mix(0.55, 1.0, smoothstep(0.0, 0.6, abs(dpz + look_pillar.z) - 0.2));
    } else {                                                       // mặt đứng
        ao *= mix(0.5, 1.0, smoothstep(0.0, 0.7, p.y));
        ao *= mix(0.6, 1.0, smoothstep(0.0, 0.9, look_room.w - p.y));
        if (abs(n.x) > 0.5 && dx < 0.02) ao *= mix(0.6, 1.0, smoothstep(0.0, 0.45, dpz));   // tường sát cột
        if (abs(n.z) > 0.5) ao *= mix(0.6, 1.0, smoothstep(0.0, 0.45, min(dx, dzw)));     // mặt bên cột / góc phòng
    }
    return ao;
}

void main() {
    vec4 base = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    int mat = int(look_material + 0.5);
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);
    float fog = clamp(1.0 - exp(-look_fog.a * dist), 0.0, 1.0);

    if (mat == 5) {                                                // bóng đèn, lòng chóa: nguồn sáng, chói hơn mọi thứ nó chiếu vào
        frag_color = vec4(mix(tonemap(base.rgb * look_shadow.w), look_fog.rgb, fog * 0.6), 1.0);
        return;
    }

    vec3 n = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    if (dot(n, to_cam) < 0.0) n = -n;

    float gloss = 0.0;
    if (mat == 1) base.rgb *= brick_floor(world_pos, gloss);
    else if (mat == 2) base.rgb = concrete_wall(base.rgb, world_pos, n, true);
    else if (mat == 3) base.rgb = concrete_wall(base.rgb, world_pos, n, false);
    else if (mat == 4) base.rgb = ceiling_panels(base.rgb, world_pos);

    // nhiễu chi tiết trên mặt hướng lên (sàn, nóc vật), mờ dần từ 40 m tới 160 m (xa hơn thì nhấp nháy)
    float up = smoothstep(0.6, 0.9, n.y);
    float fade = 1.0 - smoothstep(40.0, 160.0, dist);
    if (up * fade > 0.0) {
        float noise = texture(look_detail_tex, world_pos.xz * 0.21).r * 0.6 + texture(look_detail_tex, world_pos.xz * 0.043 + 0.37).r * 0.4;
        float detail = mat == 1 ? 0.6 : 1.0;
        base.rgb *= 1.0 + (noise - 0.5) * look_detail_strength * detail * up * fade;
    }

    float ao = fake_ao(world_pos, n);
    vec3 ambient = mix(look_ambient_down, look_ambient_up, n.y * 0.5 + 0.5) * ao;

    float spec, bounce;
    float light = gather_lamps(world_pos, n, to_cam / max(dist, 1e-4), dist, mat == 1 ? 40.0 : 0.0, spec, bounce);
    float direct_ao = mix(1.0, ao, 0.45);                           // AO cũng làm tối nhẹ ánh đèn (bù cho thiếu ánh dội)
    ambient += look_bounce * bounce * ao * (1.0 - 0.6 * up);        // mặt đứng và trần nhận ánh dội nhiều hơn sàn
    vec3 lit = base.rgb * (ambient + look_lamp_color * light * direct_ao) + look_lamp_color * spec * gloss * 0.10;
    if (look_flash_color.r > 0.0) lit += base.rgb * flash_light(world_pos, n, look_flash_world.y) * look_flash_world.x;
    if (mat == 6) lit += base.rgb * base.rgb * 0.85;                // biển: chữ sơn phản quang (nền tối gần như không phản lại), không có đèn nào thì vẫn đọc được từ xa

    frag_color = vec4(mix(tonemap(lit), look_fog.rgb, fog), base.a);
}
