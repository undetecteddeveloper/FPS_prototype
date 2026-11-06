#version 140
// Quầng quanh mọi bóng đèn, MỘT lần vẽ: mọi đỉnh của một thẻ nằm ở tâm đèn, shader bung ra thành thẻ quay về camera theo uv.
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform float halo_size;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 v_uv;

void main() {
    vec4 view = p3d_ModelViewMatrix * p3d_Vertex;
    view.xy += (p3d_MultiTexCoord0 - 0.5) * halo_size;
    gl_Position = p3d_ProjectionMatrix * view;
    v_uv = p3d_MultiTexCoord0;
}
