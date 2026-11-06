"""Nạp shader GLSL từ thư mục `shaders/` (mỗi shader hai file .vert / .frag). Có thể bật cờ biên dịch bằng `defines`.

`#include "tên.glsl"` chèn file cùng thư mục (GLSL 1.40 không có sẵn cách dùng chung mã giữa hai shader). File không có dòng `#version` thì được thêm
`#version 140`; `#define` chèn ngay sau dòng version.
"""
from pathlib import Path

from panda3d.core import Shader

SHADER_DIR = Path(__file__).resolve().parent.parent.parent / 'shaders'


def expand_includes(text: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#include'):
            name = stripped.split('"')[1]
            out.append((SHADER_DIR / name).read_text(encoding='utf-8'))
        else:
            out.append(line)
    return '\n'.join(out) + '\n'


def read_source(file_name: str) -> str:
    return expand_includes((SHADER_DIR / file_name).read_text(encoding='utf-8'))


def load_glsl(name: str, defines=()) -> Shader:
    def build(file_name):
        text = read_source(file_name)
        version = '#version 140\n'
        if text.lstrip().startswith('#version'):
            first, text = text.lstrip().split('\n', 1)
            version = first + '\n'
        return version + ''.join(f'#define {d}\n' for d in defines) + text

    shader = Shader.make(Shader.SL_GLSL, build(f'{name}.vert'), build(f'{name}.frag'))
    if shader is None:
        raise RuntimeError(f'shader {name} không biên dịch được (xem log của Panda)')
    return shader
