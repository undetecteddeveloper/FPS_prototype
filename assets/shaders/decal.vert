#version 140
// Bullet-hole decals (one mesh, a ring of quads; game/decals.py). Per vertex: position, tint (colour), uv in the hole atlas, and two custom columns:
//   `lightmap` = where the baked light of the wall under the hole is in the room's lightmap atlas (-1, -1 = none: the flat map lights the decal from the sun and ambient light),
//   `hole`     = (birth clock, cell index in the atlas, width of the decal in metres, unused).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
in vec2 lightmap;
in vec4 hole;

out vec2 v_uv;
out vec4 v_color;
out vec3 world_pos;
out vec2 lightmap_uv;
out vec4 v_hole;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
    v_color = p3d_Color;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
    lightmap_uv = lightmap;
    v_hole = hole;
}
