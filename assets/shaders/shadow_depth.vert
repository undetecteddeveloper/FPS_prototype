#version 140
// Chỉ ghi độ sâu cho bản đồ bóng của đèn trần (lamp_shadows.py). Không màu, không kết cấu.
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
