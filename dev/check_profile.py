#!/usr/bin/env python3
# 設定ファイル (JSON) と点検表 (.xlsx / .xlsm) を突き合わせて、アプリが組み立てるカードの一覧と警告を出す確認用スクリプト。
# Python の標準ライブラリだけで動く (openpyxl なども不要)。Claude Code のほか、ChatGPT・Copilot などの Python の実行環境でも使える。
#
# 使い方:
#   python check_profile.py <設定.json> <点検表.xlsm> [--sheet シート名] [--col 列名] [--json]
#     --sheet  見出しが合うシートが複数あるときに選ぶシート (省略時は候補の 1 つ目)
#     --col    書き込む列 (省略時はアプリと同じく「新しい記録」の列)
#     --json   結果を JSON で出す
#
# アプリの app/profile.js (buildProfileCards) と同じ規則で組み立てる。profile.js の規則を変えたら、このファイルも合わせて直す。
# 警告が 1 件でもあると、アプリは「点検表が改定されたため…」の注意を出す。設定ファイルを作ったら警告 0 件を目指す。

import json
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


# ---------------- 共通 ----------------

def nfkc(s):
    return unicodedata.normalize('NFKC', str(s if s is not None else ''))


def norm(s):
    """文字列の比較用 (全角・半角をそろえ、空白を除く)。profile.js の norm と同じ"""
    return re.sub(r'\s+', '', nfkc(s)).strip()


def col_num(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def col_name(c):
    s = ''
    while c > 0:
        s = chr(65 + (c - 1) % 26) + s
        c = (c - 1) // 26
    return s


def parse_ref(ref):
    m = re.match(r'^\$?([A-Z]+)\$?(\d+)$', ref or '')
    return (int(m.group(2)), col_num(m.group(1))) if m else None


def num(s):
    n = nfkc(s).replace(',', '').strip()
    return float(n) if re.match(r'^[-+]?(\d+\.?\d*|\.\d+)$', n) else None


def js_num_str(v):
    """JavaScript の String(+v.toPrecision(12)) に近い表示"""
    v = float('%.12g' % v)
    if v == int(v) and abs(v) < 1e21:
        return str(int(v))
    return repr(v)


def local(tag):
    return tag.rsplit('}', 1)[-1]


def children(node, name):
    return [x for x in node.iter() if local(x.tag) == name]


def first(node, name):
    for x in node.iter():
        if local(x.tag) == name:
            return x
    return None


def rich_text(node):
    """<si>/<is> 内の <t> を連結 (ふりがな <rPh> は除く)"""
    out = []

    def walk(n, in_rph):
        for ch in n:
            nm = local(ch.tag)
            if nm == 'rPh':
                continue
            if nm == 't':
                out.append(ch.text or '')
            else:
                walk(ch, in_rph)
    walk(node, False)
    return ''.join(out)


def resolve_path(base, target):
    if target.startswith('/'):
        return target[1:]
    parts = base.split('/')[:-1]
    for seg in target.split('/'):
        if seg == '..':
            parts.pop()
        elif seg != '.':
            parts.append(seg)
    return '/'.join(parts)


def shift_formula(f, dr, dc):
    """式の中の相対参照を dr 行・dc 列ずらす (xlsx.js の shiftFormula と同じ)"""
    def sh(part):
        def rep(m):
            pre, dcs, col, drs, row = m.groups()
            c = col_num(col) if dcs else col_num(col) + dc
            r = int(row) if drs else int(row) + dr
            if c < 1 or r < 1:
                return m.group(0)
            return f'{pre}{dcs}{col_name(c)}{drs}{r}'
        return re.sub(r'(^|[^A-Za-z0-9_.$])(\$?)([A-Z]{1,3})(\$?)(\d{1,7})(?![A-Za-z0-9_(])', rep, part)
    parts = re.split(r'("(?:[^"]|"")*")', f)
    return ''.join(p if i % 2 else sh(p) for i, p in enumerate(parts))


# ---------------- Excel の読み込み ----------------

BUILTIN_DATE = {14, 15, 16, 17, 22, 27, 28, 29, 30, 31, 34, 35, 36, 50, 51, 52, 53, 54, 55, 56, 57, 58}
BUILTIN_TIME = {18, 19, 20, 21, 32, 33, 45, 46, 47}


def classify_format(fid, code):
    if fid in BUILTIN_DATE:
        return 'date'
    if fid in BUILTIN_TIME:
        return 'time'
    if not code:
        return None
    s = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', code.split(';')[0]).lower()
    if re.search(r'[yd]', s):
        return 'date'
    if re.search(r'[hs]', s):
        return 'time'
    if 'm' in s and not re.search(r'[0#?]', s):
        return 'date'
    return None


class Cell:
    __slots__ = ('r', 'c', 't', 'value', 'fmt', 'has_f', 'formula', 'shared_si', 'empty')


def display(cell):
    """xlsx.js の displayValue と同じ表示"""
    if cell is None or cell.empty:
        return ''
    v = cell.value
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, float):
        if cell.fmt == 'date':
            import datetime
            d = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=v)
            return f'{d.year}/{d.month}/{d.day}'
        if cell.fmt == 'time':
            mins = round((v % 1) * 1440)
            return f'{(mins // 60) % 24}:{mins % 60:02d}'
        return js_num_str(v)
    if cell.has_f and (v is None or v == ''):
        return '(数式)'
    return str(v)


