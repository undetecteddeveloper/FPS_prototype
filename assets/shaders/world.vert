#version 140
// Thế giới (mặt đất, bia, cột, bờ đất): chuyển toạ độ thế giới cho fragment để tính sương mù và chi tiết mặt đất.
// Khung theo shader unlit_with_fog của Ursina (MIT); tọa độ UV nhận texture_scale / texture_offset như mọi shader của Ursina.
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
in vec4 p3d_Color;
uniform vec2 texture_scale;
uniform vec2 texture_offset;

out vec2 uvs;
out vec4 vertex_color;
out vec3 world_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uvs = (p3d_MultiTexCoord0 * texture_scale) + texture_offset;
    vertex_color = p3d_Color;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
}
