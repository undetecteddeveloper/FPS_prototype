#version 140
// Writes depth only, for the ceiling-lamp shadow map (lamp_shadows.py). No colour, no texture.
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