def text(cell):
    return display(cell).strip() if cell is not None and not cell.empty else ''


class Workbook:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.names = set(self.zip.namelist())
        wb = ET.fromstring(self.zip.read('xl/workbook.xml'))
        rels = {r.get('Id'): r.get('Target') for r in children(ET.fromstring(self.zip.read('xl/_rels/workbook.xml.rels')), 'Relationship')}
        self.sheets = []
        for s in children(wb, 'sheet'):
            rid = s.get(f'{{{REL_NS}}}id')
            self.sheets.append({'name': s.get('name'), 'path': resolve_path('xl/workbook.xml', rels[rid])})
        self.shared = []
        if 'xl/sharedStrings.xml' in self.names:
            self.shared = [rich_text(si) for si in children(ET.fromstring(self.zip.read('xl/sharedStrings.xml')), 'si')]
        self.formats = []
        if 'xl/styles.xml' in self.names:
            st = ET.fromstring(self.zip.read('xl/styles.xml'))
            custom = {int(n.get('numFmtId')): n.get('formatCode') for n in children(st, 'numFmt')}
            xfs = first(st, 'cellXfs')
            if xfs is not None:
                for xf in [x for x in xfs if local(x.tag) == 'xf']:
                    fid = int(xf.get('numFmtId') or 0)
                    self.formats.append(classify_format(fid, custom.get(fid)))
        self._cache = {}

    def sheet(self, name):
        if name not in self._cache:
            meta = next(s for s in self.sheets if s['name'] == name)
            self._cache[name] = Sheet(self, meta)
        return self._cache[name]


