#version 140
// Ống kính camera đội đầu, vẽ một lần trên ảnh đã ghép thế giới + súng: mắt cá (cùng công thức core/lens.py), viền màu, nhoè rìa, màn trập cuộn khi xoay, loé sáng,
// chỉnh màu, tối góc + vầng cam, nhiễu cảm biến. Vùng giữa chỉ tốn 3 mẫu; nhoè rìa chỉ lấy thêm mẫu ở nơi cần.
uniform sampler2D lens_scene;
uniform vec4 lens_warp;         // tỉ lệ khung, viền màu, nhoè rìa, bắt đầu nhoè
uniform vec4 lens_motion;       // nhoè thêm mỗi độ/s, màn trập cuộn mỗi độ/s, ranh giới bán kính nhoè ngoài, 0
uniform vec4 lens_vig;          // bắt đầu tối, tối hẳn, vầng cam, nhiễu
uniform vec4 lens_grade;        // tương phản, bão hoà, loé sáng, ngưỡng loé
uniform vec3 lens_tint;
uniform vec3 lens_frame;        // độ méo hiện tại, thời gian, tốc độ xoay (độ/s, dương = phải)
in vec2 v_uv;
out vec4 frag_color;

float hash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * 0.1031);
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}

void main() {
    vec2 p = v_uv * 2.0 - 1.0;
    vec2 q = vec2(p.x, p.y / lens_warp.x);
    float r2 = dot(q, q);
    float r = sqrt(r2);
    float k = lens_frame.x;
    float f = (1.0 + k * r2) / (1.0 + k);

    float turn = lens_frame.z;
    vec2 src = p * f;
    src.x += lens_motion.y * turn * p.y;                 // màn trập cuộn: hàng trên và hàng dưới được đọc ở hai thời điểm khác nhau
    vec2 uv_g = src * 0.5 + 0.5;
    float ca = lens_warp.y * r2;
    vec2 uv_r = (src * (1.0 + ca)) * 0.5 + 0.5;
    vec2 uv_b = (src * (1.0 - ca)) * 0.5 + 0.5;
    vec3 c = vec3(texture(lens_scene, uv_r).r, texture(lens_scene, uv_g).g, texture(lens_scene, uv_b).b);

    // nhoè rìa: dọc bán kính khi đứng yên, thêm theo tốc độ xoay. Bốn mẫu kèm lệch kênh để vệt nhoè tách màu như ảnh chụp
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

    // loé sáng: lấy từ các mức mipmap thô của chính ảnh, vùng sáng lan ra xung quanh
    if (lens_grade.z > 0.0) {
        vec3 b = textureLod(lens_scene, uv_g, 3.5).rgb * 0.55 + textureLod(lens_scene, uv_g, 5.5).rgb * 0.45;
        c += max(b - lens_grade.w, 0.0) / (1.0 - lens_grade.w) * lens_grade.z;
    }

    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = mix(vec3(l), c, lens_grade.y) * lens_tint;
    c = (c - 0.5) * lens_grade.x + 0.5;

    float v = 1.0 - smoothstep(lens_vig.x, lens_vig.y, r);
    float band = v * (1.0 - v) * 4.0;
    c = c * v + vec3(1.0, 0.40, 0.10) * band * lens_vig.z * clamp(l, 0.0, 1.0);

    float n = hash(gl_FragCoord.xy + fract(lens_frame.y * 7.13) * 411.0) - 0.5;
    c += n * lens_vig.w * (1.35 - clamp(l, 0.0, 1.0));

    frag_color = vec4(c, 1.0);
}
