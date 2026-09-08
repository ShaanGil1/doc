# Phase 1 edits, round 2 (after phase1_edits.md)
Each block replaces the whole definition of the same name, or adds it. What they fix: a document that mixes bold titles and `#` headings (your SOP 9999.62) now reads all of its titles, every body is list-normalised whatever the title style (no more code block from indented `a.` items), `-` bullets nest by indent, `&amp;` and friends are decoded.

---

## md_to_docx/rules.py

### ADD (new) `BULLET_LINE`  (near line 85)

```python
# "- text", "* text", "+ text": a bullet has no shape, so its depth comes from its indent relative to the first marker
BULLET_LINE = re.compile(r"^(?P<indent>[ \t]*)[-*+][ \t]+(?=\S)")
```

### REPLACE `DlaiDocument`  (near line 118)

```python
class DlaiDocument(NamedTuple):
    cover: Dict[str, str]  # opr / subject / references / effective
    sections: Dict[str, Optional[Block]]  # every name in cfg.SECTIONS
    signature: List[str]  # lines, [] when none was found
    enclosures: List[Block]
    appendices: Optional[Block]
    glossary: Optional[Glossary]
    tables: Optional[Block]
    figures: Optional[Block]
    normalize: bool  # always True now: every body is list-normalised
    # rewritten; # input is parsed raw
    offset: int  # heading level offset for # input
    findings: List[str]
```

---

## md_to_docx/boundaries.py

### DELETE `bold_starts` (its work moved into `title_starts`)

### DELETE `heading_starts` (its work moved into `title_starts`)

### ADD (new) `import html`  (near line 6)

```python
import html
```

### REPLACE `preprocess`  (near line 37)

```python
def preprocess(text: str) -> List[str]:
    """Line endings, BOM, leading tabs, __bold__ -> **bold**. Nothing is removed, so line numbers stay 1:1 with the
    input."""
    lines = html.unescape(text or "").lstrip("\ufeff").splitlines()  # "&amp;" -> "&" and friends
    return [UNDERSCORE_BOLD.sub(r"**\1**", indent_tabs(line)) for line in lines]
```

### REPLACE `regex_boundaries`  (near line 49)

```python
def regex_boundaries(lines: List[str]) -> Tuple[List[Start], str]:
    """Block starts from the deterministic rules, reading bold titles and # headings in one pass.
    Returns (starts, mode); mode is "heading" when the input has # headings (sub-heading levels are offset from the top)."""
    return title_starts(lines), ("heading" if top_heading_level(lines) else "bold")
```

### ADD (new) `top_heading_level`  (near line 55)

```python
def top_heading_level(lines: List[str]) -> int:
    """The shallowest # level outside fences, or 0 when there are no headings."""
    in_fence, levels = False, []
    for line in lines:
        if FENCE_LINE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            match = HEADING_LINE.match(line)
            if match:
                levels.append(len(match.group(1)))
    return min(levels) if levels else 0
```

### ADD (new) `title_starts`  (near line 68)

