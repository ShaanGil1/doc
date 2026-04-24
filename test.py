"""
Converts .docx files to markdown.

Approach: scan the doc once to build {numId: {ilvl: depth}} by ranking the
ilvls that actually appear in each numbering chain. Then emit markdown
using a pure lookup. Each numId is its own chain and starts fresh at
depth 1. Ilvl jumps inside a chain get compressed, so a chain using
{0, 2, 5} produces depths {1, 2, 3} with no skipped markdown levels.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

def _format_runs(paragraph: Paragraph) -> str:
    if not paragraph.runs:
        return paragraph.text

    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        if not text.strip():
            parts.append(text)
            continue

        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        inner = text.strip()

        if run.bold and run.italic:
            parts.append(f"{leading}***{inner}***{trailing}")
        elif run.bold:
            parts.append(f"{leading}**{inner}**{trailing}")
        elif run.italic:
            parts.append(f"{leading}*{inner}*{trailing}")
        else:
            parts.append(text)

    # collapse adjacent markers left over from consecutive same-style runs
    result = "".join(parts)
    result = re.sub(r'\*\*\*\*\*\*', '', result)
    result = re.sub(r'\*\*\*\*', '', result)
    return result


# ---------------------------------------------------------------------------
# Heading detection
# ---------------------------------------------------------------------------

_HEADING_STYLE_MAP = {
    "heading 1": 1, "heading 2": 2, "heading 3": 3,
    "heading 4": 4, "heading 5": 5, "heading 6": 6,
    "title": 1, "subtitle": 2,
}

_HEADER_KEYWORDS = ("heading", "title", "header", "chapter", "section", "subtitle")


def _style_heading_level(paragraph: Paragraph) -> int | None:
    name = (paragraph.style.name or "").lower()
    for key, level in _HEADING_STYLE_MAP.items():
        if name == key or name.startswith(key):
            return level
    return 1 if any(kw in name for kw in _HEADER_KEYWORDS) else None


def _looks_like_header(paragraph: Paragraph) -> bool:
    """Bold-only paragraphs or ones with 14pt+ font, under 140 chars."""
    text = paragraph.text.strip()
    if not text or len(text) > 140:
        return False

    content_runs = [r for r in paragraph.runs if r.text.strip()]
    if not content_runs:
        return False

    if all(r.bold for r in content_runs):
        return True

    for r in content_runs:
        size = getattr(r.font, 'size', None)
        if size is not None and getattr(size, 'pt', 0) >= 14:
            return True
    return False


# ---------------------------------------------------------------------------
# Number formatting for list markers
# ---------------------------------------------------------------------------

def _format_number(value: int, fmt: str) -> str:
    if fmt == 'lowerLetter':
        base = ord('a')
    elif fmt == 'upperLetter':
        base = ord('A')
    else:
        # decimal and anything unsupported (roman, ordinal, etc.) -> decimal
        return str(value)

    if value <= 26:
        return chr(base + value - 1)
    # aa, bb, cc for 27, 28, 29 (Word convention)
    return chr(base + ((value - 1) % 26)) * (((value - 1) // 26) + 1)


# ---------------------------------------------------------------------------
# numPr extraction and depth map
# ---------------------------------------------------------------------------

def _read_numpr(para_elem):
    """Pull (num_id, ilvl) off a paragraph element, or return None."""
    pPr = para_elem.find(qn('w:pPr'))
    if pPr is None:
        return None
    numPr = pPr.find(qn('w:numPr'))
    if numPr is None:
        return None
    num_id_el = numPr.find(qn('w:numId'))
    if num_id_el is None:
        return None
    num_id = num_id_el.get(qn('w:val'))
    if num_id == '0':
        return None
    ilvl_el = numPr.find(qn('w:ilvl'))
    ilvl = int(ilvl_el.get(qn('w:val'), '0')) if ilvl_el is not None else 0
    return (num_id, ilvl)


def _build_depth_map(doc) -> dict[str, dict[int, int]]:
    """
    {numId: {ilvl: depth}} where depth starts at 1 and is the rank of
    each ilvl among those actually used in that chain.
    """
    seen: dict[str, set[int]] = {}
    for p in doc.element.body.iter(qn('w:p')):
        info = _read_numpr(p)
        if info is not None:
            num_id, ilvl = info
            seen.setdefault(num_id, set()).add(ilvl)

    return {
        num_id: {ilvl: rank + 1 for rank, ilvl in enumerate(sorted(ilvls))}
        for num_id, ilvls in seen.items()
    }


# ---------------------------------------------------------------------------
# Numbering resolver: read numbering.xml, track counters, render markers
# ---------------------------------------------------------------------------

class _NumberingTracker:
    def __init__(self, doc):
        self._defs: dict[str, dict[int, dict]] = {}
        self._counters: dict[str, dict[int, int]] = {}
        self._load(doc)

    def _load(self, doc):
        try:
            part = doc.part.numbering_part
        except (AttributeError, KeyError, NotImplementedError):
            return
        if part is None:
            return

        abstract_defs: dict[str, dict[int, dict]] = {}
        for abs_num in part.element.findall(qn('w:abstractNum')):
            abs_id = abs_num.get(qn('w:abstractNumId'))
            levels: dict[int, dict] = {}
            for lvl in abs_num.findall(qn('w:lvl')):
                ilvl = int(lvl.get(qn('w:ilvl'), '0'))
                fmt_el = lvl.find(qn('w:numFmt'))
                text_el = lvl.find(qn('w:lvlText'))
                start_el = lvl.find(qn('w:start'))
                levels[ilvl] = {
                    'fmt': fmt_el.get(qn('w:val')) if fmt_el is not None else 'decimal',
                    'text': text_el.get(qn('w:val')) if text_el is not None else f'%{ilvl + 1}.',
                    'start': int(start_el.get(qn('w:val'))) if start_el is not None else 1,
                }
            abstract_defs[abs_id] = levels

        for num in part.element.findall(qn('w:num')):
            ref = num.find(qn('w:abstractNumId'))
            if ref is not None:
                abs_id = ref.get(qn('w:val'))
                if abs_id in abstract_defs:
                    self._defs[num.get(qn('w:numId'))] = abstract_defs[abs_id]

    def resolve(self, paragraph: Paragraph):
        """Returns (num_id, ilvl, fmt, marker_text) or None."""
        info = _read_numpr(paragraph._element)
        if info is None:
            return None
        num_id, ilvl = info

        levels = self._defs.get(num_id, {})
        level_def = levels.get(ilvl)

        # advance counters: reset deeper levels, bump or start this one
        counters = self._counters.setdefault(num_id, {})
        for k in [k for k in counters if k > ilvl]:
            del counters[k]
        start = level_def['start'] if level_def else 1
        counters[ilvl] = counters[ilvl] + 1 if ilvl in counters else start

        # no definition for this level -> fall back to a plain "1.2.3." form
        if level_def is None:
            parts = [str(counters[lv]) for lv in sorted(counters) if lv <= ilvl]
            return (num_id, ilvl, 'decimal', '.'.join(parts) + '.')

        fmt = level_def['fmt']
        if fmt == 'bullet':
            return (num_id, ilvl, fmt, '')

        marker = level_def['text']
        for lv in range(ilvl + 1):
            if lv in levels:
                val = counters.get(lv, levels[lv]['start'])
                marker = marker.replace(f'%{lv + 1}', _format_number(val, levels[lv]['fmt']))
        marker = re.sub(r'%\d+', '', marker)
        return (num_id, ilvl, fmt, marker)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _table_to_markdown(table: Table) -> str:
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


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

# depth 1 ('1.') -> ##, depth 2 -> ###, etc. Bump this to push lists deeper.
_LIST_HEADING_OFFSET = 1


def convert(file_path: str | Path, promote_heuristic_headers: bool = True) -> str:
    doc = Document(str(file_path))
    numbering = _NumberingTracker(doc)
    depth_map = _build_depth_map(doc)
    lines: list[str] = []

    def blank():
        if lines and lines[-1] != '':
            lines.append('')

    for element in doc.element.body:
        if element.tag == qn('w:tbl'):
            blank()
            lines.append(_table_to_markdown(Table(element, doc)))
            lines.append('')
            continue

        if element.tag != qn('w:p'):
            continue

        para = Paragraph(element, doc)
        text = _format_runs(para)
        if not text.strip():
            blank()
            continue

        # explicit Heading style
        style_level = _style_heading_level(para)
        if style_level is not None:
            blank()
            lines.append(f"{'#' * style_level} {text.strip()}")
            lines.append('')
            continue

        # list item
        list_info = numbering.resolve(para)
        if list_info is not None:
            num_id, ilvl, fmt, marker = list_info
            d = depth_map.get(num_id, {}).get(ilvl, 1)

            if fmt == 'bullet':
                lines.append('    ' * (d - 1) + '- ' + text.strip())
                continue

            prefix = '#' * min(d + _LIST_HEADING_OFFSET, 6)
            body = text.strip()
            blank()
            lines.append(f'{prefix} {marker} {body}' if marker else f'{prefix} {body}')
            lines.append('')
            continue

        # heuristic header for bold/large standalone paragraphs
        if promote_heuristic_headers and _looks_like_header(para):
            blank()
            lines.append(f'# {text.strip()}')
            lines.append('')
            continue

        lines.append(text)

    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
