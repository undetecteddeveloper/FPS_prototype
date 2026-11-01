"""Bộ thông số chỉnh được (toán thuần, không import ursina): sinh thanh trượt từ các dataclass của weapon_data, lưu / nạp JSON.

`ParamStore` giữ một `GameParams` SỐNG: mọi module của game đều giữ cùng các đối tượng dataclass đó và đọc số mỗi lần dùng, nên đổi một
số ở đây là game chạy theo số mới ngay (trừ vài trường chép lúc dựng, được đánh dấu `restart` hoặc không đưa lên bảng, xem param_meta.py).

- Thanh trượt sinh bằng introspection: kiểu (số thực / nguyên / bật-tắt / tuple số / chọn một), mặc định lấy thẳng từ dataclass;
  chú thích, khoảng kéo, nhóm lấy từ `param_meta.py` (thiếu khoảng thì tự suy 0 .. 3 lần mặc định).
- Mặc định chụp NGAY khi tạo store (trước khi nạp file người dùng), nên "đặt lại" luôn về số trong weapon_data.
- Lưu: chỉ ghi các số KHÁC mặc định (`{"version": 1, "values": {"gun.rpm": 800, ...}}`), nên đổi mặc định trong mã sau này vẫn có tác dụng
  với số chưa từng chỉnh. Nạp: đưa mọi thứ về mặc định rồi áp file (khoá thiếu = mặc định, khoá lạ / sai kiểu = bỏ qua và báo, không lỗi).
"""
import dataclasses
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fps.core import param_meta
from fps.weapon_data import GameParams

FILE_VERSION = 1


@dataclass(frozen=True)
class ParamSpec:
    id: str                    # 'gun.accuracy.stand' hoặc 'gun.kick.peak[3]' (thành phần của tuple)
    path: str                  # đối tượng chứa trường: 'gun.accuracy'
    attr: str                  # tên trường: 'stand'
    index: int                 # thành phần trong tuple, hoặc None
    group: str
    section: str
    label: str
    hint: str
    kind: str                  # 'float' | 'int' | 'bool' | 'choice'
    lo: float
    hi: float
    step: float
    default: object
    advanced: bool
    restart: bool
    choices: tuple = None      # ((giá trị, chữ), ...) khi kind == 'choice'

    @property
    def decimals(self) -> int:
        return decimals_for(self.step)


@dataclass
class GroupInfo:
    key: str
    title: str
    specs: list = field(default_factory=list)

    def sections(self, show_advanced: bool = True) -> list:
        """[(tiêu đề mục, [spec, ...])] theo thứ tự; mục rỗng (sau khi ẩn nâng cao) thì bỏ."""
        out = []
        for spec in self.specs:
            if spec.advanced and not show_advanced:
                continue
            if not out or out[-1][0] != spec.section:
                out.append((spec.section, []))
            out[-1][1].append(spec)
        return out


@dataclass
class LoadReport:
    ok: bool = True
    applied: int = 0
    ignored: list = field(default_factory=list)       # [(khoá, lý do)]
    message: str = ''


# --- định dạng ---
def decimals_for(step: float) -> int:
    if step is None or step <= 0:
        return 2
    return min(4, max(0, math.ceil(-math.log10(step) - 1e-9)))


def format_number(value: float, decimals: int) -> str:
    """Số kiểu Việt (dấu phẩy thập phân)."""
    return f'{value:.{decimals}f}'.replace('.', ',')


def format_value(spec: ParamSpec, value) -> str:
    if spec.kind == 'bool':
        return 'Bật' if value else 'Tắt'
    if spec.kind == 'choice':
        return dict((_ckey(c), t) for c, t in spec.choices).get(_ckey(value), str(value))
    if spec.kind == 'int':
        return str(int(value))
    return format_number(float(value), spec.decimals)


def _ckey(v):
    """Khoá so sánh cho giá trị của trường chọn: True / 1 / 'fake' phải khác nhau."""
    return (type(v).__name__, v)


def nice_step(lo: float, hi: float) -> float:
    """Bước kéo 1 / 2 / 5 x 10^k, khoảng 1/100 độ dài thanh."""
    span = hi - lo
    if span <= 0:
        return 0.01
    raw = span / 100.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag * 1.0001:
            return m * mag
    return 10 * mag


