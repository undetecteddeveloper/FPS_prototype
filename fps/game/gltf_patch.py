"""Patches panda3d-gltf 1.3.0 so that the M4 and Glock 17 files (Sketchfab / Fab, units in cm, skinned skeleton) can be loaded.

Call `apply()` once, BEFORE creating Ursina()/ShowBase and before loading any glb.
Eight bugs, one function each below (1.3.0 only; after changing the version, re-run tests/test_gltf_load.py):

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
8. A skeleton whose animated nodes are not all under the skin's own root (Glock 17: gun parts + camera sit beside the arm bones): the Character is rooted at the
   lowest common ancestor of the skin and every animated node (`_skeleton_root`, written into `skin['skeleton']`), so they become joints and actually move.
7. Several skins (Glock 17: one for the hand mesh, one for the glove mesh) that share ONE skeleton: the library keeps one Character per skeleton root, so the second skin
   overwrites the first and the load dies with `KeyError: 0`. Fix: the first skin builds the Character; the other skins get a copy of its CharInfo with the joint-index
   table translated to the first skin's indices (a joint the first skin lacks uses its nearest ancestor that it has).
6. Turns off Panda's on-disk model cache (so a fixed patch is not masked by old cached data) and turns off
   sRGB for textures (Ursina does not enable framebuffer-srgb, so the gun would be pitch black).
"""
import copy
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


def _skeleton_root(gltf_data, skin, parent) -> int:
    """Node the skeleton of `skin` hangs from. Normally the skin's own first joint; but when animation channels move nodes OUTSIDE that joint's subtree (the Glock 17 file:
    the gun parts and the camera are siblings of the arm bones, under `Glock17_Root_01`), the lowest common ancestor of the joint and every animated node, so those nodes become joints
    of the Character too (otherwise the library leaves them still: the slide would never move)."""
    start = skin.get('skeleton', skin['joints'][0])

    def chain(node):
        out = [node]
        while parent.get(out[-1]) is not None:
            out.append(parent[out[-1]])
        return out[::-1]                                   # root ... node

    paths = [chain(start)] + [chain(ch['target']['node']) for anim in gltf_data.get('animations', []) for ch in anim['channels'] if 'node' in ch['target']]
    common = paths[0]
    for path in paths[1:]:
        k = 0
        while k < min(len(common), len(path)) and common[k] == path[k]:
            k += 1
        common = common[:k]
    return common[-1] if common else start


def _update(self, gltf_data):
    """Remove the transforms of the skeleton's ANCESTOR nodes (the M4 file has a 0.01 scale matrix at the root).

    The library multiplies the vertices of the skinned mesh by the inverse of that scale (vertices 100x too large), then
    `Actor` keeps only the skeleton branch and drops the root nodes, so the hands end up 100x the size of the bones.
    After the patch the whole model is in cm; the game code applies the 0.01 scale to get metres.
    """
    nodes = gltf_data.get('nodes', [])
    parent = {c: i for i, n in enumerate(nodes) for c in n.get('children', [])}
    for skin in gltf_data.get('skins', []):
        start = _skeleton_root(gltf_data, skin, parent)
        skin['skeleton'] = start                         # the library roots the joints AND the animation tree at this node
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


_original_init = _converter.Converter.__init__
_original_load_skin = _converter.Converter.load_skin


class _SkinAliasDict(dict):
    """`Converter.characters` with a fallback: a skin that shares its skeleton with an earlier skin gets that skin's character, joint indices translated."""

    def __init__(self, converter):
        super().__init__()
        self.converter = converter

    def __missing__(self, skinid):
        conv = self.converter
        canonical = conv._skin_alias.get(skinid)
        if canonical is None or canonical not in self:
            raise KeyError(skinid)
        base = self[canonical]
        alias = copy.copy(base)
        mine, theirs = conv._skin_joints[skinid], conv._skin_joints[canonical]
        parent = conv._node_parent
        jvtmap = {}
        for i, node in enumerate(mine):
            while node is not None and node not in theirs:      # a joint only this skin has (a fingertip): weights go to its nearest ancestor that the first skin has
                node = parent.get(node)
            if node is not None and theirs.index(node) in base.jvtmap:
                jvtmap[i] = base.jvtmap[theirs.index(node)]
        alias.jvtmap = jvtmap
        self[skinid] = alias
        return alias


def _init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self._skin_alias = {}              # skin id -> id of the skin that owns the shared skeleton
    self._skin_joints = {}             # skin id -> its joint node ids
    self._node_parent = {}             # node id -> parent node id
    self.characters = _SkinAliasDict(self)


def _load_skin(self, skinid, gltf_skin, gltf_data):
    """Keep the FIRST skin of a shared skeleton root as the owner; later skins become aliases of it."""
    if not self._node_parent:
        self._node_parent = {c: i for i, n in enumerate(gltf_data['nodes']) for c in n.get('children', [])}
    before = dict(self.skeletons)
    _original_load_skin(self, skinid, gltf_skin, gltf_data)
    self._skin_joints[skinid] = list(gltf_skin['joints'])
    root = next(node for node, sid in self.skeletons.items() if sid == skinid)
    if root in before:
        self.skeletons[root] = before[root]
        self._skin_alias[skinid] = before[root]


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
        _converter.Converter.__init__ = _init
        _converter.Converter.load_skin = _load_skin
        _converter.Converter.load_material = _load_material
        _converter.Converter.build_animation_skeleton = _make_build_animation_skeleton()
        _applied = True
