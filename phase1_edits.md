# Phase 1 edits (md_to_docx) since the files you pasted
Each block replaces the whole definition of the same name (or adds it where noted). `helpers.py` and `logic.py` unchanged.
What they fix: the signature written as a plain marker line with a fence after it (your response body); fences never fail anywhere (markers stripped, lines print as text, a finding); no filler `your name / item 1 / item 2`; fences at any indent.

---

## md_to_docx/rules.py

### REPLACE `FENCE_LINE`  (near line 73)

```python
FENCE_LINE = re.compile(r"^\s*(?:`{3,}|~{3,})")  # any indent: the frontend indents fences too
```

### ADD (new) `SIGNATURE_LINE`  (near line 77)

```python
# a line that is only the marker, e.g. "\[508-Compliance SIGNATURE BLOCK\]"; prose mentioning it does not match
SIGNATURE_LINE = re.compile(r"^[\s\\\[\]*_]*(?:[\w\-]+\s+){0,3}SIGNATURE\s*BLOCK[\s\\\[\]*_]*:?\s*$", re.I)
```

### ADD (new) `ENCLOSURE_LIST_HEAD`  (near line 79)

```python
# the head of an authored "Enclosure(s)" list under the signature; the list is regenerated, so it is dropped
ENCLOSURE_LIST_HEAD = re.compile(r"^\s*Enclosures?\s*(?:\(s\))?\s*:?\s*$", re.I)
```

---

## md_to_docx/config.py

### REPLACE `BACK`  (near line 208)

```python
BACK = {
    "sig_lines": (),  # printed when no signature block was found; empty means print nothing (a finding says so)
    "encl_label": "Enclosure(s)",
    "encl_pattern": "Enclosure %d: %s",
    "encl_display": "ENCLOSURE %d: %s",
    "encl_first": "References",
    "encl_last": "Glossary",
    "toc_title": "TABLE OF CONTENTS",
    "toc_tab_in": 6.5,
    "toc_indent_in": 0.25,
    "toc_depth": 3,
    # Which of our styles become which table of contents level. Word builds
    # the rows from this, so the styles listed here are the ones that appear
    "toc_levels": (("enclosure", 1), ("encl_h2", 2), ("encl_h3", 3), ("glossary_part", 2), ("appendices", 1)),
    "appendices_title": "Appendices",
    "toc_placeholder": "Right-click here and choose Update Field",
    # (title, entries). Entries use the same flush-left, term-underlined
    # shape as the DEFINITIONS section
}
```

### REPLACE `STRICT_NO_CODE_BLOCKS`  (near line 240)

```python
# fence markers are always stripped and their lines rendered as text, so a code block can only come from # input;
# False (the default) makes any that remains a finding, True raises ConversionError (debugging only)
STRICT_NO_CODE_BLOCKS = False
```

---

## md_to_docx/boundaries.py

### REPLACE `imports from rules`  (near line 9)

```python
from rules import (
    BACK_NAMES,
    ENCLOSURE_LIST_HEAD,
    SIGNATURE_LINE,
    BOLD_FIELD_LINE,
    BOLD_TITLE,
    BOLD_TITLE_INLINE,
    COVER_FIELDS,
    ENCLOSURE_TITLE,
    FENCE_LINE,
    HEADING_LINE,
    LIST_MARKER,
    PART_TITLE,
    RULE_LINE,
    SECTION_ALIASES,
    SIGNATURE_MARK,
    TOC_NAMES,
    UNDERSCORE_BOLD,
    Block,
    DlaiDocument,
    Glossary,
    Start,
    normalize,
    unescape,
)
```

### REPLACE `bold_starts`  (near line 66)

```python
def bold_starts(lines: List[str]) -> List[Start]:
    """Input without # headings: bold-only lines are titles (sections by name, "Enclosure N: x", back matter, ToC).
    Past the first enclosure or back matter title a numbered bold line is body; a signature fence ends the sections."""
    starts: List[Start] = []
    fence: Optional[List[str]] = None
    fence_start = 0
    seen_section = past_sections = in_glossary = False

    for index, line in enumerate(lines):
        if fence is not None:
            fence.append(line)
            if FENCE_LINE.match(line):
                body = [l.strip() for l in fence[1:-1] if l.strip()]
                if body and SIGNATURE_MARK.search(body[0]):
                    starts.append(Start("signature", cfg.SIGNATURE_SECTION, fence_start, end=index))
                    past_sections = True  # nothing after it is a section
                fence = None
            continue
        if FENCE_LINE.match(line):
            fence, fence_start = [line], index
            continue
        if RULE_LINE.match(line):
            continue
        if SIGNATURE_LINE.match(line) and (seen_section or past_sections):
            starts.append(Start("signature", cfg.SIGNATURE_SECTION, index))  # marker as a plain line
            past_sections = True
            continue
        if not seen_section and not past_sections:
            cover = cover_start(line, index)
            if cover:
                starts.append(cover)
                continue

        match = BOLD_TITLE.match(line.lstrip())
        if not match:
            # "4. **DEFINITIONS**: See Glossary." is a title with its body inline; numbered only, so a bold lead-in
            # never is
            inline = BOLD_TITLE_INLINE.match(line.lstrip())
            canonical = SECTION_ALIASES.get(normalize(inline.group("name"))) if inline else None
            if canonical and not past_sections:
                starts.append(Start("section", canonical, index, inline=inline.group("rest").strip()))
                seen_section = True
            continue
        name = match.group("name").strip()
        key = normalize(name)
        numbered = bool(match.group("num") or match.group("inner"))
        enclosure = None if numbered else ENCLOSURE_TITLE.match(name)
        back = not numbered and (key in BACK_NAMES or (in_glossary and PART_TITLE.match(key)))
        toc = not numbered and key in TOC_NAMES
        if enclosure or back or toc:
            past_sections = True
            # PART lines only mean something between GLOSSARY and the next
            # enclosure or back matter title
            in_glossary = BACK_NAMES.get(key) == "GLOSSARY" or (in_glossary and bool(PART_TITLE.match(key)))
        if toc:
            starts.append(Start("toc", key, index))
        elif enclosure:
            number = enclosure.group(1)
            starts.append(Start("enclosure", enclosure.group(2).strip(), index, number=int(number) if number else None))
        elif back:
            kind = BACK_NAMES.get(key)
            starts.append(Start(kind.lower() if kind else "glossary_part", name, index))
        elif not past_sections and (numbered or key in SECTION_ALIASES):
            canonical = SECTION_ALIASES.get(key)
            starts.append(Start("section", canonical or name.rstrip(": "), index, matched=canonical is not None))
            seen_section = True
    return starts
