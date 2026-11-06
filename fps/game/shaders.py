"""Loads GLSL shaders from the `assets/shaders/` folder (each shader has two files, .vert / .frag). Compile flags can be enabled with `defines`.

`#include "name.glsl"` inserts a file from the same folder (GLSL 1.40 has no built-in way to share code between two shaders). A file without a `#version` line gets
`#version 140`; `#define` lines are inserted right after the version line.
"""
from pathlib import Path

from panda3d.core import Shader

SHADER_DIR = Path(__file__).resolve().parent.parent.parent / 'assets' / 'shaders'


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