def auto_range(default, kind: str) -> tuple:
    """Khoảng kéo khi param_meta không nói: từ 0 tới 3 lần mặc định (mặc định âm thì từ 3 lần mặc định tới 0; bằng 0 thì -1..1)."""
    d = float(default)
    if d > 0:
        lo, hi = 0.0, 3.0 * d
    elif d < 0:
        lo, hi = 3.0 * d, 0.0
    else:
        lo, hi = -1.0, 1.0
    if kind == 'int':
        hi = max(hi, 1.0)
    return lo, hi


# --- đường dẫn / kiểu ---
def resolve(root, path: str):
    obj = root
    for name in path.split('.'):
        obj = getattr(obj, name)
    return obj


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _kind_of(value, meta) -> str:
    if meta is not None and meta.choices is not None:
        return 'choice'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    raise TypeError(f'không đưa được lên bảng: {value!r}')


def _make_spec(root, group: str, section: str, path: str, attr: str, index, meta) -> ParamSpec:
    obj = resolve(root, path)
    value = getattr(obj, attr)
    if index is not None:
        value = value[index]
    kind = _kind_of(value, meta)
    if kind in ('bool', 'choice'):
        lo = hi = step = 0.0
    else:
        lo, hi = (meta.lo, meta.hi) if meta.lo is not None and meta.hi is not None else auto_range(value, kind)
        step = meta.step if meta.step else (1.0 if kind == 'int' else nice_step(lo, hi))
    sid = f'{path}.{attr}' + (f'[{index}]' if index is not None else '')
    return ParamSpec(id=sid, path=path, attr=attr, index=index, group=group, section=section, label=meta.label, hint=meta.hint,
                     kind=kind, lo=lo, hi=hi, step=step, default=value, advanced=meta.advanced, restart=meta.restart,
                     choices=meta.choices)


def build_specs(root: GameParams) -> list:
    """Mọi thanh trượt theo thứ tự nhóm / mục. Lỗi (id không có trong bảng meta, kiểu lạ) báo ngay, không im lặng bỏ."""
    specs = []
    for gkey, _title, sections in param_meta.GROUPS:
        for stitle, field_ids in sections:
            for fid in field_ids:
                path, attr = fid.rsplit('.', 1)
                meta = param_meta.META[fid]
                value = getattr(resolve(root, path), attr)
                if isinstance(meta, tuple):                       # tuple số: mỗi thành phần một thanh
                    if not isinstance(value, tuple) or len(value) != len(meta):
                        raise TypeError(f'{fid}: {len(meta)} thanh nhưng giá trị là {value!r}')
                    for i, m in enumerate(meta):
                        specs.append(_make_spec(root, gkey, stitle, path, attr, i, m))
                else:
                    specs.append(_make_spec(root, gkey, stitle, path, attr, None, meta))
    return specs


def all_field_ids(root: GameParams) -> set:
    """Mọi trường của GameParams ('gun.accuracy.stand', ...), đi sâu vào dataclass lồng nhau; dùng để kiểm bảng không sót trường."""
    out = set()

    def walk(obj, prefix):
        for f in dataclasses.fields(obj):
            v = getattr(obj, f.name)
            if dataclasses.is_dataclass(v):
                walk(v, f'{prefix}{f.name}.')
            else:
                out.add(f'{prefix}{f.name}')
    walk(root, '')
    return out


