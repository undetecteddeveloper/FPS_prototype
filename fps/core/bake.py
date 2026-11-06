"""Chốt số từ bảng F1 vào mã: sửa ĐÚNG ký tự của giá trị mặc định trong weapon_data.py (toán thuần chữ, không import ursina).

Mỗi số mặc định nằm ở một trong hai nơi: dòng `tên: kiểu = giá_trị` trong thân dataclass, hoặc tham số từ khoá của lời gọi
`M4 = GunData(tên=giá_trị)` (ưu tiên nơi này nếu có). Dùng `ast` để lấy vị trí chính xác của giá trị rồi thay đúng đoạn đó:
chú thích, thụt lề, kiểu xuống dòng (CRLF / LF) của file được giữ nguyên. Giá trị mặc định mà KHÔNG phải số viết thẳng
(hàm, hằng số khác...) thì không sửa tự động, trả về lý do trong `failures` để người dùng sửa tay.
"""
import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    owner: str                 # tên lớp có dòng `attr: kiểu = giá_trị` (vd 'GunKickData')
    attr: str
    value: object              # giá trị MỚI trọn vẹn (số, bool, chuỗi, hoặc tuple đủ mọi thành phần)
    call: str = None           # biến gán bằng lời gọi lớp (vd 'M4'): nếu lời gọi có tham số `attr=` thì sửa ở đó
    forbid_kw: tuple = None    # (tên lời gọi, tên tham số): lời gọi ghi đè cả đối tượng chứa trường thì không sửa tự động


CALLS = {'gun': 'M4'}      # đối tượng trên bảng -> biến gán bằng lời gọi lớp trong weapon_data.py


def edits_for(root, specs, calls=CALLS) -> list:
    """Từ các spec (thanh trượt) đã đổi, dựng danh sách Edit; tuple nhiều thành phần chỉ sinh MỘT Edit với tuple đầy đủ."""
    from fps.core.params import resolve
    out, seen = [], set()
    for s in specs:
        if (s.path, s.attr) in seen:
            continue
        seen.add((s.path, s.attr))
        parts = s.path.split('.')
        out.append(Edit(owner=type(resolve(root, s.path)).__name__, attr=s.attr, value=getattr(resolve(root, s.path), s.attr),
                        call=calls.get(s.path),
                        forbid_kw=(calls[parts[0]], parts[1]) if len(parts) > 1 and parts[0] in calls else None))
    return out


def format_literal(v) -> str:
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(float(f'{v:.6g}'))
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, tuple):
        inner = ', '.join(format_literal(x) for x in v)
        return f'({inner},)' if len(v) == 1 else f'({inner})'
    raise TypeError(f'không viết được thành mã: {v!r}')


def _is_plain_literal(node) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float, bool, str))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_plain_literal(node.operand)
    if isinstance(node, ast.Tuple):
        return all(_is_plain_literal(e) for e in node.elts)
    return False


def _class_field(tree, owner: str, attr: str):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == owner:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id == attr:
                    return item.value
    return None


def _call_of(tree, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets) and isinstance(node.value, ast.Call):
            return node.value
    return None


def _locate(tree, edit: Edit):
    """(nút giá trị, None) hoặc (None, lý do)."""
    if edit.forbid_kw:
        call = _call_of(tree, edit.forbid_kw[0])
        if call is not None and any(k.arg == edit.forbid_kw[1] for k in call.keywords):
            return None, f'{edit.forbid_kw[0]} ghi đè cả {edit.forbid_kw[1]}=...'
    if edit.call:
        call = _call_of(tree, edit.call)
        if call is not None:
            for k in call.keywords:
                if k.arg == edit.attr:
                    return (k.value, None) if _is_plain_literal(k.value) else (None, f'{edit.call}({edit.attr}=...) không phải số viết thẳng')
    node = _class_field(tree, edit.owner, edit.attr)
    if node is None:
        return None, f'không thấy dòng `{edit.attr}: ... = ...` trong lớp {edit.owner}'
    if not _is_plain_literal(node):
        return None, f'mặc định của {edit.owner}.{edit.attr} không phải số viết thẳng (hàm / hằng số)'
    return node, None


def patch_source(text: str, edits) -> tuple:
    """Trả (mã mới, [(Edit, lý do)] cho các sửa không làm được). Các sửa làm được vẫn được áp."""
    tree = ast.parse(text)
    data = text.encode('utf-8')
    starts = [0]
    for line in data.split(b'\n')[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    todo, failures = [], []
    for e in edits:
        node, why = _locate(tree, e)
        if node is None:
            failures.append((e, why))
            continue
        begin = starts[node.lineno - 1] + node.col_offset
        end = starts[node.end_lineno - 1] + node.end_col_offset
        todo.append((begin, end, format_literal(e.value)))
    todo.sort(reverse=True)
    for (b1, _e1, _), (b2, e2, _) in zip(todo, todo[1:]):
        if e2 > b1:
            raise ValueError('hai sửa chồng lên nhau (cùng một giá trị bị sửa hai lần)')
    for begin, end, new in todo:
        data = data[:begin] + new.encode('utf-8') + data[end:]
    return data.decode('utf-8'), failures
