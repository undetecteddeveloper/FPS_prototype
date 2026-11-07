#version 140
// Gun smoke: each puff is 4 vertices at its centre; the corner (+-1, +-1) pushes them out along the world camera's right / up axes (FrameLight PTA arrays),
// so the quad always faces the camera. The mesh lives under `render` with no transform: vertex positions are already world coordinates (y up).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform vec3 smoke_right;
uniform vec3 smoke_up;
uniform vec3 smoke_color;
uniform vec4 smoke_fog;         // rgb = haze colour, a = density (exp)
uniform vec2 smoke_fill;        // radius / distance where the fade starts, where it is gone

#include "light_common.glsl"
in vec4 p3d_Vertex;
in vec2 corner;
in vec3 puff;                   // radius (m), alpha, seed 0..1
out vec2 v_corner;
out vec3 v_puff;
out vec3 v_world;
out vec2 v_wisp;                // G13: the corner rotated by the puff's seed (linear in the corner, so interpolating it is exact)
flat out vec3 v_lit;            // G13: smoke colour x the light (uniforms only): once per vertex instead of once per pixel
#ifdef SMOKE_LITE
out vec4 v_col;                 // G13 'Khói súng: Đơn giản': rgb = tone-mapped + hazed colour, a = the fade by angular size, both at the corners and interpolated
#endif

void main() {
    vec3 w = p3d_Vertex.xyz + (smoke_right * corner.x + smoke_up * corner.y) * puff.x;
    gl_Position = p3d_ModelViewProjectionMatrix * vec4(w, 1.0);
    v_corner = corner;
    v_puff = puff;
    v_world = w;
    float s = puff.z * 6.2831;
    v_wisp = mat2(cos(s), -sin(s), sin(s), cos(s)) * corner;
    v_lit = smoke_color * (ambient_at(vec3(0.0, 1.0, 0.0)) + look_sun_color * (0.45 + 0.4 * max(look_sun_dir.y, 0.0)));
#ifdef SMOKE_LITE
    float dist = length(w - look_camera_pos);
    float fill = 1.0 - smoothstep(smoke_fill.x, smoke_fill.y, puff.x / max(dist, 1e-3));
    float fog = clamp(1.0 - exp(-smoke_fog.a * dist), 0.0, 1.0);
    float shade = mix(0.78, 1.0, corner.y * 0.5 + 0.5);
    v_col = vec4(mix(tonemap(v_lit * shade), smoke_fog.rgb, fog), fill);
#endif
}
