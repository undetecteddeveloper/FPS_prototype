#version 140
// Ánh sáng nửa cầu + mặt trời (pháp tuyến lấy từ đạo hàm vị trí nên không phụ thuộc mesh có normal hay không),
// nhiễu chi tiết hai tỉ lệ trên mặt nằm ngang (phá ô lưới lặp, mờ dần ở xa), và sương mù theo khoảng cách
// hoà vào màu chân trời: xa dần nhạt đi, mặt đất không còn bị cắt ngang bởi đường chân trời.
uniform sampler2D p3d_Texture0;
uniform sampler2D look_detail_tex;
uniform vec4 p3d_ColorScale;
uniform vec3 look_camera_pos;
uniform vec3 look_sun_dir;          // hướng TỚI mặt trời, thế giới
uniform vec3 look_sun_color;
uniform vec3 look_sky_color;
uniform vec3 look_ground_color;
uniform vec4 look_fog;        // rgb = màu chân trời, a = mật độ (exp); tên có tiền tố look_ để không trùng đầu vào mặc định của shader Ursina (camera_world_position, fog_color...), thứ đặt riêng cho từng vật thể và đè lên đầu vào của render
uniform float look_detail_strength;

in vec2 uvs;
in vec4 vertex_color;
in vec3 world_pos;
out vec4 frag_color;

void main() {
    vec4 base = texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color;
    vec3 to_cam = look_camera_pos - world_pos;
    float dist = length(to_cam);

    vec3 n = normalize(cross(dFdx(world_pos), dFdy(world_pos)));
    if (dot(n, to_cam) < 0.0) n = -n;

    // chi tiết: chỉ mặt hướng lên; hai lớp nhiễu khác tỉ lệ, mờ dần từ 40 m tới 160 m (xa hơn thì nhấp nháy)
    float up = smoothstep(0.6, 0.9, n.y);
    float fade = 1.0 - smoothstep(40.0, 160.0, dist);
    float noise = texture(look_detail_tex, world_pos.xz * 0.21).r * 0.6 + texture(look_detail_tex, world_pos.xz * 0.043 + 0.37).r * 0.4;
    base.rgb *= 1.0 + (noise - 0.5) * look_detail_strength * up * fade;

    vec3 ambient = mix(look_ground_color, look_sky_color, n.y * 0.5 + 0.5);
    float ndl = max(dot(n, look_sun_dir), 0.0);
    vec3 lit = base.rgb * (ambient + look_sun_color * ndl);

    float fog = 1.0 - exp(-look_fog.a * dist);
    frag_color = vec4(mix(lit, look_fog.rgb, clamp(fog, 0.0, 1.0)), base.a);
}
