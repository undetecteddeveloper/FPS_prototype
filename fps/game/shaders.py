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


_CACHE = {}


def load_glsl(name: str, defines=(), frag: str = None) -> Shader:
    """`frag` = another shader's fragment file (e.g. the sky's window quads reuse sky.frag).
    G13: the same request returns the same Shader object, so a rebuilt pass (the lens after an F2 change) reuses what the driver already compiled."""
    key = (name, tuple(defines), frag)
    if key in _CACHE:
        return _CACHE[key]

    def build(file_name):
        text = read_source(file_name)
        version = '#version 140\n'
        if text.lstrip().startswith('#version'):
            first, text = text.lstrip().split('\n', 1)
            version = first + '\n'
        return version + ''.join(f'#define {d}\n' for d in defines) + text

    shader = Shader.make(Shader.SL_GLSL, build(f'{name}.vert'), build(f'{frag or name}.frag'))
    if shader is None:
        raise RuntimeError(f'shader {name} không biên dịch được (xem log của Panda)')
    _CACHE[key] = shader
    return shader


def prepare(shader: Shader):
    """G13: queue a shader build for the GPU (compiled at the start of the next frame). The Intel driver still finishes its own compile at the first DRAW
    with a build (a 50-150 ms frame), so Game.warm_shader_builds also draws every build once at start-up."""
    from ursina import application
    gsg = application.base.win.get_gsg()
    if gsg is not None:
        shader.prepare(gsg.get_prepared_objects())
