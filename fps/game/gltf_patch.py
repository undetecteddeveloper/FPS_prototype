"""Patches panda3d-gltf 1.3.0 so that the M4 file (Sketchfab, units in cm, skinned skeleton) can be loaded.

Call `apply()` once, BEFORE creating Ursina()/ShowBase and before loading any glb.
Six bugs, one function each below (1.3.0 only; after changing the version, re-run tests/test_gltf_load.py):

1. get_buffer_from_accessor: slices `memoryview[start:end:stride]` by BYTE, so it raises BufferError
   when loading animation (the file has a byteStride equal to the element size).
2. load_material: ignores the `diffuseTexture` of KHR_materials_pbrSpecularGlossiness, so every mesh
   keeps only the normal map (flat blue colour). Switch to baseColor and drop the normal map (Panda's
   fixed-function path cannot use it).
3. build_animation_skeleton: a joint missing an animation channel (e.g. Spine_02) is placed at the
   bind pose (at the origin). glTF standard: stand at the node's TRS. Without this patch the whole arm falls to the floor.
4. update: the file has a 0.01 scale matrix on the skeleton's ANCESTOR nodes; the library multiplies
   the skinned mesh vertices by its inverse, then Actor discards those nodes, so the hands are 100x the size of the bones.
5. build_character_joints: auxiliary joints (like `Main`) still create an extra scene node carrying the
   same offset, and the node updated by the joint sits inside it, so the offset is applied twice and the gun body flies off elsewhere.
6. Turns off Panda's on-disk model cache (so a fixed patch is not masked by old cached data) and turns off
   sRGB for textures (Ursina does not enable framebuffer-srgb, so the gun would be pitch black).
"""
import inspect
import struct
import textwrap

import panda3d.core as p3d
from gltf import _converter
from gltf._converter_maps import COMPONENT_FORMT_STR_MAP, COMPONENT_NUM_MAP, COMPONENT_SIZE_MAP

_applied = False


def _get_buffer_from_accessor(self, gltf_data, accid, unpack=True):
    acc = gltf_data['accessors'][accid]
    view = gltf_data['bufferViews'][acc['bufferView']]
    buff = memoryview(self.buffers[view['buffer']])

    element_size = COMPONENT_SIZE_MAP[acc['componentType']] * COMPONENT_NUM_MAP[acc['type']]
    stride = view.get('byteStride') or element_size
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    count = acc['count']

    if stride == element_size:
        buffdata = buff[start:start + count * element_size]
    else:
        buffdata = b''.join(
            bytes(buff[start + i * stride:start + i * stride + element_size]) for i in range(count)
        )

    if not unpack:
        return buffdata

    formatstr = COMPONENT_FORMT_STR_MAP[acc['componentType']] * COMPONENT_NUM_MAP[acc['type']]
    acctype = acc['type']
    if acctype == 'SCALAR':
        convertfn = lambda x: x[0]
    elif acctype == 'VEC2':
        convertfn = lambda x: p3d.LVector2(*x)
    elif acctype == 'VEC3':
        convertfn = lambda x: p3d.LVector3(*x)
    elif acctype == 'VEC4':
        convertfn = lambda x: p3d.LVector4(*x)
    else:
        convertfn = lambda x: x
    return list(map(convertfn, struct.iter_unpack(f'<{formatstr}', buffdata)))


_original_load_material = _converter.Converter.load_material


def _load_material(self, matid, gltf_mat):
    """KHR_materials_pbrSpecularGlossiness -> pbrMetallicRoughness (colour only), normal map dropped.

    Library 1.3.0 ignores the `diffuseTexture` of the spec-gloss standard, so the mesh keeps only the
    normal map and renders as one flat blue colour. Panda's fixed-function path cannot use normal maps either.
    """
    sg = gltf_mat.get('extensions', {}).get('KHR_materials_pbrSpecularGlossiness')
    if sg is not None:
        gltf_mat = dict(gltf_mat)
        pbr = {
            'baseColorFactor': sg.get('diffuseFactor', [1.0, 1.0, 1.0, 1.0]),
            'metallicFactor': 0.0,
            'roughnessFactor': 1.0 - sg.get('glossinessFactor', 1.0),
        }
        if 'diffuseTexture' in sg:
            pbr['baseColorTexture'] = sg['diffuseTexture']
        gltf_mat['pbrMetallicRoughness'] = pbr
        gltf_mat.pop('normalTexture', None)
    return _original_load_material(self, matid, gltf_mat)