class Sheet:
    def __init__(self, wb, meta):
        self.name = meta['name']
        doc = ET.fromstring(wb.zip.read(meta['path']))
        self.cells = {}
        shared_f = {}
        self.max_r = self.max_c = 0
        for c in children(doc, 'c'):
            pos = parse_ref(c.get('r'))
            if not pos:
                continue
            t = c.get('t') or 'n'
            s = int(c.get('s') or 0)
            v = first(c, 'v')
            f = first(c, 'f')
            value = None
            if t == 's' and v is not None:
                value = wb.shared[int(v.text)] if int(v.text) < len(wb.shared) else ''
            elif t == 'inlineStr':
                isn = first(c, 'is')
                value = rich_text(isn) if isn is not None else ''
            elif t == 'b' and v is not None:
                value = v.text == '1'
            elif t in ('str', 'e') and v is not None:
                value = v.text or ''
            elif v is not None and (v.text or '') != '':
                value = float(v.text)
            cell = Cell()
            cell.r, cell.c = pos
            cell.t, cell.value = t, value
            cell.fmt = wb.formats[s] if s < len(wb.formats) else None
            cell.has_f = f is not None
            cell.formula = None
            cell.shared_si = None
            cell.empty = (value is None or value == '') and not cell.has_f
            if f is not None:
                ft = f.text or ''
                if f.get('t') == 'shared':
                    si = f.get('si')
                    if ft:
                        shared_f[si] = (pos[0], pos[1], ft)
                    cell.shared_si = si
                if ft:
                    cell.formula = ft
            self.cells[pos] = cell
            if not cell.empty:
                self.max_r = max(self.max_r, pos[0])
                self.max_c = max(self.max_c, pos[1])
        for cell in self.cells.values():
            if cell.formula or not cell.shared_si:
                continue
            m = shared_f.get(cell.shared_si)
            if m:
                cell.formula = shift_formula(m[2], cell.r - m[0], cell.c - m[1])
        self.merges = []
        for m in children(doc, 'mergeCell'):
            a, *b = m.get('ref').split(':')
            p, q = parse_ref(a), parse_ref(b[0] if b else a)
            self.merges.append((p[0], p[1], q[0], q[1]))
        self.validations = []
        for dv in children(doc, 'dataValidation'):
            if dv.get('type') != 'list':
                continue
            ranges = []
            for part in (dv.get('sqref') or '').split():
                a, *b = part.split(':')
                p, q = parse_ref(a), parse_ref(b[0] if b else a)
                if p:
                    ranges.append((p[0], p[1], (q or p)[0], (q or p)[1]))
            f1 = first(dv, 'formula1')
            self.validations.append((ranges, (f1.text or '').strip() if f1 is not None else ''))

    def get(self, r, c):
        return self.cells.get((r, c))

    def value_at(self, r, c):
        for (r1, c1, r2, c2) in self.merges:
            if r1 <= r <= r2 and c1 <= c <= c2:
                cell = self.get(r1, c1)
                break
        else:
            cell = self.get(r, c)
        return cell if cell is not None and not cell.empty else None

    def validation_options(self, r, c):
        for ranges, f in self.validations:
            if any(r1 <= r <= r2 and c1 <= c <= c2 for (r1, c1, r2, c2) in ranges):
                if f.startswith('"'):
                    return [s.strip() for s in f[1:-1].split(',') if s.strip()] or None
                if '!' in f:
                    return None
                a, *b = f.split(':')
                p = parse_ref(a)
                if not p:
                    return None
                q = parse_ref(b[0]) if b else p
                out = [display(self.get(rr, cc)).strip() for rr in range(p[0], q[0] + 1) for cc in range(p[1], q[1] + 1)]
                out = [s for s in out if s]
                return out or None
        return None


def is_recorded(cell):
    """記録が入っているセルか。「-」だけのセルは空とみなす (xlsx.js の isRecorded と同じ)"""
    if cell is None or cell.empty:
        return False
    if cell.has_f:
        return True
    return not re.match(r'^[-‐-―−ーｰ]+$', nfkc(display(cell)).strip())


# ---------------- 設定に従ったカードの組み立て (profile.js と同じ規則) ----------------

def check_headers(sheet, profile):
    out = []
    for ref, expect in (profile.get('headerCheck') or {}).items():
        p = parse_ref(ref)
        got = text(sheet.value_at(*p)) if p else ''
        if norm(got) != norm(expect):
            out.append(f'見出し {ref} が「{expect}」ではありません (実際: 「{got}」)')
    return out


