#version 140
uniform sampler2D p3d_Texture0;
uniform vec4 halo_color;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    frag_color = texture(p3d_Texture0, v_uv) * halo_color;
}
