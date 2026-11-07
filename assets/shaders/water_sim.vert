#version 140
// One fullscreen card per simulation pass (game/water_sim.py); the fragment shader works per texel with texelFetch, so no texture coordinates are needed.
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
