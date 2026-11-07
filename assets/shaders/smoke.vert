#version 140
// Gun smoke: each puff is 4 vertices at its centre; the corner (+-1, +-1) pushes them out along the world camera's right / up axes (FrameLight PTA arrays),
// so the quad always faces the camera. The mesh lives under `render` with no transform: vertex positions are already world coordinates (y up).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform vec3 smoke_right;
uniform vec3 smoke_up;
in vec4 p3d_Vertex;
in vec2 corner;
in vec3 puff;                   // radius (m), alpha, seed 0..1
out vec2 v_corner;
out vec3 v_puff;
out vec3 v_world;

void main() {
    vec3 w = p3d_Vertex.xyz + (smoke_right * corner.x + smoke_up * corner.y) * puff.x;
    gl_Position = p3d_ModelViewProjectionMatrix * vec4(w, 1.0);
    v_corner = corner;
    v_puff = puff;
    v_world = w;
}
