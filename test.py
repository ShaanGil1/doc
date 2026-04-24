"""
Convert .docx to markdown.

Algorithm:
    Pre-pass: record the last list position where each numId appears.
    Main pass: walk the body with a stack of (num_id, ilvl). For each
    list item, compute depth:
        1. If (num_id, ilvl) already on stack -> truncate to it
        2. Else if num_id on stack at a different ilvl -> pop back to
           it, then push/replace based on whether the new ilvl is deeper
           or shallower
        3. Else (new num_id) -> first purge any stack entries whose
           numId's last occurrence is before the current position
           (those spans have ended), then push

The pre-pass is the "look-ahead" that lets us tell whether a numId
still has more items coming or if its span has already ended.

Two entry points:
    convert(path)  -> markdown string
    inspect(path)  -> prints the diagnostic walk
"""

import re
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


def _numpr(pe):
    pPr = pe.find(qn('w:pPr'))
    if pPr is None:
        return None
    np = pPr.find(qn('w:numPr'))
    if np is None:
        return None
    nid_el = np.find(qn('w:numId'))
    if nid_el is None:
        return None
    nid = nid_el.get(qn('w:val'))
    if nid == '0':
        return None
    il_el = np.find(qn('w:ilvl'))
    il = int(il_el.get(qn('w:val'), '0')) if il_el is not None else 0
    return (nid, il)


def _format_number(v, fmt):
    if fmt == 'lowerLetter' and v <= 26:
        return chr(ord('a') + v - 1)
    if fmt == 'upperLetter' and v <= 26:
        return chr(ord('A') + v - 1)
    return str(v)


def _format_runs(para):
    parts = []
    for r in para.runs:
        t = r.text
        if not t:
            continue
        if not t.strip():
            parts.append(t)
            continue
        lead = t[:len(t) - len(t.lstrip())]
        trail = t[len(t.rstrip()):]
        inner = t.strip()
        if r.bold and r.italic:
            parts.append(f'{lead}***{inner}***{trail}')
        elif r.bold:
            parts.append(f'{lead}**{inner}**{trail}')
        elif r.italic:
            parts.append(f'{lead}*{inner}*{trail}')
        else:
            parts.append(t)
    result = ''.join(parts) if parts else para.text
    result = re.sub(r'\*\*\*\*\*\*', '', result)
    result = re.sub(r'\*\*\*\*', '', result)
    return result


def _table_md(table):
    rows = [[c.text.strip().replace('\n', ' ') for c in r.cells] for r in table.rows]
    if not rows:
        return ''
    cols = max(len(r) for r in rows)
    pad = lambda r: (r + [''] * (cols - len(r)))[:cols]
    lines = [
        '| ' + ' | '.join(pad(rows[0])) + ' |',
        '| ' + ' | '.join('---' for _ in range(cols)) + ' |',
    ]
    lines += ['| ' + ' | '.join(pad(r)) + ' |' for r in rows[1:]]
    return '\n'.join(lines)


def _scan_lists(doc):
    """
    First pass: walk direct body paragraphs in order, return two things:
      - last_pos: {num_id: last list-index where it appeared}
      - parents:  set of num_ids that have another num_id's first occurrence
                  strictly inside their span (first..last)
    """
    occurrences = {}
    pos = 0
    for el in doc.element.body:
        if el.tag != qn('w:p'):
            continue
        info = _numpr(el)
        if info:
            occurrences.setdefault(info[0], []).append(pos)
            pos += 1

    last_pos = {nid: idxs[-1] for nid, idxs in occurrences.items()}
    parents = set()
    for nid, idxs in occurrences.items():
        first, last = idxs[0], idxs[-1]
        for other_nid, other_idxs in occurrences.items():
            if other_nid != nid and any(first < i < last for i in other_idxs):
                parents.add(nid)
                break
    return last_pos, parents


def _load_numbering_defs(doc):
    defs = {}
    try:
        part = doc.part.numbering_part
    except Exception:
        part = None
    if part is None:
        return defs
    abs_defs = {}
    for a in part.element.findall(qn('w:abstractNum')):
        lvls = {}
        for l in a.findall(qn('w:lvl')):
            il = int(l.get(qn('w:ilvl'), '0'))
            f = l.find(qn('w:numFmt'))
            t = l.find(qn('w:lvlText'))
            s = l.find(qn('w:start'))
            lvls[il] = {
                'fmt': f.get(qn('w:val')) if f is not None else 'decimal',
                'text': t.get(qn('w:val')) if t is not None else f'%{il + 1}.',
                'start': int(s.get(qn('w:val'))) if s is not None else 1,
            }
        abs_defs[a.get(qn('w:abstractNumId'))] = lvls
    for n in part.element.findall(qn('w:num')):
        r = n.find(qn('w:abstractNumId'))
        if r is not None and r.get(qn('w:val')) in abs_defs:
            defs[n.get(qn('w:numId'))] = abs_defs[r.get(qn('w:val'))]
    return defs


