#version 140
// Water droplets (game/splash.py): each drop is a quad built here, facing the camera and STRETCHED along its velocity (a camera sees a moving drop as a short streak).
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;                 // drop centre (world)
in vec2 corner;                     // -1..1
in vec3 drop;                       // velocity (m/s)
in vec2 look;                       // x = radius (m), y = alpha

#include "light_common.glsl"
#define SUN_WINDOW_VERTEX
#include "sun_window.glsl"

out vec2 uv;
out float alpha;
out float sunlit;

void main() {
    vec3 c = p3d_Vertex.xyz;
    float speed = length(drop);
    vec3 axis = speed > 1e-3 ? drop / speed : vec3(0.0, 1.0, 0.0);
    vec3 to_cam = normalize(look_camera_pos - c);
    vec3 side = cross(axis, to_cam);
    side = length(side) > 1e-4 ? normalize(side) : vec3(1.0, 0.0, 0.0);
    float len = look.x + speed * 0.025;
    vec3 p = c + axis * corner.y * len + side * corner.x * look.x;
    gl_Position = p3d_ModelViewProjectionMatrix * vec4(p, 1.0);
    uv = corner;
    alpha = look.y;
    sunlit = sun_visible(c);
}
