"""Vá panda3d-gltf 1.3.0 để nạp được file M4 (Sketchfab, đơn vị cm, bộ xương có skin).

Gọi `apply()` một lần, TRƯỚC khi tạo Ursina()/ShowBase và trước khi nạp bất kỳ glb nào.
Sáu lỗi, mỗi lỗi một hàm bên dưới (chỉ bản 1.3.0; đổi phiên bản thì chạy lại tests/test_gltf_load.py):

1. get_buffer_from_accessor: cắt `memoryview[start:end:stride]` theo BYTE nên ném BufferError
   khi nạp animation (file có byteStride bằng đúng kích thước phần tử).
2. load_material: bỏ qua `diffuseTexture` của KHR_materials_pbrSpecularGlossiness nên mọi mesh
   chỉ còn normal map (màu xanh phẳng). Đổi sang baseColor, bỏ normal map (đường vẽ cố định
   của Panda không dùng được nó).
3. build_animation_skeleton: khớp thiếu kênh animation (vd. Spine_02) bị đặt theo tư thế bind
   (ở gốc toạ độ). Chuẩn glTF: đứng ở TRS của nút. Cả cánh tay rơi xuống sàn nếu không vá.
4. update: file có ma trận tỷ lệ 0,01 ở các nút TỔ TIÊN bộ xương; thư viện nhân đỉnh mesh có skin
   với nghịch đảo của nó rồi Actor vứt các nút đó đi, nên tay to gấp 100 lần xương.
5. build_character_joints: khớp phụ (như `Main`) vẫn sinh thêm nút cảnh mang cùng độ lệch,
   nút cập nhật theo khớp nằm bên trong nó, độ lệch bị cộng hai lần, thân súng bay đi chỗ khác.
6. Tắt cache model trên đĩa của Panda (sửa bản vá mà cache cũ vẫn được dùng lại) và tắt sRGB
   cho texture (Ursina không bật framebuffer-srgb nên súng đen kịt).
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
    """KHR_materials_pbrSpecularGlossiness -> pbrMetallicRoughness (chỉ lấy màu), bỏ normal map.

    Thư viện 1.3.0 bỏ qua `diffuseTexture` của chuẩn spec-gloss nên mesh chỉ còn normal map,
    vẽ ra một màu xanh phẳng. Đường vẽ cố định của Panda cũng không dùng được normal map.
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
    """Khớp thiếu kênh animation phải đứng ở tư thế nghỉ của nút glTF, không phải tư thế bind.

    Thư viện lấy giá trị mặc định từ tư thế bind (IBM), nên khớp tĩnh như `Spine_02` bị đặt ở gốc
    toạ độ và cả cánh tay treo dưới nó rơi xuống sàn. Chuẩn glTF: tư thế hiện tại của khớp không có
    kênh = TRS của nút; IBM chỉ dùng để biết tư thế gốc của da.
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
    """Xoá phép biến đổi của các nút TỔ TIÊN của bộ xương (file M4 có ma trận tỷ lệ 0,01 ở gốc).

    Thư viện nhân đỉnh của mesh có skin với nghịch đảo tỷ lệ đó (đỉnh lớn gấp 100 lần), rồi
    `Actor` chỉ giữ nhánh bộ xương và bỏ các nút gốc, nên tay to gấp 100 lần so với xương.
    Sau bản vá, cả mô hình ở đơn vị cm; code game tự scale 0,01 để ra mét.
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
    """Mọi nút đã thành khớp thì không được thêm một nút cảnh trùng lặp.

    Thư viện chỉ bỏ nút cảnh cho khớp nằm trong skin. Khớp phụ như `Main` (cha của mesh súng) vẫn
    sinh thêm nút cảnh mang cùng độ lệch, và nút cập nhật theo khớp lại nằm BÊN TRONG nó, nên độ
    lệch bị cộng hai lần: thân súng bay đi chỗ khác.
    """
    jvtmap = _original_build_character_joints(self, char, root_nodeids, affected_nodeids, skinid, gltf_data)
    self._joint_nodes.update(affected_nodeids)
    return jvtmap


def apply():
    global _applied
    if not _applied:
        # Panda cache model đã chuyển đổi trên đĩa, nên sửa bản vá mà cache cũ vẫn được dùng lại.
        p3d.loadPrcFileData('', 'model-cache-dir\nmodel-cache-models 0\nmodel-cache-textures 0')
        # Ursina không bật framebuffer-srgb: texture đánh dấu sRGB sẽ bị tối đi (súng đen kịt).
        p3d.loadPrcFileData('', 'gltf-no-srgb true')
        _converter.Converter.get_buffer_from_accessor = _get_buffer_from_accessor
        _converter.Converter.update = _update
        _converter.Converter.build_character_joints = _build_character_joints
        _converter.Converter.load_material = _load_material
        _converter.Converter.build_animation_skeleton = _make_build_animation_skeleton()
        _applied = True