def _walk(doc):
    defs = _load_numbering_defs(doc)
    last_pos, parents = _scan_lists(doc)

    stack = []          # list of (num_id, ilvl)
    counters = {}       # num_id -> {ilvl: count}
    list_pos = 0        # current list-item index

    def compute_depth(nid, il):
        entry = (nid, il)
        # (1) exact match on stack -> truncate to it
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] == entry:
                del stack[i + 1:]
                return i + 1
        # (2) this is a NEW parent numId and everything on the stack is already
        # dead (its last occurrence is before this position) -> the prior list
        # world is over, start fresh at depth 1
        if nid in parents and not any(s[0] == nid for s in stack):
            if not any(last_pos.get(s[0], -1) >= list_pos for s in stack):
                stack.clear()
                stack.append(entry)
                return 1
        # (3) same numId at different ilvl -> pop back to it, then push/replace
        for i in range(len(stack) - 1, -1, -1):
            if stack[i][0] == nid:
                del stack[i + 1:]
                top_il = stack[-1][1]
                if il > top_il:
                    stack.append(entry)
                else:
                    stack[-1] = entry
                return len(stack)
        # (4) completely new numId (non-parent, or parent with still-alive
        # contexts on the stack) -> push as sub-list of current top
        stack.append(entry)
        return len(stack)

    for el in doc.element.body:
        if el.tag == qn('w:tbl'):
            yield {'kind': 'table', 'text': _table_md(Table(el, doc))}
            continue
        if el.tag != qn('w:p'):
            continue

        para = Paragraph(el, doc)
        text = _format_runs(para)

        if not text.strip():
            yield {'kind': 'blank'}
            continue

        # heading style
        style = (para.style.name or '').lower()
        hl = None
        for i in range(1, 7):
            if style.startswith(f'heading {i}'):
                hl = i
                break
        if style == 'title':
            hl = 1
        elif style == 'subtitle':
            hl = 2
        if hl:
            yield {'kind': 'heading', 'level': hl, 'text': text.strip()}
            continue

        # list item
        info = _numpr(el)
        if info:
            nid, il = info
            levels = defs.get(nid, {})
            lvl = levels.get(il)

            # counter bookkeeping for marker rendering
            c = counters.setdefault(nid, {})
            for k in [k for k in c if k > il]:
                del c[k]
            start = lvl['start'] if lvl else 1
            c[il] = c[il] + 1 if il in c else start

            # marker text
            if lvl is None:
                parts = [str(c[k]) for k in sorted(c) if k <= il]
                marker, fmt = '.'.join(parts) + '.', 'decimal'
            elif lvl['fmt'] == 'bullet':
                marker, fmt = '', 'bullet'
            else:
                fmt = lvl['fmt']
                marker = lvl['text']
                for k in range(il + 1):
                    if k in levels:
                        v = c.get(k, levels[k]['start'])
                        marker = marker.replace(
                            f'%{k + 1}',
                            _format_number(v, levels[k]['fmt']),
                        )
                marker = re.sub(r'%\d+', '', marker)

            d = compute_depth(nid, il)
            list_pos += 1
            yield {
                'kind': 'list', 'num_id': nid, 'ilvl': il,
                'depth': d, 'fmt': fmt, 'marker': marker,
                'text': text.strip(),
            }
            continue

        yield {'kind': 'body', 'text': text}


def convert(path):
    doc = Document(str(path))
    out = []

    def blank():
        if out and out[-1] != '':
            out.append('')

    for item in _walk(doc):
        k = item['kind']
        if k == 'blank':
            blank()
        elif k == 'table':
            blank()
            out.append(item['text'])
            out.append('')
        elif k == 'heading':
            blank()
            out.append('#' * item['level'] + ' ' + item['text'])
            out.append('')
        elif k == 'list':
            if item['fmt'] == 'bullet':
                out.append('    ' * (item['depth'] - 1) + '- ' + item['text'])
            else:
                prefix = '#' * min(item['depth'] + 1, 6)
                if item['marker']:
                    out.append(f'{prefix} {item["marker"]} {item["text"]}')
                else:
                    out.append(f'{prefix} {item["text"]}')
                blank()
        elif k == 'body':
            out.append(item['text'])

    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip()


def inspect(path):
    doc = Document(str(path))
    last_pos, parents = _scan_lists(doc)

    print('NUMID SUMMARY  (parent = has another numId inside its span)')
    print('-' * 70)
    for nid in sorted(last_pos, key=lambda n: last_pos[n]):
        tag = 'parent' if nid in parents else 'sub'
        print(f'  numId {nid:<6}  last at list-pos {last_pos[nid]:<4}  ({tag})')
    print()

    print(f'{"kind":<6}  {"numId":<6}  {"ilvl":<4}  {"depth":<5}  {"marker":<10}  text')
    print('-' * 100)
    for item in _walk(doc):
        k = item['kind']
        if k == 'blank':
            continue
        if k == 'list':
            print(f'{"list":<6}  {item["num_id"]:<6}  {item["ilvl"]:<4}  '
                  f'{item["depth"]:<5}  {item["marker"]:<10}  {item["text"][:70]}')
        elif k == 'heading':
            label = f'H{item["level"]}'
            print(f'{label:<6}  {"":<6}  {"":<4}  {"":<5}  {"":<10}  {item["text"][:70]}')
        elif k == 'body':
            print(f'{"body":<6}  {"":<6}  {"":<4}  {"":<5}  {"":<10}  {item["text"][:70]}')
        elif k == 'table':
            print(f'{"table":<6}')
    print()
    print('MARKDOWN OUTPUT')
    print('-' * 70)
    print(convert(path))
