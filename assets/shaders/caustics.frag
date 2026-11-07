#version 140
// Caustic pass (G11): brightness of one piece of a light triangle = its area on flat water / its area where it landed (one texel). Drawn with additive blending, two-sided:
// folded triangles overlap and add up, flat water gives exactly 1.
in vec2 flat_pos;
uniform vec4 caus_texel;            // x = area of one texel (m^2), y = brightest value written (keeps a degenerate triangle from writing a huge spike)

out vec4 frag_color;

void main() {
    vec2 a = dFdx(flat_pos), b = dFdy(flat_pos);
    float flat_area = abs(a.x * b.y - a.y * b.x);
    frag_color = vec4(min(flat_area / caus_texel.x, caus_texel.y), 0.0, 0.0, 1.0);
}
