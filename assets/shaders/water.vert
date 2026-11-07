#version 140
// Pool water: one flat quad at the water level; the fragment shader does everything (ripples, reflection, colour).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;

out vec3 world_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
}