```python
def title_starts(lines: List[str]) -> List[Start]:
    """One pass over the lines. A title is a bold-only line, a numbered bold title (text after the colon allowed), a
    signature marker line or fence, or a # heading; each is classified by name the same way whichever style it uses."""
    starts: List[Start] = []
    fence: Optional[List[str]] = None
    fence_start = 0
    top = top_heading_level(lines)
    seen_section = past_sections = in_glossary = False

    def classify(name: str, numbered: bool, index: int, heading_level: int = 0):
        """Classify one title; returns True when it was consumed as a start."""
        nonlocal seen_section, past_sections, in_glossary
        key = normalize(name)
        canonical = SECTION_ALIASES.get(key)
        if canonical and not past_sections:
            starts.append(Start("section", canonical, index))
            seen_section = True
            return True
        if heading_level and heading_level != top and not (in_glossary and PART_TITLE.match(key)):
            return False  # a deeper heading is body: a sub-heading inside an enclosure
        enclosure = None if numbered else ENCLOSURE_TITLE.match(name)
        back = not numbered and (key in BACK_NAMES or (in_glossary and PART_TITLE.match(key)))
        toc = not numbered and key in TOC_NAMES
        if heading_level and not (enclosure or back or toc):
            enclosure_title, number = name, None  # any other top-level heading is an enclosure
        elif enclosure:
            enclosure_title, number = enclosure.group(2).strip(), enclosure.group(1)
        else:
            enclosure_title = None
        if enclosure_title is not None or back or toc:
            past_sections = True
            in_glossary = BACK_NAMES.get(key) == "GLOSSARY" or (in_glossary and bool(PART_TITLE.match(key)))
        if toc:
            starts.append(Start("toc", key, index))
        elif back:
            kind = BACK_NAMES.get(key)
            starts.append(Start(kind.lower() if kind else "glossary_part", name, index))
        elif enclosure_title is not None:
            starts.append(Start("enclosure", enclosure_title, index, number=int(number) if number else None))
        elif not heading_level and not past_sections and numbered:
            starts.append(Start("section", name.rstrip(": "), index, matched=False))  # unknown numbered bold title
            seen_section = True
        else:
            return False
        return True

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
        heading = HEADING_LINE.match(line)
        if heading:
            classify(heading.group(2).strip(), False, index, len(heading.group(1)))
            continue
        match = BOLD_TITLE.match(line.lstrip())
        if match:
            classify(match.group("name").strip(), bool(match.group("num") or match.group("inner")), index)
            continue
        # "4. **DEFINITIONS**: See Glossary." is a title with its body inline; numbered only, so a bold lead-in never is
        inline = BOLD_TITLE_INLINE.match(line.lstrip())
        canonical = SECTION_ALIASES.get(normalize(inline.group("name"))) if inline else None
        if canonical and not past_sections:
            starts.append(Start("section", canonical, index, inline=inline.group("rest").strip()))
            seen_section = True
    return starts
```

### REPLACE `assemble`  (near line 170)

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

    offset = (top_heading_level(lines) or 1) - 1 if mode == "heading" else 0
    return DlaiDocument(
        cover,
        sections,
        signature,
        enclosures,
        pages.get("APPENDICES"),
        glossary,
        pages.get("TABLES"),
        pages.get("FIGURES"),
        True,  # every body is list-normalised; a # heading anywhere no longer switches that off
        offset,
        findings,
    )
```

---

## md_to_docx/template_processor.py

### REPLACE `imports from rules`  (near line 17)

```python
from rules import (
    FENCE_LINE,
    GLOSSARY_ENTRY,
    HEADING_LINE,
    BULLET_LINE,
    LIST_MARKER,
    MARKER_DEPTH,
    RULE_LINE,
    SECTION_ALIASES,
    Block,
    ConversionError,
    DlaiDocument,
    normalize,
)
```

### REPLACE `resolve_marker`  (near line 169)

```python
def resolve_marker(line: str, state: dict) -> Optional[str]:
    """Rewrite a list line as "1." at the depth its marker implies. Shaped markers (1. a. (1) (a)) read their depth from
    the shape relative to the first marker in the body; bullets read it from their indent. Nothing can skip a level."""
    match = LIST_MARKER.match(line)
    bullet = None if match else BULLET_LINE.match(line)
    if not match and not bullet:
        return None
    indent = len(line[: len(line) - len(line.lstrip())].expandtabs(4))
    if "base_indent" not in state:
        state["base_indent"] = indent
    if match:
        shape = next(name for name, value in match.groupdict().items() if value)
        level = MARKER_DEPTH[shape]
        depths = state.setdefault("depths", {})  # shape level -> depth
        if level not in depths:
            first = min(depths) if depths else level
            depths[level] = min(max(0, level - first), state.get("prev", -1) + 1)
        depth = depths[level]
        rest = line[match.end() :]
    else:
        wanted = max(0, indent - state["base_indent"]) // 2  # two spaces per level, as bullets are usually written
        depth = min(wanted, state.get("prev", -1) + 1)
        rest = line[bullet.end() :]
    state["prev"] = depth
    return "    " * depth + "1. " + rest
```

---

## Tests: replace `md_to_docx/tests/check.py` with the copy in the zip; add `md_to_docx/tests/mixed_headings.md`.
