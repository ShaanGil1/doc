"""
Converts .docx files to markdown.

Key ideas:

- Visual nesting depth for list items is derived from a running stack of
  (numId, ilvl) pairs, not from the raw docx ilvl. Word's ilvl can be
  arbitrary (a letter sublevel might be defined at ilvl=5 in the numbering
  definition), so using it directly as a markdown depth produces garbage
  like ###### for a first-level sublist. The stack approach gives us
  "where this item actually sits in the hierarchy of items we've seen".

- Non-list paragraphs are tested against heading heuristics (bold-only
  runs, large font, header-ish custom style names). This catches section
  titles that aren't tagged with a Heading style in Word.

- List markers (1., a., 1.1., i.) are reconstructed from numbering.xml
  and kept in the output text.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Inline formatting (bold / italic)
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

    result = "".join(parts)
    # collapse adjacent same-style markers from consecutive runs
    result = re.sub(r'\*\*\*\*\*\*', '', result)
    result = re.sub(r'\*\*\*\*', '', result)
    return result


# ---------------------------------------------------------------------------
# Heading detection: styles first, then heuristics
# ---------------------------------------------------------------------------

_HEADING_STYLE_MAP = {
    "heading 1": 1,
    "heading 2": 2,
    "heading 3": 3,
    "heading 4": 4,
    "heading 5": 5,
    "heading 6": 6,
    "title": 1,
    "subtitle": 2,
}

# words that, if they appear in a custom style name, hint this is a header
_HEADER_KEYWORDS = ("heading", "title", "header", "chapter", "section", "subtitle")


def _style_heading_level(paragraph: Paragraph) -> int | None:
    name = (paragraph.style.name or "").lower()
    for key, level in _HEADING_STYLE_MAP.items():
        if name == key or name.startswith(key):
            return level
    # custom style whose name sounds like a header
    for kw in _HEADER_KEYWORDS:
        if kw in name:
            return 1
    return None


def _looks_like_header(paragraph: Paragraph) -> bool:
    """
    Heuristic for section headers that aren't marked with a Heading style.
    Triggers when the whole paragraph is bold, or uses a font noticeably
    larger than typical body text.
    """
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
        if size is not None:
            try:
                if size.pt >= 14:
                    return True
            except (ValueError, AttributeError):
                pass

    return False


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
    return str(value)


# ---------------------------------------------------------------------------
# Numbering resolver: reads numbering.xml and generates the marker text
# ---------------------------------------------------------------------------

class _NumberingTracker:
    def __init__(self, doc):
        self._defs: dict[str, dict[int, dict]] = {}
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
        Returns (num_id, ilvl, fmt, marker_text) if paragraph is a list item,
        otherwise None.
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

        if num_id == '0':
            return None

        # fallback if we couldn't read the numbering definition
        if num_id not in self._defs or ilvl not in self._defs[num_id]:
            counters = self._counters.setdefault(num_id, {})
            for deeper in [k for k in counters if k > ilvl]:
                del counters[deeper]
            counters[ilvl] = counters.get(ilvl, 0) + 1
            parts = [str(counters[lv]) for lv in sorted(counters) if lv <= ilvl]
            return (num_id, ilvl, 'decimal', ".".join(parts) + ".")

        levels = self._defs[num_id]
        level_def = levels[ilvl]
        fmt = level_def['fmt']

        counters = self._counters.setdefault(num_id, {})
        for deeper in [k for k in counters if k > ilvl]:
            del counters[deeper]
        if ilvl in counters:
            counters[ilvl] += 1
        else:
            counters[ilvl] = level_def['start']

        if fmt == 'bullet':
            return (num_id, ilvl, fmt, '')

        marker = level_def['text']
        for lv in range(ilvl + 1):
            if lv in counters and lv in levels:
                marker = marker.replace(
                    f'%{lv + 1}',
                    _format_number(counters[lv], levels[lv]['fmt']),
                )
        return (num_id, ilvl, fmt, marker)


# ---------------------------------------------------------------------------
# Visual depth tracker
# ---------------------------------------------------------------------------

class _DepthTracker:
    """
    Tracks visual nesting depth of list items by walking them in order.

    The stack holds (num_id, ilvl) pairs representing the path of list
    contexts we're currently inside. Depth is just len(stack).

    Rules:
    - If (num_id, ilvl) is already on the stack, this is a continuation.
      Truncate the stack to that spot and return its depth.
    - Otherwise push it. But first pop any same-num_id entries whose
      ilvl is >= this one (those contexts have ended).
    - We deliberately don't pop entries from a DIFFERENT num_id, because
      in Word a sub-list often uses a separate num_id from its parent
      and we want it to stack on top, not replace.
    """

    def __init__(self):
        self.stack: list[tuple[str, int]] = []

    def depth_for(self, num_id: str, ilvl: int) -> int:
        entry = (num_id, ilvl)

        for i, existing in enumerate(self.stack):
            if existing == entry:
                del self.stack[i + 1:]
                return i + 1

        while self.stack:
            top_num, top_ilvl = self.stack[-1]
            if top_num == num_id and top_ilvl >= ilvl:
                self.stack.pop()
            else:
                break

        self.stack.append(entry)
        return len(self.stack)


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

# depth 1 (top-level list item like "1.") -> ##, depth 2 -> ###, etc.
# increase this if you want list items to sit deeper in the heading tree.
_LIST_HEADING_OFFSET = 1


def convert(
    file_path: str | Path,
    promote_heuristic_headers: bool = True,
) -> str:
    """
    Convert a .docx to markdown.

    - Headings (from styles) become # through ######.
    - List items become headings with the Word-rendered marker kept in the
      text. Depth is based on the running hierarchy of list items, not on
      docx ilvl. So '1.' is always ##, its first sublevel (a., i., 1.1,
      whatever) is ###, the next one deeper is ####, and so on, no matter
      how weird the ilvl values are in the underlying numbering definition.
    - Bullet list items stay as markdown bullets, indented by depth.
    - Non-list paragraphs that look like section titles become # when
      promote_heuristic_headers is True (bold-only paragraphs or 14pt+
      fonts). Pass False if you want every plain paragraph to stay as
      body text.
    - Tables become markdown tables.
    """
    doc = Document(str(file_path))
    numbering = _NumberingTracker(doc)
    depth = _DepthTracker()
    lines: list[str] = []

    def ensure_blank_line():
        if lines and lines[-1] != "":
            lines.append("")

    for element in doc.element.body:
        # table
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

        if not text.strip():
            ensure_blank_line()
            continue

        # 1. explicit Heading style
        style_level = _style_heading_level(para)
        if style_level is not None:
            ensure_blank_line()
            lines.append(f"{'#' * style_level} {text.strip()}")
            lines.append("")
            continue

        # 2. list item
        list_info = numbering.resolve(para)
        if list_info is not None:
            num_id, ilvl, fmt, marker = list_info
            d = depth.depth_for(num_id, ilvl)

            if fmt == 'bullet':
                indent = "    " * (d - 1)
                lines.append(f"{indent}- {text.strip()}")
                continue

            heading_level = min(d + _LIST_HEADING_OFFSET, 6)
            prefix = '#' * heading_level
            body = text.strip()
            line = f"{prefix} {marker} {body}" if marker else f"{prefix} {body}"
            ensure_blank_line()
            lines.append(line)
            lines.append("")
            continue

        # 3. heuristic header (bold-only paragraph, large font, etc.)
        if promote_heuristic_headers and _looks_like_header(para):
            ensure_blank_line()
            lines.append(f"# {text.strip()}")
            lines.append("")
            continue

        # 4. regular body text
        lines.append(text)

    result = "\n".join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()