class ParamStore:
    def __init__(self, params: GameParams):
        self.root = params
        self.specs = build_specs(params)
        self.by_id = {s.id: s for s in self.specs}
        self.groups = []
        for gkey, title, _ in param_meta.GROUPS:
            self.groups.append(GroupInfo(gkey, title, [s for s in self.specs if s.group == gkey]))
        self.group_by_key = {g.key: g for g in self.groups}
        self.defaults = {s.id: s.default for s in self.specs}
        self._listeners = []

    # --- người nghe: gọi MỘT lần cho mỗi lần đổi (cả lô khi nạp / đặt lại), với danh sách spec đã đổi ---
    def subscribe(self, fn):
        self._listeners.append(fn)

    def _notify(self, changed: list):
        if changed:
            for fn in self._listeners:
                fn(changed)

    # --- đọc / ghi ---
    def get(self, spec: ParamSpec):
        v = getattr(resolve(self.root, spec.path), spec.attr)
        return v[spec.index] if spec.index is not None else v

    def _write(self, spec: ParamSpec, value):
        obj = resolve(self.root, spec.path)
        if spec.index is None:
            setattr(obj, spec.attr, value)
        else:
            items = list(getattr(obj, spec.attr))
            items[spec.index] = value
            setattr(obj, spec.attr, type(getattr(obj, spec.attr))(items))

    def coerce(self, spec: ParamSpec, raw):
        """Đưa giá trị thô (từ giao diện hoặc JSON) về đúng kiểu và kẹp vào khoảng; ném ValueError nếu sai kiểu / không hữu hạn."""
        if spec.kind == 'bool':
            if not isinstance(raw, bool):
                raise ValueError('cần true / false')
            return raw
        if spec.kind == 'choice':
            for c, _ in spec.choices:
                if _ckey(c) == _ckey(raw):
                    return c
            raise ValueError('không phải một lựa chọn hợp lệ')
        if not is_number(raw) or not math.isfinite(raw):
            raise ValueError('cần một số hữu hạn')
        if spec.kind == 'int':
            if float(raw) != int(raw):
                raise ValueError('cần số nguyên')
            return int(min(max(int(raw), int(spec.lo)), int(spec.hi)))
        return float(min(max(float(raw), spec.lo), spec.hi))

    def set(self, spec: ParamSpec, raw) -> bool:
        """Đặt giá trị; trả về True nếu có đổi. Sai kiểu thì ném ValueError."""
        value = self.coerce(spec, raw)
        if self.get(spec) == value and type(self.get(spec)) is type(value):
            return False
        self._write(spec, value)
        self._notify([spec])
        return True

    def is_default(self, spec: ParamSpec) -> bool:
        v = self.get(spec)
        return v == spec.default and type(v) is type(spec.default)

    def reset(self, spec: ParamSpec) -> bool:
        return self.reset_many([spec]) > 0

    def reset_many(self, specs) -> int:
        changed = []
        for s in specs:
            if not self.is_default(s):
                self._write(s, s.default)
                changed.append(s)
        self._notify(changed)
        return len(changed)

    def reset_group(self, key: str) -> int:
        return self.reset_many(self.group_by_key[key].specs)

    def reset_all(self) -> int:
        return self.reset_many(self.specs)

    def changed_specs(self, group: str = None) -> list:
        return [s for s in self.specs if (group is None or s.group == group) and not self.is_default(s)]

    # --- lưu / nạp ---
    def to_dict(self) -> dict:
        return {'version': FILE_VERSION, 'values': {s.id: self.get(s) for s in self.changed_specs()}}

    def apply_dict(self, data) -> LoadReport:
        """Đưa mọi thứ về mặc định rồi áp `data`. Dữ liệu không đúng dạng thì không đổi gì (ok=False)."""
        if not isinstance(data, dict) or not isinstance(data.get('values'), dict):
            return LoadReport(False, message='file không đúng dạng (thiếu "values")')
        report = LoadReport()
        valid = []
        for key, raw in data['values'].items():
            spec = self.by_id.get(key)
            if spec is None:
                report.ignored.append((str(key), 'khoá lạ'))
                continue
            try:
                valid.append((spec, self.coerce(spec, raw)))
            except ValueError as e:
                report.ignored.append((key, f'sai kiểu: {e}'))
        before = {s.id: self.get(s) for s in self.specs}
        for s in self.specs:
            self._write(s, s.default)
        for spec, value in valid:
            self._write(spec, value)
        report.applied = len(valid)
        self._notify([s for s in self.specs if self.get(s) != before[s.id] or type(self.get(s)) is not type(before[s.id])])
        extra = f', bỏ qua {len(report.ignored)} mục không dùng được' if report.ignored else ''
        report.message = f'đã nạp {report.applied} giá trị{extra}'
        return report

    def save(self, path) -> LoadReport:
        path = Path(path)
        data = self.to_dict()
        try:
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            return LoadReport(False, message=f'không ghi được {path.name}: {e}')
        n = len(data['values'])
        return LoadReport(True, applied=n, message=f'đã lưu {n} giá trị khác mặc định vào {path.name}')

    def load(self, path) -> LoadReport:
        path = Path(path)
        try:
            text = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return LoadReport(False, message=f'chưa có file {path.name} (bấm Lưu trước)')
        except (OSError, UnicodeDecodeError) as e:
            return LoadReport(False, message=f'không đọc được {path.name}: {e}')
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return LoadReport(False, message=f'{path.name} bị hỏng ({e.msg}), giữ nguyên thông số hiện tại')
        report = self.apply_dict(data)
        if not report.ok:
            report.message = f'{path.name}: {report.message}, giữ nguyên thông số hiện tại'
        return report
