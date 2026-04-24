"""Simple .docx -> markdown converter for LLM preprocessing.

Keeps the useful pieces from the original:
- Word heading styles become Markdown headings.
- Word numbering is reconstructed from numbering.xml.
- numId/ilvl is the main depth signal.
- indentation is only a fallback when a numId is flat/malformed.
- typed section markers like C4.10.3.4 are detected conservatively.
"""

import argparse
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

NUMBERED_AS_HEADINGS = True
MAX_LEVEL = 6
TYPED_SECTION_RE = re.compile(
    r"^\s*(?P<marker>(?:[A-Z]{1,5}\d+|\d+)(?:\.\d+){0,8})\.?\s+(?P<body>.+?)\s*$"
)


def _numpr(pe):
    pPr = pe.find(qn("w:pPr"))
    if pPr is None:
        return None
    numPr = pPr.find(qn("w:numPr"))
    if numPr is None:
        return None
    numId = numPr.find(qn("w:numId"))
    if numId is None:
        return None
    nid = numId.get(qn("w:val"))
    if not nid or nid == "0":
        return None
    ilvl = numPr.find(qn("w:ilvl"))
    return nid, int(ilvl.get(qn("w:val"), "0")) if ilvl is not None else 0


def _left_indent(pPr):
    if pPr is None:
        return None
    ind = pPr.find(qn("w:ind"))
    if ind is None or ind.get(qn("w:left")) is None:
        return None
    try:
        return int(ind.get(qn("w:left")))
    except ValueError:
        return None


def _load_numbering_defs(doc):
    try:
        part = doc.part.numbering_part
    except Exception:
        return {}

    abstract_defs = {}
    for abstract in part.element.findall(qn("w:abstractNum")):
        levels = {}
        for lvl in abstract.findall(qn("w:lvl")):
            ilvl = int(lvl.get(qn("w:ilvl"), "0"))
            fmt = lvl.find(qn("w:numFmt"))
            text = lvl.find(qn("w:lvlText"))
            start = lvl.find(qn("w:start"))
            levels[ilvl] = {
                "fmt": fmt.get(qn("w:val")) if fmt is not None else "decimal",
                "text": text.get(qn("w:val")) if text is not None else f"%{ilvl + 1}.",
                "start": int(start.get(qn("w:val"))) if start is not None else 1,
                "indent": _left_indent(lvl.find(qn("w:pPr"))),
            }
        abstract_defs[abstract.get(qn("w:abstractNumId"))] = levels

    defs = {}
    for num in part.element.findall(qn("w:num")):
        ref = num.find(qn("w:abstractNumId"))
        if ref is not None and ref.get(qn("w:val")) in abstract_defs:
            defs[num.get(qn("w:numId"))] = abstract_defs[ref.get(qn("w:val"))]
    return defs


def _indent_for(pe, nid, ilvl, defs):
    own = _left_indent(pe.find(qn("w:pPr")))
    if own is not None:
        return own
    return defs.get(nid, {}).get(ilvl, {}).get("indent")


def _indent_depths(doc, defs):
    stats = {}
    for el in doc.element.body:
        if el.tag != qn("w:p"):
            continue
        info = _numpr(el)
        if not info:
            continue
        nid, ilvl = info
        indent = _indent_for(el, nid, ilvl, defs)
        row = stats.setdefault(nid, {"ilvls": set(), "indents": set()})
        row["ilvls"].add(ilvl)
        if indent is not None:
            row["indents"].add(indent)

    # Only use indentation when Word's ilvl gives us no hierarchy.
    out = {}
    for nid, row in stats.items():
        if len(row["ilvls"]) == 1 and len(row["indents"]) > 1:
            out[nid] = {v: i + 1 for i, v in enumerate(sorted(row["indents"]))}
    return out


def _depth(nid, ilvl, indent, indent_depths):
    if indent is not None and nid in indent_depths:
        return min(indent_depths[nid].get(indent, ilvl + 1), MAX_LEVEL)
    return min(ilvl + 1, MAX_LEVEL)


def _roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    s = []
    for v, sym in vals:
        while n >= v:
            s.append(sym)
            n -= v
    return "".join(s)


def _format_number(n, fmt):
    if fmt == "lowerLetter" and 1 <= n <= 26:
        return chr(ord("a") + n - 1)
    if fmt == "upperLetter" and 1 <= n <= 26:
        return chr(ord("A") + n - 1)
    if fmt == "lowerRoman":
        return _roman(n).lower()
    if fmt == "upperRoman":
        return _roman(n)
    if fmt == "decimalZero":
        return f"{n:02d}"
    return str(n)


def _render_marker(nid, ilvl, defs, counters):
    levels = defs.get(nid, {})
    lvl = levels.get(ilvl)
    c = counters.setdefault(nid, {})

    for k in list(c):
        if k > ilvl:
            del c[k]
    c[ilvl] = c[ilvl] + 1 if ilvl in c else (lvl["start"] if lvl else 1)

    if lvl is None:
        return ".".join(str(c[k]) for k in sorted(c) if k <= ilvl) + ".", "decimal"
    if lvl["fmt"] == "bullet":
        return "", "bullet"

    marker = lvl["text"]
    for k in range(ilvl + 1):
        if k in levels:
            marker = marker.replace(
                f"%{k + 1}",
                _format_number(c.get(k, levels[k]["start"]), levels[k]["fmt"]),
            )
    return re.sub(r"%\d+", "", marker), lvl["fmt"]


