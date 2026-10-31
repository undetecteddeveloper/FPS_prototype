"""Nạp shader GLSL từ thư mục `shaders/` (mỗi shader hai file .vert / .frag). Có thể bật cờ biên dịch bằng `defines`.

Mã nguồn dùng `#version 120` (Panda cấp thuộc tính `p3d_*`); `#define` chèn ngay sau dòng version.
"""
from pathlib import Path

from panda3d.core import Shader

SHADER_DIR = Path(__file__).resolve().parent.parent.parent / 'shaders'


def load_glsl(name: str, defines=()) -> Shader:
    head = '#version 120\n' + ''.join(f'#define {d}\n' for d in defines)
    vert = (SHADER_DIR / f'{name}.vert').read_text(encoding='utf-8')
    frag = (SHADER_DIR / f'{name}.frag').read_text(encoding='utf-8')
    shader = Shader.make(Shader.SL_GLSL, head + vert, head + frag)
    if shader is None:
        raise RuntimeError(f'shader {name} không biên dịch được (xem log của Panda)')
    return shader
