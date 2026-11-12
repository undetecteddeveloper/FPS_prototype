#version 140
// G18 enemies (capsules) and the Backrooms door leaves: plain lit solids. Local position kept for the eyes.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
out vec3 world_pos;
out vec3 world_n;
out vec3 local_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    world_n = mat3(p3d_ModelMatrix) * p3d_Normal;
    local_pos = p3d_Vertex.xyz;
}