def _format_runs(para):
    out = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        if not text.strip():
            out.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        inner = text.strip()
        if run.bold and run.italic:
            out.append(f"{lead}***{inner}***{trail}")
        elif run.bold:
            out.append(f"{lead}**{inner}**{trail}")
        elif run.italic:
            out.append(f"{lead}*{inner}*{trail}")
        else:
            out.append(text)
    return re.sub(r"\*{4,}", "", "".join(out) if out else para.text)


def _table_md(table):
    rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in table.rows]
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    pad = lambda r: (r + [""] * (cols - len(r)))[:cols]
    lines = ["| " + " | ".join(pad(rows[0])) + " |",
             "| " + " | ".join("---" for _ in range(cols)) + " |"]
    lines += ["| " + " | ".join(pad(r)) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _heading_level(para):
    style = (para.style.name or "").lower()
    for i in range(1, 7):
        if style.startswith(f"heading {i}"):
            return i
    if style == "title":
        return 1
    if style == "subtitle":
        return 2
    return None


def _typed_section(text):
    m = TYPED_SECTION_RE.match(text)
    if not m:
        return None
    marker = m.group("marker")
    return marker, m.group("body"), min(marker.count(".") + 1, MAX_LEVEL)


def _walk(doc):
    defs = _load_numbering_defs(doc)
    indent_depth = _indent_depths(doc, defs)
    counters = {}

    for el in doc.element.body:
        if el.tag == qn("w:tbl"):
            yield {"kind": "table", "text": _table_md(Table(el, doc))}
            continue
        if el.tag != qn("w:p"):
            continue

        para = Paragraph(el, doc)
        text = _format_runs(para).strip()
        if not text:
            yield {"kind": "blank"}
            continue

        hl = _heading_level(para)
        if hl:
            yield {"kind": "heading", "level": hl, "text": text}
            continue

        info = _numpr(el)
        if info:
            nid, ilvl = info
            indent = _indent_for(el, nid, ilvl, defs)
            marker, fmt = _render_marker(nid, ilvl, defs, counters)
            yield {
                "kind": "numbered", "num_id": nid, "ilvl": ilvl,
                "indent": indent, "depth": _depth(nid, ilvl, indent, indent_depth),
                "fmt": fmt, "marker": marker, "text": text,
            }
            continue

        typed = _typed_section(text)
        if typed:
            marker, body, level = typed
            yield {"kind": "typed_section", "level": level, "marker": marker, "text": text, "body": body}
            continue

        yield {"kind": "body", "text": text}


def convert(path, numbered_as_headings=NUMBERED_AS_HEADINGS):
    doc = Document(str(path))
    out = []

    def blank():
        if out and out[-1] != "":
            out.append("")

    for item in _walk(doc):
        kind = item["kind"]
        if kind == "blank":
            blank()
        elif kind == "table":
            blank(); out += [item["text"], ""]
        elif kind == "heading":
            blank(); out += ["#" * item["level"] + " " + item["text"], ""]
        elif kind == "typed_section":
            blank(); out += ["#" * item["level"] + " " + item["text"], ""]
        elif kind == "numbered":
            depth = item["depth"]
            if item["fmt"] == "bullet":
                out.append("    " * (depth - 1) + "- " + item["text"])
            elif numbered_as_headings:
                blank()
                prefix = "#" * min(depth + 1, MAX_LEVEL)
                out.append(f"{prefix} {item['marker']} {item['text']}" if item["marker"] else f"{prefix} {item['text']}")
                out.append("")
            else:
                out.append("    " * (depth - 1) + f"{item['marker']} {item['text']}".strip())
        else:
            out.append(item["text"])

    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def inspect(path):
    doc = Document(str(path))
    print(f"{'kind':<14} {'numId':<6} {'ilvl':<4} {'depth':<5} {'indent':<8} {'marker':<14} text")
    print("-" * 100)
    for item in _walk(doc):
        if item["kind"] == "numbered":
            print(f"numbered       {item['num_id']:<6} {item['ilvl']:<4} {item['depth']:<5} {str(item['indent']):<8} {item['marker'][:14]:<14} {item['text'][:70]}")
        elif item["kind"] == "typed_section":
            print(f"typed_section  {'':<6} {'':<4} {item['level']:<5} {'':<8} {item['marker'][:14]:<14} {item['body'][:70]}")
        elif item["kind"] == "heading":
            print(f"heading        {'':<6} {'':<4} {item['level']:<5} {'':<8} {'':<14} {item['text'][:70]}")
        elif item["kind"] == "body":
            print(f"body           {'':<6} {'':<4} {'':<5} {'':<8} {'':<14} {item['text'][:70]}")
        elif item["kind"] == "table":
            print("table")