```

### REPLACE `heading_starts`  (near line 135)

```python
def heading_starts(lines: List[str]) -> List[Start]:
    """Input with # headings: a required-section name is a section at any level; other top-level headings are
    enclosures."""
    starts: List[Start] = []
    in_fence = False
    levels = []
    for line in lines:
        if FENCE_LINE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            match = HEADING_LINE.match(line)
            if match:
                levels.append(len(match.group(1)))
    top = min(levels) if levels else 1

    in_fence = seen_heading = in_glossary = False
    for index, line in enumerate(lines):
        if FENCE_LINE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not seen_heading:
            cover = cover_start(line, index)
            if cover:
                starts.append(cover)
                continue
        if seen_heading and SIGNATURE_LINE.match(line):
            starts.append(Start("signature", cfg.SIGNATURE_SECTION, index))
            continue
        match = HEADING_LINE.match(line)
        if not match:
            continue
        seen_heading = True
        level, text = len(match.group(1)), match.group(2).strip()
        key = normalize(text)
        canonical = SECTION_ALIASES.get(key)
        if canonical:
            starts.append(Start("section", canonical, index))
            continue
        if in_glossary and PART_TITLE.match(key):
            starts.append(Start("glossary_part", text, index))
            continue
        if level != top:
            continue
        if key in TOC_NAMES:
            starts.append(Start("toc", key, index))
        elif key in BACK_NAMES:
            starts.append(Start(BACK_NAMES[key].lower(), text, index))
        else:
            enclosure = ENCLOSURE_TITLE.match(text)
            number = enclosure.group(1) if enclosure else None
            starts.append(
                Start(
                    "enclosure",
                    enclosure.group(2).strip() if enclosure else text,
                    index,
                    number=int(number) if number else None,
                )
            )
        in_glossary = BACK_NAMES.get(key) == "GLOSSARY"
    return starts
