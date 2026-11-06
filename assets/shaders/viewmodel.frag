// Súng + tay: KHÔNG có đèn riêng. Mỗi điểm được đổi sang toạ độ thế giới (camera + vị trí trong hệ camera) rồi nhận đúng các đèn trần, bóng, ánh nền, tia lửa
// và đường tông của thế giới (light_common.glsl): đi tới chỗ tối thì súng tối theo, đèn ở phía nào thì thân súng sáng phía đó.
// Dùng normal map của file glb, tính khung tiếp tuyến từ đạo hàm nên không cần cột tangent trong mesh.
uniform sampler2D p3d_Texture0;
uniform sampler2D vm_normal_tex;
uniform vec4 vm_mat;            // độ bóng, độ tập trung vệt sáng, phản chiếu môi trường, độ nổi normal map
uniform vec4 vm_sleeve;         // rgb màu tay áo, a = 1 thì màu da của texture được thay bằng tay áo (cẳng tay trong asset là da trần)
uniform vec3 vm_view_x;         // trục phải / lên / trước của camera thế giới (đổi mỗi khung)
uniform vec3 vm_view_y;
uniform vec3 vm_view_z;
uniform float vm_flash_falloff;
uniform float vm_albedo;

#include "light_common.glsl"

in vec3 v_pos;
in vec3 v_normal;
in vec2 v_uv;
out vec4 frag_color;

vec3 mapped_normal(vec3 n) {
    vec3 s = texture(vm_normal_tex, v_uv).xyz * 2.0 - 1.0;
    s.xy *= vm_mat.w;
    vec3 dp1 = dFdx(v_pos), dp2 = dFdy(v_pos);
    vec2 du1 = dFdx(v_uv), du2 = dFdy(v_uv);
    vec3 dp2p = cross(dp2, n), dp1p = cross(n, dp1);
    vec3 t = dp2p * du1.x + dp1p * du2.x;
    vec3 b = dp2p * du1.y + dp1p * du2.y;
    float m = max(dot(t, t), dot(b, b));
    if (m <= 1e-14) return n;                 // uv suy biến (mảnh tam giác rất nhỏ)
    m = 1.0 / sqrt(m);
    return normalize(t * m * s.x + b * m * s.y + n * s.z);
}

void main() {
    vec4 base = texture(p3d_Texture0, v_uv);
    if (vm_sleeve.a > 0.5) {
        float l = dot(base.rgb, vec3(0.3, 0.6, 0.1));
        base.rgb = vm_sleeve.rgb * (0.55 + 0.9 * l);
    }
    else base.rgb *= vm_albedo;
    vec3 n = normalize(v_normal);
    if (!gl_FrontFacing) n = -n;
    n = mapped_normal(n);

    // hệ camera GL (-z là phía trước) -> thế giới
    vec3 local = vm_view_x * v_pos.x + vm_view_y * v_pos.y - vm_view_z * v_pos.z;
    vec3 p = look_camera_pos + local;
    vec3 n_w = normalize(vm_view_x * n.x + vm_view_y * n.y - vm_view_z * n.z);
    float dist = length(local);
    vec3 v_dir = -local / max(dist, 1e-4);

    float spec, bounce;
    // truyền khoảng cách >= ngưỡng bóng mềm: súng rất gần camera nhưng 1 mẫu bóng là đủ cho nó
    float light = gather_lamps(p, n_w, v_dir, max(dist, look_shadow_lod.x), vm_mat.y, spec, bounce);
    vec3 ambient = mix(look_ambient_down, look_ambient_up, n_w.y * 0.5 + 0.5) + look_bounce * bounce * (1.0 - 0.4 * max(n_w.y, 0.0));
    vec3 diffuse = ambient + look_lamp_color * light;
    vec3 lit = base.rgb * diffuse;
    lit += look_lamp_color * spec * vm_mat.x * (0.35 + base.rgb);

    // phản chiếu mờ: đang ở chỗ có sáng thì mép kim loại bắt sáng theo ánh nền tại chỗ; chỗ tối thì mất
    float fres = pow(1.0 - max(dot(n_w, v_dir), 0.0), 4.0);
    vec3 r = reflect(-v_dir, n_w);
    lit += fres * vm_mat.z * mix(look_ambient_down, look_ambient_up, r.y * 0.5 + 0.5) * 6.0
         + fres * vm_mat.z * look_lamp_color * (light + bounce * 0.02) * 0.35;

    if (look_flash_color.r > 0.0) lit += base.rgb * flash_light(p, n_w, vm_flash_falloff);

    frag_color = vec4(tonemap(lit), base.a);
}
