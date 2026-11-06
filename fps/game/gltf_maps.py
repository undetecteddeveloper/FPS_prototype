"""Reads normal maps from the glb file. `gltf_patch.py` drops the normal maps when the model is loaded (Panda's fixed-function path cannot use them), so the gun's own shader fetches them here.

Downscaled to at most 1024 x 1024: the gun takes a small part of the screen; 2048 only costs memory and GPU upload time.
"""
import json
import struct
from pathlib import Path

from panda3d.core import PNMImage, SamplerState, StringStream, Texture

MAX_SIZE = 1024


def glb_chunks(path: Path) -> tuple:
    """(decoded JSON, binary part) of a glb file."""
    with open(path, 'rb') as f:
        f.read(12)
        json_len = struct.unpack('<I', f.read(4))[0]
        f.read(4)
        data = json.loads(f.read(json_len))
        bin_len = struct.unpack('<I', f.read(4))[0]
        f.read(4)
        return data, f.read(bin_len)


def _image_bytes(data: dict, blob: bytes, index: int) -> bytes:
    view = data['bufferViews'][data['images'][index]['bufferView']]
    start = view.get('byteOffset', 0)
    return blob[start:start + view['byteLength']]


def read_normal_maps(path: Path) -> dict:
    """{material name: Texture of the normal map}."""
    data, blob = glb_chunks(path)
    out = {}
    for mat in data.get('materials', []):
        ref = mat.get('normalTexture')
        if not ref:
            continue
        image = PNMImage()
        if not image.read(StringStream(_image_bytes(data, blob, data['textures'][ref['index']]['source']))):
            continue
        if image.get_x_size() > MAX_SIZE or image.get_y_size() > MAX_SIZE:
            small = PNMImage(min(image.get_x_size(), MAX_SIZE), min(image.get_y_size(), MAX_SIZE), 3)
            small.quick_filter_from(image)
            image = small
        tex = Texture(f'{mat["name"]}_normal')
        tex.load(image)
        tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        tex.set_magfilter(SamplerState.FT_linear)
        tex.set_anisotropic_degree(4)
        out[mat['name']] = tex
    return out
