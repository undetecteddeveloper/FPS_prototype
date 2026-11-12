r"""Builds the game's Benelli M1014 model assets/guns/benelli_m1014.glb from the original Sketchfab file assets/guns/fps_benelli_m4_animations.glb (66 MB, not in git).
Needs numpy + Pillow (build time only: the game never imports numpy).

Why the original cannot be loaded as it is (found 9/11/2026 with tools/build/prep_benelli_glb.py --report and a numpy re-implementation of glTF skinning):
  1. SCALE: the three gun meshes (`benelli_m4_*`: body, shell holder, loaded shell) are authored ~82x larger than the hands and the skeleton: the gun body is ~3 700 units long while the
     arms and the hand-held shell are ~25 and ~2.6 units. The hand-held shell mesh (2.59 long) and the same shell on the gun (210.8 long) fix the ratio at 0.01227; the hand-to-hand spacing of the
     rig (16.9 units) against the grip-to-forend distance of the gun (1 400 raw) says 0.0120. The gun vertices are multiplied by `--scale` (default 0.0122) so the gun, the hands and the animations agree.
     After it 1 unit is ~2.2-2.4 cm (a real M4 Super 90 is 1.0 m: the scaled body is ~45 units), see GunData.model_scale in weapon_data.py.
  2. TEXTURES: 4096 x 4096 PNGs (14 MB each, 100 MB of RAM once decoded). The game's shader only reads the base colour and the normal map (the metal / occlusion maps are never sampled),
     so base colour / normal maps are cut to `--max-size` (default 2048 for the gun body, 1024 for the rest) and the unused maps become 4 x 4 pixels.
  3. KHR_texture_transform: the gun materials carry a 180 degree rotation on every texture. The game's shader reads the raw UVs (no texture matrix), so the rotation is baked into the images
     (a 180 degree rotation of the image == u' = 1 - u, v' = 1 - v under the repeat wrap) and the extension is removed. Offsets / scales other than the identity are refused.
Everything else (skeleton, 8 animations, materials) is copied untouched. Run: .venv\Scripts\python.exe -X utf8 tools\build\prep_benelli_glb.py [--scale 0.0122] [--report]
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'assets' / 'guns' / 'fps_benelli_m4_animations.glb'
TARGET = ROOT / 'assets' / 'guns' / 'benelli_m1014.glb'
GUN_MESH_PREFIX = 'benelli_m4_'                  # the three meshes that are too large (the hands / hand-held shell meshes are not named like this)
GUN_MATERIAL_SIZE = {'TTI_Benelli_M4': 2048}     # materials whose base colour keeps more pixels (the body fills the frame when aiming)
DEFAULT_SIZE = 1024
UNUSED_SIZE = 4
COMPONENT = {5126: ('<f4', 4), 5123: ('<u2', 2), 5125: ('<u4', 4), 5121: ('u1', 1), 5120: ('i1', 1), 5122: ('<i2', 2)}
NUM = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(path: Path) -> tuple:
    with open(path, 'rb') as f:
        magic, version, _length = struct.unpack('<4sII', f.read(12))
        assert magic == b'glTF' and version == 2
        jlen, jtype = struct.unpack('<I4s', f.read(8))
        assert jtype == b'JSON'
        data = json.loads(f.read(jlen))
        blen, btype = struct.unpack('<I4s', f.read(8))
        assert btype == b'BIN\x00'
        return data, bytearray(f.read(blen))


def write_glb(path: Path, data: dict, blob: bytes):
    text = json.dumps(data, separators=(',', ':')).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    blob = bytes(blob) + b'\x00' * (-len(blob) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    with open(path, 'wb') as f:
        f.write(struct.pack('<4sII', b'glTF', 2, total))
        f.write(struct.pack('<I4s', len(text), b'JSON'))
        f.write(text)
        f.write(struct.pack('<I4s', len(blob), b'BIN\x00'))
        f.write(blob)


def texture_roles(data: dict) -> dict:
    """image index -> {'base' | 'normal' | 'unused': [(material, slot)]}. Base colour and normal map are the only maps the game's shader samples."""
    roles = {}
    for mat in data['materials']:
        slots = {'baseColor': mat.get('pbrMetallicRoughness', {}).get('baseColorTexture'), 'normal': mat.get('normalTexture'),
                 'metalRough': mat.get('pbrMetallicRoughness', {}).get('metallicRoughnessTexture'), 'occlusion': mat.get('occlusionTexture'), 'emissive': mat.get('emissiveTexture')}
        for slot, info in slots.items():
            if info is None:
                continue
            image = data['textures'][info['index']]['source']
            role = {'baseColor': 'base', 'normal': 'normal'}.get(slot, 'unused')
            roles.setdefault(image, {}).setdefault(role, []).append((mat['name'], slot))
    return roles


