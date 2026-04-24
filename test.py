"""
Convert .docx to markdown.

Two entry points:
    convert(path)  -> returns the markdown string
    inspect(path)  -> prints what the converter sees in the doc,
                      useful for debugging when the output looks wrong

The algorithm:
    1. Load numbering.xml so we can generate marker text (1., a., 1.1, etc.)
    2. Build a depth map: for each numId, rank the ilvls that actually
       appear and assign depth = rank + 1. Each numId chain is independent
       and starts at depth 1.
    3. Walk the body. For each list paragraph, look up its depth in the
       map and emit `#` * (depth + 1) + marker + text.
"""

import re
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _numpr(para_elem):
    """If paragraph is a list item, return (num_id, ilvl). Otherwise None."""
    pPr = para_elem.find(qn('w:pPr'))
    if pPr is None:
        return None
    numPr = pPr.find(qn('w:numPr'))
    if numPr is None:
        return None
    nid_el = numPr.find(qn('w:numId'))
    if nid_el is None:
        return None
    nid = nid_el.get(qn('w:val'))
    if nid == '0':
        return None
    il_el = numPr.find(qn('w:ilvl'))
    ilvl = int(il_el.get(qn('w:val'), '0')) if il_el is not None else 0
    return (nid, ilvl)


def _format_number(value, fmt):
    if fmt == 'lowerLetter' and value <= 26:
        return chr(ord('a') + value - 1)
    if fmt == 'upperLetter' and value <= 26:
        return chr(ord('A') + value - 1)
    return str(value)


def _format_runs(paragraph):
    parts = []
    for r in paragraph.runs:
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
    result = ''.join(parts) if parts else paragraph.text
    result = re.sub(r'\*\*\*\*\*\*', '', result)
    result = re.sub(r'\*\*\*\*', '', result)
    return result


def _table_md(table):
    rows = [[c.text.strip().replace('\n', ' ') for c in r.cells] for r in table.rows]
    if not rows:
        return ''
    cols = max(len(r) for r in rows)
    pad = lambda r: (r + [''] * (cols - len(r)))[:cols]
    out = [
        '| ' + ' | '.join(pad(rows[0])) + ' |',
        '| ' + ' | '.join('---' for _ in range(cols)) + ' |',
    ]
    out += ['| ' + ' | '.join(pad(r)) + ' |' for r in rows[1:]]
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# The core walk: yields one dict per body item
# ---------------------------------------------------------------------------

def _walk(doc):
    # load numbering definitions
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

    # build depth map: rank ilvls within each numId
    seen = {}
    for p in doc.element.body.iter(qn('w:p')):
        info = _numpr(p)
        if info:
            seen.setdefault(info[0], set()).add(info[1])
    depth_map = {
        nid: {il: rank + 1 for rank, il in enumerate(sorted(ilvls))}
        for nid, ilvls in seen.items()
    }

    counters = {}

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

            # counter bookkeeping: reset deeper levels, bump or start this one
            c = counters.setdefault(nid, {})
            for k in [k for k in c if k > il]:
                del c[k]
            start = lvl['start'] if lvl else 1
            c[il] = c[il] + 1 if il in c else start

            # generate marker
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

            depth = depth_map.get(nid, {}).get(il, 1)
            yield {
                'kind': 'list', 'num_id': nid, 'ilvl': il,
                'depth': depth, 'fmt': fmt, 'marker': marker,
                'text': text.strip(),
            }
            continue

        yield {'kind': 'body', 'text': text}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    """
    Print everything the converter sees in the doc. Compare this against
    the doc open in Word to find where it's getting confused.
    """
    doc = Document(str(path))

    seen = {}
    for p in doc.element.body.iter(qn('w:p')):
        info = _numpr(p)
        if info:
            seen.setdefault(info[0], set()).add(info[1])
    depth_map = {
        nid: {il: rank + 1 for rank, il in enumerate(sorted(ilvls))}
        for nid, ilvls in seen.items()
    }

    print('DEPTH MAP  (numId -> {raw_ilvl: assigned_depth})')
    print('-' * 70)
    for nid, m in depth_map.items():
        print(f'  numId={nid}  :  {m}')
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


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('usage: python docx_to_md.py <path.docx> [--inspect]')
        sys.exit(1)
    if '--inspect' in sys.argv:
        inspect(sys.argv[1])
    else:
        print(convert(sys.argv[1]))
