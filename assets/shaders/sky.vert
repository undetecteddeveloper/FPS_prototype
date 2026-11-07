#version 140
// Sky dome: only the ROTATION of the camera is applied (w = 0 drops the translation), and the depth is pushed to the far plane, so the dome is always behind everything and never clips.
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
in vec4 p3d_Vertex;
out vec3 sky_dir;

void main() {
    sky_dir = p3d_Vertex.xyz;                                   // the dome is not rotated: model direction = world direction
    vec4 v = p3d_ModelViewMatrix * vec4(p3d_Vertex.xyz, 0.0);
    vec4 p = p3d_ProjectionMatrix * vec4(v.xyz, 1.0);
    gl_Position = vec4(p.xy, p.w, p.w);
}
