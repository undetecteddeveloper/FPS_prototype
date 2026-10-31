// Súng + tay (cảnh súng): skin bộ xương trên GPU, vẽ trong không gian nhìn (camera súng không xoay nên +y = lên).
// ENABLE_SKINNING: dùng cho mesh có skin (bàn tay); mesh cứng (thân súng, băng đạn...) vẽ không skin.
// Phần skin theo mẫu của panda3d-simplepbr (BSD-3-Clause, Mitchell Stokes): p3d_TransformTable + transform_weight / transform_index.
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform mat3 p3d_NormalMatrix;
#ifdef ENABLE_SKINNING
uniform mat4 p3d_TransformTable[100];
attribute vec4 transform_weight;
attribute vec4 transform_index;
#endif
attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec2 p3d_MultiTexCoord0;

varying vec3 v_pos;
varying vec3 v_normal;
varying vec2 v_uv;

void main() {
#ifdef ENABLE_SKINNING
    mat4 skin = p3d_TransformTable[int(transform_index.x)] * transform_weight.x
              + p3d_TransformTable[int(transform_index.y)] * transform_weight.y
              + p3d_TransformTable[int(transform_index.z)] * transform_weight.z
              + p3d_TransformTable[int(transform_index.w)] * transform_weight.w;
    vec4 model_pos = skin * p3d_Vertex;
    vec3 model_normal = mat3(skin) * p3d_Normal;
#else
    vec4 model_pos = p3d_Vertex;
    vec3 model_normal = p3d_Normal;
#endif
    vec4 view_pos = p3d_ModelViewMatrix * model_pos;
    v_pos = view_pos.xyz;
    v_normal = p3d_NormalMatrix * model_normal;
    v_uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ProjectionMatrix * view_pos;
}
