#version 140
// G13: the sky behind the window holes of an indoor map (game/sky.py hole_quads): a quad in world space just outside each hole; the view direction from the eye
// to the pixel is what sky.frag reads, so the holes show the same sky as the camera-centred sphere did. Drawn with the normal depth test (the wall hides the rest).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform vec3 look_camera_pos;
in vec4 p3d_Vertex;
out vec3 sky_dir;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    sky_dir = (p3d_ModelMatrix * p3d_Vertex).xyz - look_camera_pos;
}
