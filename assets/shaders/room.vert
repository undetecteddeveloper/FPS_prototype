#version 140
// Pool hall (walls, ceiling, deck, steps, handrails): one mesh with two sets of coordinates.
//   texcoord 0 = position in metres on the face (the tiles are drawn from it, so they line up across neighbouring faces);
//   column `lightmap` = where the baked light of this face is in the lightmap atlas (a custom column: p3d_MultiTexCoord1 gets the SAME data as texcoord 0 when the node has one texture stage).
// The vertex colour holds the tile albedo (rgb) and the tile size in metres (a; 0 = plain colour).
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
in vec2 lightmap;

out vec4 vertex_color;
out vec2 metric;
out vec2 lightmap_uv;
out vec3 world_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vertex_color = p3d_Color;
    metric = p3d_MultiTexCoord0;
    lightmap_uv = lightmap;
    world_pos = (p3d_ModelMatrix * p3d_Vertex).xyz;
}