_OLD_DEFAULTS = """        translation = LVector3()
        rotation_vec = LVector3()
        scale = LVector3()
        decompose_matrix(self.csxform * joint_mat * self.csxform_inv, scale, rotation_vec, translation, CS_yup_right)
        rotation = LQuaternion()
        rotation.set_hpr(rotation_vec, CS_yup_right)
"""

_NEW_DEFAULTS = """        if 'matrix' in bone:
            translation = LVector3()
            rotation_vec = LVector3()
            scale = LVector3()
            decompose_matrix(self.csxform * joint_mat * self.csxform_inv, scale, rotation_vec, translation, CS_yup_right)
            rotation = LQuaternion()
            rotation.set_hpr(rotation_vec, CS_yup_right)
        else:
            translation = LVector3(*bone.get('translation', (0.0, 0.0, 0.0)))
            scale = LVector3(*bone.get('scale', (1.0, 1.0, 1.0)))
            _rx, _ry, _rz, _rw = bone.get('rotation', (0.0, 0.0, 0.0, 1.0))
            rotation = LQuaternion(_rw, _rx, _ry, _rz)
"""


def _make_build_animation_skeleton():
    """A joint missing an animation channel must stand at the glTF node's rest pose, not at the bind pose.

    The library takes its defaults from the bind pose (IBM), so a static joint like `Spine_02` is placed
    at the origin and the whole arm hanging below it falls to the floor. glTF standard: the current pose
    of a joint with no channel = the node's TRS; IBM is only used to know the skin's rest pose.
    """
    src = textwrap.dedent(inspect.getsource(_converter.Converter.build_animation_skeleton))
    old = textwrap.indent(textwrap.dedent(_OLD_DEFAULTS), '    ')
    new = textwrap.indent(textwrap.dedent(_NEW_DEFAULTS), '    ')
    patched = src.replace(old, new)
    if patched == src:
        raise RuntimeError('gltf_patch: không tìm thấy đoạn mặc định animation, panda3d-gltf đã đổi phiên bản?')
    namespace = _converter.__dict__
    exec(compile(patched, '<gltf_patch.build_animation_skeleton>', 'exec'), namespace)
    return namespace.pop('build_animation_skeleton')


_original_update = _converter.Converter.update


def _update(self, gltf_data):
    """Remove the transforms of the skeleton's ANCESTOR nodes (the M4 file has a 0.01 scale matrix at the root).

    The library multiplies the vertices of the skinned mesh by the inverse of that scale (vertices 100x too large), then
    `Actor` keeps only the skeleton branch and drops the root nodes, so the hands end up 100x the size of the bones.
    After the patch the whole model is in cm; the game code applies the 0.01 scale to get metres.
    """
    nodes = gltf_data.get('nodes', [])
    parent = {c: i for i, n in enumerate(nodes) for c in n.get('children', [])}
    for skin in gltf_data.get('skins', []):
        start = skin.get('skeleton', skin['joints'][0])
        node = parent.get(start)
        while node is not None:
            for key in ('matrix', 'translation', 'rotation', 'scale'):
                nodes[node].pop(key, None)
            node = parent.get(node)
    return _original_update(self, gltf_data)


_original_build_character_joints = _converter.Converter.build_character_joints


def _build_character_joints(self, char, root_nodeids, affected_nodeids, skinid, gltf_data):
    """When every node has become a joint, do not add a duplicate scene node.

    The library drops the scene node only for joints inside the skin. Auxiliary joints like `Main` (the parent
    of the gun mesh) still create an extra scene node carrying the same offset, and the node updated by the
    joint sits INSIDE it, so the offset is applied twice: the gun body flies off elsewhere.
    """
    jvtmap = _original_build_character_joints(self, char, root_nodeids, affected_nodeids, skinid, gltf_data)
    self._joint_nodes.update(affected_nodeids)
    return jvtmap


def apply():
    global _applied
    if not _applied:
        # Panda caches the converted model on disk, so after editing this patch the old cache would still be reused.
        p3d.loadPrcFileData('', 'model-cache-dir\nmodel-cache-models 0\nmodel-cache-textures 0')
        # Ursina does not enable framebuffer-srgb: a texture marked sRGB would be darkened (gun pitch black).
        p3d.loadPrcFileData('', 'gltf-no-srgb true')
        _converter.Converter.get_buffer_from_accessor = _get_buffer_from_accessor
        _converter.Converter.update = _update
        _converter.Converter.build_character_joints = _build_character_joints
        _converter.Converter.load_material = _load_material
        _converter.Converter.build_animation_skeleton = _make_build_animation_skeleton()
        _applied = True