```

### REPLACE `assemble`  (near line 202)

```python
def assemble(lines: List[str], starts: List[Start], mode: str) -> DlaiDocument:
    """Starts -> DlaiDocument. A missing or failed block becomes None with a finding and nothing else moves."""
    findings: List[str] = []
    starts = sorted(starts, key=lambda s: s.line)
    if mode == "bold" and any(s.kind != "cover" for s in starts):
        findings.append("bold mode: no # headings, titles identified from " "bold lines")

    cover: Dict[str, str] = {}
    sections: Dict[str, Optional[Block]] = {name: None for name in cfg.SECTIONS}
    signature: List[str] = []
    enclosures: List[Block] = []
    pages: Dict[str, Block] = {}
    glossary_preamble: Optional[Block] = None
    parts: List[Block] = []
    last_section: Optional[str] = None

    first = starts[0].line if starts else len(lines)
    unused = [l.strip() for l in lines[:first] if l.strip()]
    if unused:
        findings.append(
            "%d line(s) above the first recognised block not used: " "%s" % (len(unused), " | ".join(unused[:3]))
        )

    def leftover(text_lines: List[str]):
        """Lines after a fenced signature go back to the section around it,
        as a paragraph of their own"""
        if last_section is not None and sections[last_section] is not None:
            sections[last_section].lines.extend([""] + text_lines)

    # sections end at the signature, the ToC or the first enclosure; a section start after that is not a section
    # (usually the enclosure a section points at with "See Enclosure N")
    sections_end = min(
        [
            s.line
            for s in starts
            if s.kind in ("signature", "toc", "enclosure", "appendices", "glossary", "tables", "figures")
            or (s.kind == "section" and s.name == cfg.SIGNATURE_SECTION)
        ]
        or [len(lines)]
    )
    kept_starts = []
    for start in starts:
        if start.kind == "section" and start.name != cfg.SIGNATURE_SECTION and start.line >= sections_end:
            findings.append(
                "section %s at line %d comes after the sections end (line %d); "
                "ignored" % (start.name, start.line + 1, sections_end + 1)
            )
        else:
            kept_starts.append(start)
    starts = kept_starts

    for position, start in enumerate(starts):
        next_line = starts[position + 1].line if position + 1 < len(starts) else len(lines)
        stop = start.end if start.end is not None else next_line - 1
        body = lines[start.line + 1 : stop + 1]
        if start.inline:
            body = [start.inline] + body
        block = Block(start.name, body, start.line + 1)
        kind = start.kind

        if kind == "cover":
            value = [LIST_MARKER.sub("", l.strip()) for l in body if l.strip() and not RULE_LINE.match(l)]
            cover[start.name] = unescape("\n".join(value))
        elif kind == "signature" or (kind == "section" and start.name == cfg.SIGNATURE_SECTION):
            signature = signature_lines(body, findings)
            if start.end is not None:
                leftover(lines[start.end + 1 : next_line])
        elif kind == "section":
            if not start.matched:
                findings.append("UNMATCHED heading (kept): %s" % start.name)
                if last_section is not None and sections[last_section] is not None:
                    sections[last_section].lines.extend(["", "# " + start.name, ""] + body)
            elif sections[start.name] is not None:
                findings.append("DUPLICATE heading for section: %s" % start.name)
            else:
                sections[start.name] = block
                last_section = start.name
        elif kind == "toc":
            findings.append("TABLE OF CONTENTS block dropped; the table is " "generated")
        elif kind == "enclosure":
            placed = len(enclosures) + 1
            if start.number is not None and start.number != placed:
                findings.append(
                    "ENCLOSURE numbering: '%s' written as %d, " "placed as %d" % (start.name, start.number, placed)
                )
            if not any(l.strip() for l in body):
                findings.append("ENCLOSURE '%s' has no content" % start.name)
            enclosures.append(block)
        elif kind == "glossary":
            if glossary_preamble is not None:
                findings.append("DUPLICATE GLOSSARY block, second dropped")
            else:
                glossary_preamble = block
        elif kind == "glossary_part":
            parts.append(block)
        else:  # appendices, tables, figures
            name = kind.upper()
            if name in pages:
                findings.append("DUPLICATE %s block, second dropped" % name)
            else:
                pages[name] = block

    glossary = None
    if glossary_preamble is not None:
        abbreviations = definitions = None
        other: List[Block] = []
        for part in parts:
            key = normalize(part.title)
            if any(w in key for w in cfg.GLOSSARY_COLUMNS["keywords"]) and abbreviations is None:
                abbreviations = part
            elif any(w in key for w in cfg.GLOSSARY_DEFINITIONS["keywords"]) and definitions is None:
                definitions = part
            else:
                other.append(part)
        glossary = Glossary(glossary_preamble, abbreviations, definitions, other)
    elif parts:
        findings.append("%d glossary PART block(s) with no GLOSSARY title, " "not used" % len(parts))

    for name, block in sections.items():
        if block is None and name != cfg.SIGNATURE_SECTION:
            findings.append(
                "optional section not present: %s" % name
                if cfg.SECTIONS[name].optional
                else "MISSING required section: %s" % name
            )

    offset = 0
    if mode == "heading":
        levels = [
            len(HEADING_LINE.match(lines[s.line]).group(1))
            for s in starts
            if s.kind in ("enclosure", "appendices", "glossary", "tables", "figures")
        ]
        offset = (min(levels) if levels else 1) - 1
    return DlaiDocument(
        cover,
        sections,
        signature,
        enclosures,
        pages.get("APPENDICES"),
        glossary,
        pages.get("TABLES"),
        pages.get("FIGURES"),
        mode == "bold",
        offset,
        findings,
    )