def split_opts(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [o.strip() for o in v.split('|') if o.strip()]
    return None


def build(sheet, profile, target_col=None):
    warnings = []
    C = {k: col_num(v) for k, v in profile['columns'].items()}

    def at(r, k):
        return sheet.get(r, C[k]) if C.get(k) else None

    warnings += check_headers(sheet, profile)

    label_col = col_num(profile['meta']['labelCol'])
    meta_rows = []
    for m in profile['meta']['rows']:
        found = 0
        for r in range(1, profile['items']['startRow']):
            if norm(text(sheet.get(r, label_col))) == norm(m['label']):
                found = r
                break
        if found:
            meta_rows.append({**m, 'row': found})
        else:
            warnings.append(f'基本情報「{m["label"]}」の行が見つかりません')

    key_col = col_num(profile['items']['keyCol'])
    stop = profile['items'].get('stopWhen')
    rows = []
    for r in range(profile['items']['startRow'], sheet.max_r + 1):
        if stop and norm(text(sheet.get(r, col_num(stop['col'])))) == norm(stop['equals']):
            break
        if any(text(at(r, k)) for k in ('name', 'sub', 'unit', 'set', 'min', 'max')):
            rows.append(r)

    by_key = {}
    for r in rows:
        by_key.setdefault(norm(text(sheet.get(r, key_col))), []).append(r)
    row_label = {}
    last = ''
    for r in rows:
        name = re.sub(r'[\s　]+', ' ', text(at(r, 'name'))) or last
        last = name
        row_label[r] = {'name': name, 'label': name or f'{r}行目', 'sub': text(at(r, 'sub'))}

    moved = {}

    def name_ok(row, name):
        lb = row_label[row]
        return not name or norm(name) in norm(lb['label'] + lb['sub']) or norm(lb['label']) == norm(name)

    def find_row(ref, what):
        rs = by_key.get(norm(ref.get('no', '')))
        if not rs:
            warnings.append(f'{what}: キー {ref.get("no")} の行が見つかりません')
            return None
        named = [r for r in rs if name_ok(r, ref.get('name'))]
        pick = next((r for r in named if r == ref.get('_row')), named[0] if named else rs[0])
        if ref.get('name') and not name_ok(pick, ref['name']):
            warnings.append(f'{what}: キー {ref.get("no")} の項目名が「{ref["name"]}」ではありません (実際: 「{row_label[pick]["label"]}」)')
            return None
        if isinstance(ref.get('_row'), int) and ref['_row'] != pick:
            moved[pick] = f'キー {ref.get("no")} {ref.get("name") or ""}: {ref["_row"]} → {pick} 行目'
        return pick

    preset = {r for r in (find_row(ref, '前もって値を入れてある行') for ref in profile.get('presetRows') or []) if r}

    rec_start = col_num(profile['records']['startCol'])
    rec_rows = [m['row'] for m in meta_rows] + [r for r in rows if r not in preset]
    record_cols = [c for c in range(rec_start, max(sheet.max_c, rec_start) + 1) if any(is_recorded(sheet.get(r, c)) for r in rec_rows)]
    next_col = record_cols[-1] + 1 if record_cols else rec_start
    if target_col is None:
        target_col = next_col
    prev_cols = [c for c in record_cols if c < target_col]
    prev_col = prev_cols[-1] if prev_cols else None

    def base(r):
        cur = sheet.get(r, target_col)
        prev = sheet.get(r, prev_col) if prev_col else None
        return {
            'row': r, 'ref': col_name(target_col) + str(r),
            'locked': bool(cur is not None and not cur.empty),
            'existing': display(cur) if cur is not None and not cur.empty else '',
            'prev': display(prev) if prev is not None and not prev.empty else '',
        }

    meta = [{**base(m['row']), 'kind': 'meta', 'label': re.sub(r'[:：]\s*$', '', m['label']), 'type': m['type']} for m in meta_rows]

    kinds = profile.get('kinds') or {}
    items = []
    last_section = ''
    for r in rows:
        section = text(at(r, 'section')) or last_section
        last_section = section
        name, sub = row_label[r]['name'], row_label[r]['sub']
        set_text = text(at(r, 'set'))
        kind_text = text(at(r, 'kind'))
        range_kind = None
        if any(norm(k) == norm(kind_text) for k in kinds.get('range') or []):
            range_kind = 'range'
        elif any(norm(k) == norm(kind_text) for k in kinds.get('reference') or []):
            range_kind = 'reference'
        mn, mx = num(text(at(r, 'min'))), num(text(at(r, 'max')))
        tol = next((norm(k) for k in kinds.get('tolerance') or [] if norm(kind_text).startswith(norm(k))), None)
        if tol and num(set_text) is not None:
            w = num(norm(kind_text)[len(tol):])
            if w is not None:
                mn, mx, range_kind = round(num(set_text) - w, 6), round(num(set_text) + w, 6), 'range'
        has_range = bool(range_kind and (mn is not None or mx is not None))
        b = base(r)
        options = sheet.validation_options(r, target_col)
        if not options:
            probe = [norm(x) for x in (set_text, b['prev']) if x]
            options = next((s for s in profile.get('choiceSets') or [] if any(norm(o) in probe for o in s)), None)
        unit = text(at(r, 'unit'))
        numeric = unit or num(set_text) is not None or mn is not None or mx is not None or num(b['prev']) is not None
        fallback = 'number' if profile.get('defaultType') == 'number' and not (b['prev'] and num(b['prev']) is None) else 'text'
        typ = 'choice' if options else ('number' if numeric else fallback)
        fmt = lambda v: js_num_str(v) if v is not None else ''
        items.append({
            **b, 'kind': 'item', 'key': text(sheet.get(r, key_col)), 'section': section,
            'label': name or f'{r}行目', 'sub': sub, 'unit': unit, 'setText': set_text,
            'rangeKind': range_kind if has_range else None,
            'rangeText': f'{fmt(mn)}～{fmt(mx)}' if has_range else '',
            'kindText': kind_text, 'digits': num(text(at(r, 'digits'))),
            'options': options, 'type': typ, 'cond': {},
        })

    item_by_row = {c['row']: c for c in items}

    def resolve(ref, what):
        r = find_row(ref, what)
        return item_by_row.get(r) if r else None

    for ref in profile.get('rowTypes') or []:
        c = resolve(ref, '入力方法の指定')
        if not c:
            continue
        opts = split_opts(ref.get('options'))
        if opts:
            c['options'], c['type'] = opts, 'choice'
        elif ref.get('type') in ('number', 'text', 'choice'):
            c['type'] = ref['type']
        else:
            warnings.append(f'入力方法の指定: キー {ref.get("no")} の type / options が正しくありません')
        dis = split_opts(ref.get('disabled')) or []
        if dis:
            c['disabledOptions'] = dis
        if c['type'] == 'choice' and not c.get('options'):
            warnings.append(f'入力方法の指定: キー {ref.get("no")} は選択式ですが選択肢 (options) がありません')
            c['type'] = 'text'

    for g in profile.get('sectionRows') or []:
        for ref in g.get('rows') or []:
            c = resolve(ref, f'見出し「{g.get("section")}」の行')
            if c:
                c['section'] = g.get('section')

    for ref in profile.get('formulaRows') or []:
        c = resolve(ref, '自動計算の行')
        if not c:
            continue
        if c['locked']:
            cur = sheet.get(c['row'], target_col)
            if cur is not None and cur.formula:
                c.update(type='formula', formula=re.sub(r'^=', '', cur.formula), locked=False, keepFormula=True)
            continue
        f = re.sub(r'^=', '', ref['formula']).replace('{col}', col_name(target_col)) if ref.get('formula') else ''
        if not f:
            src = next((col for col in reversed(prev_cols) if getattr(sheet.get(c['row'], col), 'formula', None)), None)
            if src:
                f = shift_formula(sheet.get(c['row'], src).formula, 0, target_col - src)
        if not f:
            warnings.append(f'自動計算の行: キー {ref.get("no")} の式が前回までの記録に見つかりません (設定の formula で指定できます)')
            continue
        c['type'], c['formula'] = 'formula', f

    for ref in profile.get('compactRows') or []:
        c = resolve(ref, '一覧表示の行')
        if c:
            c['compact'] = True

    split_order = {}  # 行 → (かたまりの番号, 値の順番)。入力の順番は値ごとに上から下へ
    for gi, g in enumerate(profile.get('splitGroups') or []):
        members = [c for c in (resolve(ref, '列分け表示の行') for ref in g.get('rows') or []) if c]
        by = g.get('by') or ('label' if g.get('pattern') else 'sub')
        rx = re.compile(g['pattern']) if g.get('pattern') else None

        def key_of(c):
            v = nfkc(c.get(by) or '')
            if not rx:
                return v
            m = rx.search(v)
            return ((m.group(1) if m.groups() and m.group(1) is not None else m.group(0)).strip()) if m else ''
        keys = [nfkc(k) for k in (g.get('order') or list(dict.fromkeys(key_of(c) for c in members)))]
        for c in members:
            key = key_of(c)
            c['compact'] = True
            c['split'] = f'{gi + 1}:{key}'
            if rx and by == 'label':
                c['label'] = rx.sub('', nfkc(c['label']), count=1).strip() or c['label']
            split_order[c['row']] = (gi, keys.index(key) if key in keys else len(keys))

    for ref in profile.get('optionalRows') or []:
        c = resolve(ref, '任意入力の行')
        if c:
            c['optional'] = True

    excluded = set()
    for ref in profile.get('exclude') or []:
        c = resolve(ref, '対象外の行')
        if c:
            excluded.add(c['row'])

    conditions = []
    for cd in profile.get('conditions') or []:
        cond = {'key': cd.get('key'), 'label': cd.get('label'), 'options': cd.get('options'), 'kind': (cd.get('match') or {}).get('type', 'select')}
        if cd.get('source'):
            src = resolve(cd['source'], f'条件「{cd.get("label")}」')
            if not src:
                continue
            cond['sourceRow'] = src['row']
            if cd.get('options') and not src.get('options'):
                src['options'], src['type'] = cd['options'], 'choice'
        match = cd.get('match') or {}
        if match.get('type') == 'token':
            opts = [norm(o) for o in cd['options']]
            for c in items:
                toks = []
                for k in match['columns']:
                    s = nfkc(c['label'] if k == 'name' else c.get(k) or '')
                    toks += [norm(t) for t in re.findall(r'[A-Za-z0-9.]+|[^\sA-Za-z0-9.()（）/、,]+', s)]
                toks = [t for t in toks if t]
                hit = next((o for i, o in enumerate(cd['options']) if opts[i] in toks), None)
                if hit and c['row'] != cond.get('sourceRow'):
                    c['cond'][cd['key']] = hit
        elif match.get('type') == 'band':
            rx = re.compile(match['pattern'])
            for c in items:
                for k in match['columns']:
                    m = rx.search(nfkc(c['label'] if k == 'name' else c.get(k) or ''))
                    if m:
                        c['cond'][cd['key']] = m.group(0)
                        break
        elif cd.get('rows'):
            for opt, refs in cd['rows'].items():
                for ref in refs:
                    c = resolve(ref, f'条件「{cd.get("label")}」の{opt}')
                    if c:
                        c['cond'][cd['key']] = opt
            if cd.get('placeBefore'):
                pb = resolve(cd['placeBefore'], f'条件「{cd.get("label")}」の表示位置')
                cond['placeBefore'] = pb['row'] if pb else None
            for opt, ref in (cd.get('writes') or {}).items():
                resolve(ref, f'条件「{cd.get("label")}」の記入先')
        conditions.append(cond)

    if moved:
        ex = list(moved.values())
        warnings.append(f'行の位置が設定と変わっています ({len(moved)} か所。例: {" / ".join(ex[:3])}{" ほか" if len(ex) > 3 else ""})')

    # 列分け表示のかたまりは、最初の行の位置にまとめて置き、値ごとの順に並べ替える (アプリの入力の順番)
    ordered, placed = [], set()
    for c in items:
        so = split_order.get(c['row'])
        if not so:
            ordered.append(c)
            continue
        if so[0] in placed:
            continue
        placed.add(so[0])
        group = [x for x in items if split_order.get(x['row'], (None,))[0] == so[0]]
        group.sort(key=lambda x: (split_order[x['row']][1], x['row']))
        ordered += group
    items = ordered
    for c in items:
        c['excluded'] = c['row'] in excluded
    return {
        'sheet': sheet.name, 'meta': meta, 'items': items, 'conditions': conditions, 'warnings': warnings,
        'recordCols': [col_name(c) for c in record_cols], 'prevCol': col_name(prev_col) if prev_col else None,
        'targetCol': col_name(target_col), 'nextCol': col_name(next_col),
        'presetRows': sorted(preset),
    }


# ---------------- 結果の表示 ----------------

TYPE_JA = {'number': '数値', 'text': '文字', 'choice': '選択', 'formula': '自動計算', 'date': '日付', 'time': '時間', 'name': '担当'}


def report(file_name, profile, wb, candidates, res):
    out = []
    p = out.append
    p(f'設定: {profile.get("name")}')
    fm = profile.get('fileMatch')
    if fm:
        ok = nfkc(fm) in nfkc(file_name)
        p(f'ファイル名の一致 (fileMatch「{fm}」): {"OK" if ok else "× 合わない (アプリはこの設定を選ばない)"}')
    p(f'見出しが合うシート: {", ".join(candidates) or "なし (アプリでは入力を始められない)"}')
    if not res:
        return '\n'.join(out)
    p(f'使ったシート: {res["sheet"]}')
    p(f'記録のある列: {" ".join(res["recordCols"][-5:])}{" ほか" if len(res["recordCols"]) > 5 else ""} (計 {len(res["recordCols"])} 列)')
    p(f'新しい記録の列: {res["nextCol"]} / 書き込む列: {res["targetCol"]} / 前回の列: {res["prevCol"]}')
    if res['presetRows']:
        p(f'前もって値を入れてある行 (列探しで見ない): {", ".join(map(str, res["presetRows"]))}')
    p('')
    p(f'警告: {len(res["warnings"])} 件' + (' (アプリは「点検表が改定されたため…」の注意を出す)' if res['warnings'] else ' (OK)'))
    for w in res['warnings']:
        p(f'  - {w}')
    p('')
    p('基本情報:')
    for m in res['meta']:
        p(f'  {m["row"]:>4} 行 {m["label"]} ({TYPE_JA.get(m["type"], m["type"])}){" 記入済" if m["locked"] else ""}')
    p('')
    p('条件:')
    for cd in res['conditions']:
        n = sum(1 for c in res['items'] if cd['key'] in c['cond'])
        p(f'  {cd["label"]} ({cd["kind"]}) 選択肢: {cd.get("options")} / 元の行: {cd.get("sourceRow")} / 振り分けた行: {n} 行')
    p('')
    p('カード (行 | キー | 区分 | 項目名 | 入力方法 | 管理値 | 前回 | 印):')
    sec = None
    for c in res['items']:
        if c['section'] != sec:
            sec = c['section']
            p(f'  ── {sec or "(区分なし)"} ──')
        marks = []
        if c['excluded']:
            marks.append('対象外')
        if c['locked']:
            marks.append(f'記入済「{c["existing"]}」')
        if c.get('optional'):
            marks.append('任意')
        if c.get('compact'):
            marks.append('一覧')
        if c.get('split'):
            marks.append(f'列分け {c["split"]}')
        if c.get('keepFormula'):
            marks.append('式あり→値だけ書く')
        for k, v in c['cond'].items():
            marks.append(f'条件 {k}={v}')
        if c['row'] in res['presetRows']:
            marks.append('前もって値')
        typ = TYPE_JA.get(c['type'], c['type'])
        if c['type'] == 'choice':
            dis = c.get('disabledOptions')
            typ += '[' + '|'.join(c['options']) + ']' + (f' 押せない:{"|".join(dis)}' if dis else '')
        if c['type'] == 'formula':
            typ += f' ={c["formula"]}'
        label = c['label'] + (f' / {c["sub"]}' if c['sub'] else '') + (f' [{c["unit"]}]' if c['unit'] else '')
        rng = c['rangeText'] + (f' ({c["kindText"]})' if c['rangeText'] and c['kindText'] else '')
        p(f'  {c["row"]:>4} | {c["key"]:>4} | {label} | {typ} | {rng or "-"} | {c["prev"] or "-"} | {" ".join(marks)}')
    return '\n'.join(out)


def main(argv):
    opts = {}
    i = 0
    rest = []
    while i < len(argv):
        a = argv[i]
        if a in ('--sheet', '--col'):
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        if a == '--json':
            opts['json'] = True
        else:
            rest.append(a)
        i += 1
    if len(rest) < 2:
        print('使い方: python check_profile.py <設定.json> <点検表.xlsm> [--sheet シート名] [--col 列名] [--json]')
        return 2
    with open(rest[0], encoding='utf-8') as f:
        profile = json.load(f)
    if profile.get('type') != 'inspection-cards-profile':
        print('点検カードの設定ファイルではありません (type が inspection-cards-profile でない)')
        return 2
    for k in ('name', 'sheet', 'columns', 'items', 'records', 'meta'):
        if not profile.get(k):
            print(f'設定ファイルに「{k}」がありません')
            return 2
    wb = Workbook(rest[1])
    has_check = bool(profile.get('headerCheck'))
    candidates = [s['name'] for s in wb.sheets if (has_check or s['name'] == profile['sheet']) and not check_headers(wb.sheet(s['name']), profile)]
    sheet_name = opts.get('sheet') or (candidates[0] if candidates else None)
    res = None
    if sheet_name:
        if sheet_name not in [s['name'] for s in wb.sheets]:
            print(f'シート「{sheet_name}」がありません')
            return 2
        res = build(wb.sheet(sheet_name), profile, col_num(opts['col']) if opts.get('col') else None)
    if opts.get('json'):
        print(json.dumps({'candidates': candidates, **(res or {})}, ensure_ascii=False, indent=1))
    else:
        print(report(rest[1].replace('\\', '/').split('/')[-1], profile, wb, candidates, res))
        if len(candidates) > 1:
            print(f'\n※ 見出しが合うシートが {len(candidates)} つあります。アプリでは初回に選ぶ必要があります (--sheet で切り替えて確認できます)')
    return 0 if res and not res['warnings'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