def bake_texture_transform(data: dict) -> int:
    """Remove KHR_texture_transform (rotation of exactly 180 degrees only); returns how many texture infos had one."""
    count = 0
    for mat in data['materials']:
        infos = [mat.get('normalTexture'), mat.get('occlusionTexture'), mat.get('emissiveTexture'), *(mat.get('pbrMetallicRoughness', {}).get(k) for k in ('baseColorTexture', 'metallicRoughnessTexture'))]
        for info in infos:
            ext = (info or {}).get('extensions', {}).pop('KHR_texture_transform', None)
            if ext is None:
                continue
            ok = abs(abs(ext.get('rotation', 0.0)) - np.pi) < 1e-4 and ext.get('offset', [0, 0]) == [0, 0] and ext.get('scale', [1, 1]) == [1, 1] and 'texCoord' not in ext
            assert ok, f'KHR_texture_transform other than a plain 180 degree rotation: {ext}'
            count += 1
            if not info['extensions']:
                del info['extensions']
    if 'extensionsUsed' in data and 'KHR_texture_transform' in data['extensionsUsed']:
        data['extensionsUsed'].remove('KHR_texture_transform')
        if not data['extensionsUsed']:
            del data['extensionsUsed']
    return count


def rotated_images(data: dict) -> set:
    """Images that were rotated by a KHR_texture_transform in ANY of their uses (called BEFORE bake_texture_transform)."""
    out = set()
    for mat in data['materials']:
        infos = [mat.get('normalTexture'), mat.get('occlusionTexture'), mat.get('emissiveTexture'), *(mat.get('pbrMetallicRoughness', {}).get(k) for k in ('baseColorTexture', 'metallicRoughnessTexture'))]
        for info in infos:
            if info and 'KHR_texture_transform' in info.get('extensions', {}):
                out.add(data['textures'][info['index']]['source'])
    return out


def accessor_view(data: dict, blob: bytearray, index: int) -> tuple:
    """(numpy view of an accessor that is stored with its natural stride, the accessor)."""
    acc = data['accessors'][index]
    view = data['bufferViews'][acc['bufferView']]
    dtype, size = COMPONENT[acc['componentType']]
    n = NUM[acc['type']]
    stride = view.get('byteStride', size * n)
    assert stride == size * n, 'interleaved accessor: not handled'
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    return np.frombuffer(blob, dtype=dtype, count=acc['count'] * n, offset=start).reshape(acc['count'], n), acc


def scale_gun_meshes(data: dict, blob: bytearray, scale: float) -> list:
    done = []
    for mesh in data['meshes']:
        if not mesh.get('name', '').startswith(GUN_MESH_PREFIX):
            continue
        for prim in mesh['primitives']:
            pos, acc = accessor_view(data, blob, prim['attributes']['POSITION'])
            pos *= scale                                                  # in place: `pos` is a writable view of the bytearray
            acc['min'] = [float(x) for x in pos.min(axis=0)]
            acc['max'] = [float(x) for x in pos.max(axis=0)]
            done.append((mesh['name'], acc['min'], acc['max']))
    return done