```

### ADD (new) `signature_lines`  (near line 351)

```python
def signature_lines(body: List[str], findings: List[str]) -> List[str]:
    """The signature lines: fences and the marker stripped, the authored Enclosure(s) list dropped (it is regenerated)."""
    out: List[str] = []
    dropped = 0
    listing = False
    for line in body:
        if FENCE_LINE.match(line) or RULE_LINE.match(line) or not line.strip():
            continue
        if listing:
            dropped += 1
            continue
        if SIGNATURE_LINE.match(line):
            continue
        if ENCLOSURE_LIST_HEAD.match(line):
            listing = True
            continue
        out.append(unescape(line.strip()))
    findings.append("SIGNATURE BLOCK taken (%d line(s))" % len(out))
    if dropped:
        findings.append("authored Enclosure(s) list under the signature dropped (%d line(s)); the list is generated" % dropped)
    return out
```

---

## md_to_docx/template_processor.py

### REPLACE `normalize_lists`  (near line 185)

```python
def normalize_lists(lines: List[str]) -> List[str]:
    """Bold-mode body lines made safe for the parser: markers resolved, blanks between items dropped, prose flush left."""
    out: List[str] = []
    state: dict = {}
    for line in lines:
        if RULE_LINE.match(line):
            continue
        if not line.strip():
            out.append(line)
            continue
        resolved = resolve_marker(line, state)
        if resolved is not None:
            # blank lines between items carry nothing (styles set the spacing) and are half of the code-block trigger
            while state.get("in_list") and out and out[-1] == "":
                out.pop()
            state["in_list"] = True
            out.append(resolved)
            continue
        # prose after a blank line ends the list (next marker restarts at depth 0); without a blank it stays with the item
        if out and out[-1] == "":
            state["prev"] = -1
        state["in_list"] = False
        out.append(line.lstrip())
    return out
```

### REPLACE `body_nodes`  (near line 211)

```python
def body_nodes(block: Block, doc: DlaiDocument) -> list:
    """Parse one block's lines. Fence markers are always dropped (their lines render as text); bold-mode input is
    list-normalised first, # input is parsed as written since its bullets nest by indentation."""
    text_lines = ["" if FENCE_LINE.match(line) else line for line in block.lines]  # a fence marker becomes a paragraph break
    note = "code fence markers stripped in '%s'; the lines print as text" % (block.title or "cover")
    if text_lines != block.lines and note not in doc.findings:
        doc.findings.append(note)
    if doc.normalize:
        text_lines = normalize_lists(text_lines)
    nodes = logic.parse_markdown("\n".join(text_lines)).children
    check_code_blocks(nodes, block, doc.findings)
    return nodes
