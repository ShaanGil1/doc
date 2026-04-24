"""
Converts .docx files to markdown.

Reads heading styles, inline formatting (bold/italic), and tables
directly from the docx. Everything else is body text.

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
# Heading detection
# ---------------------------------------------------------------------------

_HEADING_MAP = {
    "heading 1": "#",
    "heading 2": "##",
    "heading 3": "###",
    "heading 4": "####",
    "heading 5": "#####",
    "heading 6": "######",
    "title": "#",
    "subtitle": "##",
}


def _get_heading_prefix(paragraph: Paragraph) -> str | None:
    style_name = (paragraph.style.name or "").lower()
    for key, prefix in _HEADING_MAP.items():
        if style_name == key or style_name.startswith(key):
            return prefix
    return None


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

    lines = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        while len(row) < len(rows[0]):
            row.append("")
        lines.append("| " + " | ".join(row[:len(rows[0])]) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Indentation
# ---------------------------------------------------------------------------

def _get_indent_level(paragraph: Paragraph) -> int:
    """
    Get the indentation level of a paragraph.
    Checks two sources:
      1. numPr (list numbering properties) ilvl attribute
      2. explicit left_indent from paragraph formatting
    Returns an indent level (0 = no indent, 1 = one level in, etc.)
    """
    # check list numbering indent level first
    pPr = paragraph._element.find(qn('w:pPr'))
    if pPr is not None:
        numPr = pPr.find(qn('w:numPr'))
        if numPr is not None:
            ilvl = numPr.find(qn('w:ilvl'))
            if ilvl is not None:
                return int(ilvl.get(qn('w:val'), '0'))

    # fall back to explicit left indent
    left_indent = paragraph.paragraph_format.left_indent
    if left_indent and left_indent > 0:
        # convert EMUs to roughly indent levels (360000 EMU ~ 0.5 inch ~ 1 level)
        return min(int(left_indent / 360000), 6)

    return 0


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(file_path: str | Path) -> str:
    """
    Convert a .docx to markdown.
    Headings from styles, bold/italic from runs, tables, everything else
    is body text with indentation preserved.
    """
    doc = Document(str(file_path))
    lines: list[str] = []

    for element in doc.element.body:
        # table
        if element.tag == qn('w:tbl'):
            for t in doc.tables:
                if t._element is element:
                    lines.append("")
                    lines.append(_table_to_markdown(t))
                    lines.append("")
                    break
            continue

        # skip non-paragraph elements
        if element.tag != qn('w:p'):
            continue

        para = Paragraph(element, doc)
        text = _format_runs(para)

        # empty paragraph
        if not text.strip():
            if lines and lines[-1] != "":
                lines.append("")
            continue

        # heading
        heading_prefix = _get_heading_prefix(para)
        if heading_prefix:
            lines.append("")
            lines.append(f"{heading_prefix} {text.strip()}")
            lines.append("")
            continue

        # body text with indentation preserved
        indent = _get_indent_level(para)
        if indent > 0:
            lines.append("    " * indent + text.strip())
        else:
            lines.append(text)

    result = "\n".join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()
