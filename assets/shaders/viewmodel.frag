// Gun + hands: NO light of their own. Each point is converted to world coordinates (camera + position in camera space), then receives exactly the sun, ambient light, muzzle flash
// and tone curve of the world (light_common.glsl): turning away from the sun darkens the gun, and the gun body is lit on the side facing the sun.
// Uses the normal map from the glb file; the tangent frame is computed from derivatives, so the mesh needs no tangent column.
uniform sampler2D p3d_Texture0;
uniform sampler2D vm_normal_tex;
uniform vec4 vm_mat;            // gloss, highlight sharpness, environment reflection, normal map strength
uniform vec4 vm_sleeve;         // rgb sleeve colour; a = 1 replaces the texture's skin colour with the sleeve colour (the forearm in the asset is bare skin)
uniform vec3 vm_view_x;         // world camera's right / up / forward axes (changes every frame)
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
    if (m <= 1e-14) return n;                 // degenerate uv (a very small triangle sliver)
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

    // GL camera space (-z is forward) -> world
    vec3 local = vm_view_x * v_pos.x + vm_view_y * v_pos.y - vm_view_z * v_pos.z;
    vec3 p = look_camera_pos + local;
    vec3 n_w = normalize(vm_view_x * n.x + vm_view_y * n.y - vm_view_z * n.z);
    float dist = length(local);
    vec3 v_dir = -local / max(dist, 1e-4);

    float ndl = max(dot(n_w, look_sun_dir), 0.0);
    float spec = (ndl > 0.0 && vm_mat.y > 0.0) ? pow(max(dot(n_w, normalize(look_sun_dir + v_dir)), 0.0), vm_mat.y) : 0.0;
    // look_frame.y = share of the sun that reaches the player (0 in the shade of the pool hall, 1 on open ground); .z = scale of the ambient light there
    vec3 sun_c = look_sun_color * look_frame.y;
    vec3 ambient = ambient_at(n_w) * look_frame.z;
    vec3 lit = base.rgb * (ambient + sun_c * ndl);
    lit += sun_c * spec * vm_mat.x * (0.35 + base.rgb);

    // faint reflection: the metal edges pick up the sky and the sun
    float fres = pow(1.0 - max(dot(n_w, v_dir), 0.0), 4.0);
    vec3 r = reflect(-v_dir, n_w);
    lit += fres * vm_mat.z * ambient_at(r) * look_frame.z * 6.0
         + fres * vm_mat.z * sun_c * ndl * 0.35;

    if (look_flash_color.r > 0.0) lit += base.rgb * flash_light(p, n_w, vm_flash_falloff);

    frag_color = vec4(tonemap(lit), base.a);
}