```

### REPLACE `write_signature_block`  (near line 455)

```python
def write_signature_block(document, titles: List[str], lines=None, findings: List[str] = None, glossary: bool = True):
    """Signature lines (config sig_lines when none were found), then the Enclosure(s) list, Glossary last."""
    back = cfg.BACK
    signature = lines or list(back["sig_lines"])
    if not signature and findings is not None:
        findings.append("SIGNATURE BLOCK not found; no signature lines printed")
    for line in signature:
        write(document, "signature", line)
    write(document, "encl_label", back["encl_label"])
    for index, title in enumerate(titles, start=1):
        write(document, "encl_item", back["encl_pattern"] % (index, title))
    if glossary:
        last = write(document, "encl_item", back["encl_last"])
        last.paragraph_format.first_line_indent = Inches(0)
```

### REPLACE `md_to_docx`  (near line 654)

```python
def md_to_docx(doc: DlaiDocument, doc_title: str = "PLACEHOLDER TITLE", template_name=None):
    """Render a DlaiDocument (from boundaries.build_document or the section
    agent) as a .docx. Returns (bytes, findings)."""
    findings = doc.findings
    opts = helpers.DocxOptions(body_font=cfg.BODY_FONT, body_size_pt=cfg.BODY_SIZE)
    document = WordDocument()
    numbering = helpers.Numbering(document)

    # 1. every ToC row and bookmark name, before anything is written
    entries = plan_toc(doc)
    bookmarks = [entry.bookmark for entry in entries]

    # 2. page setup, the Word styles, then the cover
    setup_page(document, doc_title)
    write_cover(document, numbering, doc_title, doc.cover, template_name)

    # 3. the required sections, in config order
    write_sections(document, opts, numbering, doc)

    # 4. signature block and table of contents
    write_signature_block(document, [b.title for b in doc.enclosures], doc.signature, findings)
    write_table_of_contents(document, entries)

    # 5. the enclosures, then whatever back matter the author supplied
    write_enclosures(document, opts, numbering, doc, bookmarks)
    write_back_matter(document, bookmarks, doc, opts, numbering)

    # 6. tell Word to refresh page numbers on open, then serialise to bytes
    helpers.update_fields_on_open(document)
    return helpers.document_to_bytes(document), findings
```

---

## main.py  (replace the whole file)

```python
"""python main.py input.md output.docx [--title T] [--template SOP] [--provider llm|regex] [--quiet]
Findings are logged on the "md_to_docx" logger, never printed; main() returns (docx_bytes, findings)."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent"), str(ROOT)]

from agent import llm_boundaries  # noqa: E402  md_section_agent
from boundaries import assemble, preprocess, regex_boundaries  # noqa: E402  md_to_docx
from template_processor import md_to_docx  # noqa: E402  md_to_docx

log = logging.getLogger("md_to_docx")


def main(markdown_path, out_path, title="PLACEHOLDER TITLE", template=None, provider="llm"):
    markdown = Path(markdown_path).read_text(encoding="utf-8")  # 1. read
    lines = preprocess(markdown)  # 2. line endings, tabs; nothing removed

    if provider == "llm":
        starts, mode, findings = llm_boundaries(lines)  # 3a. the model (falls back to the rules)
    else:
        starts, mode = regex_boundaries(lines)  # 3b. the rules only
        findings = []

    sections = assemble(lines, starts, mode)  # 4. starts -> DlaiDocument
    docx_bytes, more = md_to_docx(sections, title, template)  # 5. render
    findings += more

    Path(out_path).write_bytes(docx_bytes)  # 6. write
    findings.insert(0, "wrote %s (%d bytes) using the %s provider" % (out_path, len(docx_bytes), provider))
    for finding in findings:  # 7. report
        log.info(finding)
    return docx_bytes, findings


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("markdown")
    ap.add_argument("output")
    ap.add_argument("--title", default="PLACEHOLDER TITLE")
    ap.add_argument("--template", default=None, help="cover document type, e.g. SOP")
    ap.add_argument("--provider", default="llm", choices=("llm", "regex"))
    ap.add_argument("--quiet", action="store_true", help="do not echo the findings to the console")
    args = ap.parse_args()
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
        for noisy in ("openai", "httpx", "httpcore"):  # the client's own retry chatter; our findings say what happened
            logging.getLogger(noisy).setLevel(logging.WARNING)
    main(args.markdown, args.output, args.title, args.template, args.provider)
```

---

## Tests (optional): replace `md_to_docx/tests/check.py` with the copy in the zip; add `md_to_docx/tests/signature_after_lines.md`.
