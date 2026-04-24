"""
Converts .docx files to markdown.

Reads heading styles, inline formatting (bold/italic), tables, and
numbered/lettered/bulleted lists directly from the docx. List items
become headings with their numbering preserved in the text so a
level-0 item reads as "## 1. Foo" and a level-1 item reads as
"### 1.1. Bar" or "### a. Bar" depending on the Word format.

Usage:
    from docx_to_md import convert
    markdown = convert("path/to/doc.docx")
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Inline formatting (bold, italic)
# ---------------------------------------------------------------------------

def _format_runs(paragraph: Paragraph) -> str:
    """Wrap bold/italic runs in markdown syntax."""
    if not paragraph.runs:
        return paragraph.text

    parts = []
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue

        bold = run.bold
        italic = run.italic

        # don't wrap whitespace-only runs
        if not text.strip():
            parts.append(text)
            continue

        # pull whitespace outside formatting markers
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        inner = text.strip()

        if bold and italic:
            parts.append(f"{leading}***{inner}***{trailing}")
        elif bold:
            parts.append(f"{leading}**{inner}**{trailing}")
        elif italic:
            parts.append(f"{leading}*{inner}*{trailing}")
        else:
            parts.append(text)

    result = "".join(parts)
    # merge adjacent same-format markers from consecutive runs
    result = re.sub(r'\*\*\*\*\*\*', '', result)
    result = re.sub(r'\*\*\*\*', '', result)
    return result


# ---------------------------------------------------------------------------
# Heading detection from paragraph style
# ---------------------------------------------------------------------------

_HEADING_MAP = {
    "heading 1": 1,
    "heading 2": 2,
    "heading 3": 3,
    "heading 4": 4,
    "heading 5": 5,
    "heading 6": 6,
    "title": 1,
    "subtitle": 2,
}


def _get_style_heading_level(paragraph: Paragraph) -> int | None:
    style_name = (paragraph.style.name or "").lower()
    for key, level in _HEADING_MAP.items():
        if style_name == key or style_name.startswith(key):
            return level
    return None


# ---------------------------------------------------------------------------
# Number formatting helpers
# ---------------------------------------------------------------------------

def _to_roman(n: int) -> str:
    vals = [
        (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
        (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
        (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
    ]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def _format_number(value: int, fmt: str) -> str:
    if fmt == 'decimal':
        return str(value)
    if fmt == 'lowerLetter':
        # a..z, then aa, bb, cc (Word's convention)
        if value <= 26:
            return chr(ord('a') + value - 1)
        return chr(ord('a') + ((value - 1) % 26)) * (((value - 1) // 26) + 1)
    if fmt == 'upperLetter':
        if value <= 26:
            return chr(ord('A') + value - 1)
        return chr(ord('A') + ((value - 1) % 26)) * (((value - 1) // 26) + 1)
    if fmt == 'lowerRoman':
        return _to_roman(value).lower()
    if fmt == 'upperRoman':
        return _to_roman(value)
    # decimalZero, ordinal, cardinalText, etc all fall back to decimal
    return str(value)


# ---------------------------------------------------------------------------
# Numbering / list tracking
# ---------------------------------------------------------------------------

class _NumberingTracker:
    """
    Resolves list item numbering (1., a., i., 1.1., etc.) by parsing
    numbering.xml and tracking running counters across the document.
    """

    def __init__(self, doc):
        # numId -> { ilvl -> {fmt, text, start} }
        self._defs: dict[str, dict[int, dict]] = {}
        # numId -> { ilvl -> current_count }
        self._counters: dict[str, dict[int, int]] = {}
        self._load(doc)

    def _load(self, doc):
        try:
            numbering_part = doc.part.numbering_part
        except (AttributeError, KeyError, NotImplementedError):
            return
        if numbering_part is None:
            return

        root = numbering_part.element

        # first pass: abstractNum definitions
        abstract_defs: dict[str, dict[int, dict]] = {}
        for abs_num in root.findall(qn('w:abstractNum')):
            abs_id = abs_num.get(qn('w:abstractNumId'))
            levels: dict[int, dict] = {}
            for lvl in abs_num.findall(qn('w:lvl')):
                ilvl = int(lvl.get(qn('w:ilvl'), '0'))

                fmt_el = lvl.find(qn('w:numFmt'))
                fmt = fmt_el.get(qn('w:val')) if fmt_el is not None else 'decimal'

                text_el = lvl.find(qn('w:lvlText'))
                lvl_text = (
                    text_el.get(qn('w:val'))
                    if text_el is not None else f'%{ilvl + 1}.'
                )

                start_el = lvl.find(qn('w:start'))
                start = int(start_el.get(qn('w:val'))) if start_el is not None else 1

                levels[ilvl] = {'fmt': fmt, 'text': lvl_text, 'start': start}
            abstract_defs[abs_id] = levels

        # second pass: num -> abstractNum resolution
        for num in root.findall(qn('w:num')):
            num_id = num.get(qn('w:numId'))
            ref = num.find(qn('w:abstractNumId'))
            if ref is None:
                continue
            abs_id = ref.get(qn('w:val'))
            if abs_id in abstract_defs:
                self._defs[num_id] = abstract_defs[abs_id]

    def resolve(self, paragraph: Paragraph):
        """
        If paragraph is a list item, return (ilvl, fmt, marker_text).
        fmt is something like 'decimal', 'bullet', 'lowerLetter'.
        marker_text is the rendered prefix like '1.' or 'a.' or '1.1.'.
        Returns None if the paragraph is not part of a list.
        """
        pPr = paragraph._element.find(qn('w:pPr'))
        if pPr is None:
            return None
        numPr = pPr.find(qn('w:numPr'))
        if numPr is None:
            return None

        num_id_el = numPr.find(qn('w:numId'))
        ilvl_el = numPr.find(qn('w:ilvl'))
        if num_id_el is None:
            return None
        num_id = num_id_el.get(qn('w:val'))
        ilvl = int(ilvl_el.get(qn('w:val'), '0')) if ilvl_el is not None else 0

        # numId 0 means "explicitly no numbering" in Word
        if num_id == '0':
            return None

        # fallback path if we couldn't find the definition for some reason
        if num_id not in self._defs or ilvl not in self._defs[num_id]:
            counters = self._counters.setdefault(num_id, {})
            for deeper in [k for k in counters if k > ilvl]:
                del counters[deeper]
            counters[ilvl] = counters.get(ilvl, 0) + 1
            parts = [str(counters[lv]) for lv in range(ilvl + 1) if lv in counters]
            return (ilvl, 'decimal', ".".join(parts) + ".")

        levels = self._defs[num_id]
        level_def = levels[ilvl]
        fmt = level_def['fmt']

        # advance counters: reset deeper levels, then bump or start this one
        counters = self._counters.setdefault(num_id, {})
        for deeper in [k for k in counters if k > ilvl]:
            del counters[deeper]
        if ilvl in counters:
            counters[ilvl] += 1
        else:
            counters[ilvl] = level_def['start']

        if fmt == 'bullet':
            return (ilvl, fmt, '')

        # substitute %1, %2, ... in lvlText using each level's own format
        marker = level_def['text']
        for lv in range(ilvl + 1):
            if lv in counters and lv in levels:
                val = counters[lv]
                lv_fmt = levels[lv]['fmt']
                marker = marker.replace(f'%{lv + 1}', _format_number(val, lv_fmt))

        return (ilvl, fmt, marker)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _table_to_markdown(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)

    def pad(r):
        while len(r) < col_count:
            r.append("")
        return r[:col_count]

    lines = []
    lines.append("| " + " | ".join(pad(rows[0])) + " |")
    lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(pad(row)) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

# How many hashes to use for a list item at level N.
# Level 0 (top-level list item, "1.") -> ##
# Level 1 ("1.1" or "a.") -> ###
# Adjust if you want list items to sit at a different depth.
_LIST_HEADING_OFFSET = 2


def convert(file_path: str | Path) -> str:
    """
    Convert a .docx to markdown.

    - Heading styles become # through ######.
    - List items become headings with their numbering preserved,
      for example "## 1. Foo", "### 1.1. Bar", "### a. Baz".
    - Bullet list items become standard markdown bullets.
    - Tables become markdown tables.
    - Bold/italic runs are preserved.
    """
    doc = Document(str(file_path))
    tracker = _NumberingTracker(doc)
    lines: list[str] = []

    def ensure_blank_line():
        if lines and lines[-1] != "":
            lines.append("")

    for element in doc.element.body:
        # table: build it directly from the element, no rescanning doc.tables
        if element.tag == qn('w:tbl'):
            tbl = Table(element, doc)
            ensure_blank_line()
            lines.append(_table_to_markdown(tbl))
            lines.append("")
            continue

        if element.tag != qn('w:p'):
            continue

        para = Paragraph(element, doc)
        text = _format_runs(para)

        # empty paragraph collapses to a single blank line
        if not text.strip():
            ensure_blank_line()
            continue

        # explicit heading style wins over list-based heading logic
        style_level = _get_style_heading_level(para)
        if style_level is not None:
            ensure_blank_line()
            lines.append(f"{'#' * style_level} {text.strip()}")
            lines.append("")
            continue

        # list item?
        list_info = tracker.resolve(para)
        if list_info is not None:
            ilvl, fmt, marker = list_info

            if fmt == 'bullet':
                indent = "    " * ilvl
                lines.append(f"{indent}- {text.strip()}")
                continue

            heading_level = min(ilvl + _LIST_HEADING_OFFSET, 6)
            prefix = '#' * heading_level
            body = text.strip()
            if marker:
                line = f"{prefix} {marker} {body}"
            else:
                line = f"{prefix} {body}"
            ensure_blank_line()
            lines.append(line)
            lines.append("")
            continue

        # regular body paragraph
        lines.append(text)

    result = "\n".join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()
