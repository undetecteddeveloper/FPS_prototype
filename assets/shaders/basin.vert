#version 140
// G12: the pool basin under the water as real geometry (core/poolmap.py `basin_faces`), drawn only while some pixel looks through the water.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 world_pos;
out vec3 world_normal;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    world_normal = p3d_Normal;                       // the mesh sits in world coordinates (no transform)
}
