// Ánh sáng cho súng + tay: nửa cầu (trời / đất) + mặt trời + vệt bóng loáng nhẹ + viền sáng + đèn tia lửa đầu nòng.
uniform sampler2D p3d_Texture0;
uniform vec3 sun_dir;          // hướng TỚI mặt trời (không gian nhìn)
uniform vec3 sun_color;
uniform vec3 sky_color;
uniform vec3 ground_color;
uniform float spec_strength;
uniform float rim_strength;
uniform vec3 flash_pos;        // đèn tia lửa đầu nòng (không gian nhìn)
uniform vec3 flash_color;      // đã nhân cường độ; đen = tắt
uniform float flash_falloff;   // 1 / (1 + falloff * d^2)

varying vec3 v_pos;
varying vec3 v_normal;
varying vec2 v_uv;

void main() {
    vec4 base = texture2D(p3d_Texture0, v_uv);
    vec3 n = normalize(v_normal);
    vec3 view = normalize(-v_pos);
    if (!gl_FrontFacing) n = -n;

    vec3 ambient = mix(ground_color, sky_color, n.y * 0.5 + 0.5);
    float ndl = max(dot(n, sun_dir), 0.0);
    vec3 lit = ambient + sun_color * ndl;

    vec3 half_vec = normalize(sun_dir + view);
    float spec = pow(max(dot(n, half_vec), 0.0), 36.0) * spec_strength * ndl;
    float rim = pow(1.0 - max(dot(n, view), 0.0), 3.0) * rim_strength;

    vec3 to_flash = flash_pos - v_pos;
    float d2 = dot(to_flash, to_flash);
    float flash_ndl = max(dot(n, normalize(to_flash)), 0.0);
    vec3 flash = flash_color * flash_ndl / (1.0 + flash_falloff * d2);

    vec3 color = base.rgb * (lit + flash) + sun_color * spec + sky_color * rim;
    gl_FragColor = vec4(color, base.a);
}
