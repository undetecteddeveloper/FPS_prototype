#version 140
// G13: the finished lens image (drawn at the 3D resolution of F2 'Độ phân giải 3D', below 100%) stretched over the window with linear filtering.
// Text and the F1 / F2 panels are drawn after this at the full window size, so they stay sharp.
uniform sampler2D blit_src;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    frag_color = vec4(texture(blit_src, v_uv).rgb, 1.0);
}
