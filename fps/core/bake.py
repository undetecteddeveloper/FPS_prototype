"""Bake numbers from the F1 panel into the code: edits EXACTLY the characters of each default value in weapon_data.py (pure text logic, no ursina import).

Each default number lives in one of two places: the `name: type = value` line in the dataclass body, or a keyword argument of the call
`M4 = GunData(name=value)` (this place wins if present). It uses `ast` to get the exact position of the value, then replaces exactly that span:
comments, indentation and the file's line endings (CRLF / LF) are kept. A default value that is NOT a plain literal number
(a function, another constant...) is not edited automatically; the reason is returned in `failures` so the user can edit it by hand.
"""
import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    owner: str                 # name of the class that has the `attr: type = value` line (e.g. 'GunKickData')
    attr: str
    value: object              # the NEW complete value (number, bool, string, or a tuple with every component)
    call: str = None           # variable assigned from a class call (e.g. 'M4'): if that call has an `attr=` keyword, edit it there
    forbid_kw: tuple = None    # (call name, keyword name): if the call overrides the whole object holding the field, it is not edited automatically


CALLS = {'gun': 'M4'}      # object on the panel -> variable assigned from a class call in weapon_data.py


def edits_for(root, specs, calls=CALLS) -> list:
    """From the changed specs (sliders), build the Edit list; a multi-component tuple produces ONE Edit with the full tuple."""
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
    """(value node, None) or (None, reason)."""
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
    """Returns (new source, [(Edit, reason)] for the edits that could not be made). The edits that can be made are still applied."""
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