def reencode_image(raw: bytes, role: str, max_size: int, rotate: bool) -> bytes:
    img = Image.open(io.BytesIO(raw))
    img.load()
    if role == 'unused':
        small = Image.new('RGB', (UNUSED_SIZE, UNUSED_SIZE), (128, 128, 128))
    else:
        small = img.convert('RGB')
        if rotate:
            small = small.rotate(180)
        if max(small.size) > max_size:
            small = small.resize((max_size, max_size), Image.LANCZOS)
    out = io.BytesIO()
    small.save(out, format='PNG', optimize=True)
    return out.getvalue()


def rebuild(data: dict, blob: bytearray, replaced: dict) -> bytearray:
    """New binary chunk: every bufferView copied in order (4-byte aligned), the ones in `replaced` (index -> bytes) swapped. Offsets and the buffer length are updated."""
    out = bytearray()
    for i, view in enumerate(data['bufferViews']):
        start = view.get('byteOffset', 0)
        chunk = replaced.get(i, bytes(blob[start:start + view['byteLength']]))
        out += b'\x00' * (-len(out) % 4)
        view['byteOffset'] = len(out)
        view['byteLength'] = len(chunk)
        out += chunk
    data['buffers'][0]['byteLength'] = len(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--scale', type=float, default=0.0122, help='multiplier on the gun mesh vertices (see the module text)')
    ap.add_argument('--max-size', type=int, default=DEFAULT_SIZE)
    ap.add_argument('--source', default=str(SOURCE))
    ap.add_argument('--target', default=str(TARGET))
    ap.add_argument('--report', action='store_true', help='only print what would change')
    args = ap.parse_args(argv)
    data, blob = read_glb(Path(args.source))
    roles = texture_roles(data)
    rotated = rotated_images(data)
    replaced = {}
    print(f'{"image":>5s} {"role":8s} {"size":>11s} -> {"new":>11s} {"KB":>7s} {"rot180":>6s}  used by')
    for i, image in enumerate(data['images']):
        view = data['bufferViews'][image['bufferView']]
        raw = bytes(blob[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']])
        used = roles.get(i, {})
        role = 'base' if 'base' in used else 'normal' if 'normal' in used else 'unused'
        mats = [m for lst in used.values() for m, _slot in lst]
        limit = max((GUN_MATERIAL_SIZE.get(m, args.max_size) for m in mats), default=args.max_size) if role == 'base' else args.max_size
        new = reencode_image(raw, role, limit, i in rotated and role != 'unused')
        before = Image.open(io.BytesIO(raw)).size
        after = Image.open(io.BytesIO(new)).size
        print(f'{i:5d} {role:8s} {before[0]:5d}x{before[1]:<5d} -> {after[0]:5d}x{after[1]:<5d} {len(new) // 1024:7d} {"yes" if i in rotated and role != "unused" else "":>6s}  {sorted(set(mats))}')
        replaced[image['bufferView']] = new
    baked = bake_texture_transform(data)
    gun = scale_gun_meshes(data, blob, args.scale)
    for name, lo, hi in gun:
        print(f'gun mesh {name[:44]:44s} x{args.scale}: min {[round(v, 2) for v in lo]} max {[round(v, 2) for v in hi]}')
    print(f'texture transforms baked into the images: {baked}')
    if args.report:
        return 0
    out = rebuild(data, blob, replaced)
    data['asset'] = {**data.get('asset', {}), 'copyright': 'Derived from "FPS Benelli M4 Animations" by Cransh (CC BY 4.0) with tools/build/prep_benelli_glb.py: gun meshes x%g, textures downscaled, KHR_texture_transform baked' % args.scale}
    Path(args.target).parent.mkdir(parents=True, exist_ok=True)
    write_glb(Path(args.target), data, out)
    print(f'wrote {args.target}: {Path(args.target).stat().st_size / 1e6:.1f} MB (source {Path(args.source).stat().st_size / 1e6:.1f} MB)')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
