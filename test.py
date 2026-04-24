"""
Convert .docx to markdown.

Core idea: walk the doc once, maintaining a stack of (numId, ilvl) pairs
that represents the list contexts we're currently nested inside. Depth of
any item is its position in that stack. When a new numId appears mid-flow,
it pushes as a sub-list of whatever's on top. When a previous numId
reappears, we pop back to it.

Example sequence of numIds: 1, 2, 2, 2, 1, 11, 11, 11, 1
    see 1    -> push           [1]           depth 1
    see 2    -> push            [1, 2]       depth 2  (sub of 1)
    see 2,2  -> stay            [1, 2]       depth 2
    see 1    -> pop back        [1]          depth 1
    see 11   -> push            [1, 11]      depth 2  (sub of 1)
    see 1    -> pop back        [1]          depth 1
"""

import re
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


def _numpr(pe):
    """If paragraph is a list item, return (num_id, ilvl). Else None."""
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


def _walk(doc):
    """Yield one dict per body item: table, heading, list, body, or blank."""

    # load numbering.xml so we can render marker text (1., a., 1.1, etc.)
    defs = {}
    try:
        part = doc.part.numbering_part
    except Exception:
        part = None
    if part is not None:
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

    # stack of (num_id, ilvl) representing nesting path
    stack = []
    counters = {}  # num_id -> {ilvl: count}

    def compute_depth(nid, il):
        entry = (nid, il)
        # exact match on stack -> truncate to it
        for i in range(len(stack) - 1, -1, -1):
            if stack[i] == entry:
                del stack[i + 1:]
                return i + 1
        # numId on stack at a different ilvl -> pop back to it, then push or replace
        for i in range(len(stack) - 1, -1, -1):
            if stack[i][0] == nid:
                del stack[i + 1:]
                top_il = stack[-1][1]
                if il > top_il:
                    stack.append(entry)
                else:
                    stack[-1] = entry
                return len(stack)
        # new numId entirely -> push as sub-list of current top
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

            # render marker text (1., a., 1.1., etc.)
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
