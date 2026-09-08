# Phase 1 edits, round 3 (after phase1_edits_2.md)
Hardening of the mixed-title reading from a set of variant documents. Each block replaces the whole definition of the same name, or adds it. Also one block in the agent (`title_inline`).

---

## md_to_docx/rules.py

### REPLACE `HEADING_LINE`  (near line 61)

```python
HEADING_LINE = re.compile(r"^\s*(#{1,6})\s+(.*?)\s*#*\s*$")  # any indent; closing #s ignored
```

---

## md_to_docx/boundaries.py

### ADD (new) `import re`  (near line 7)

```python
import re
```

### REPLACE `imports from rules`  (near line 11)

```python
from rules import (
    BACK_NAMES,
    MARKUP,
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

### ADD (new) `plain_title`  (near line 70)

```python
def plain_title(line: str) -> str:
    """A title line as bare text: no #, no **, no list number."""
    text = HEADING_LINE.sub(lambda m: m.group(2), line.strip())
    return MARKUP.sub("", re.sub(r"^\d+[.)]\s+", "", text)).strip().rstrip(":").strip()
```

### ADD (new) `last_section_line`  (near line 76)

```python
def last_section_line(lines: List[str]) -> int:
    """Index of the last line that is a known section title in any style; the sections zone ends there (-1 if none)."""
    last = -1
    for index, line in enumerate(lines):
        text = line.strip()
        heading = HEADING_LINE.match(text)
        bold = BOLD_TITLE.match(text) or BOLD_TITLE_INLINE.match(text)
        name = heading.group(2) if heading else (bold.group("name") if bold else "")
        if name and (normalize(name) in SECTION_ALIASES or normalize(name.partition(":")[0]) in SECTION_ALIASES):
            last = index
    return last
```

### REPLACE `title_starts`  (near line 89)

```python
def title_starts(lines: List[str]) -> List[Start]:
    """One pass over the lines. A title is a bold-only line, a numbered bold title (text after the colon allowed), a
    signature marker line or fence, or a # heading; each is classified by name the same way whichever style it uses."""
    starts: List[Start] = []
    fence: Optional[List[str]] = None
    fence_start = 0
    top = top_heading_level(lines)
    last_section = last_section_line(lines)
    prefixed = any(ENCLOSURE_TITLE.match(plain_title(line)) for line in lines)  # the document names its enclosures
    seen_section = past_sections = in_glossary = False

    def classify(name: str, numbered: bool, index: int, heading_level: int = 0):
        """Classify one title; returns True when it was consumed as a start."""
        nonlocal seen_section, past_sections, in_glossary
        key = normalize(name)
        canonical = SECTION_ALIASES.get(key)
        inline = ""
        if not canonical and heading_level and ":" in name:  # "# DEFINITIONS: See Glossary." has its body on the line
            head, _, rest = name.partition(":")
            canonical, inline = SECTION_ALIASES.get(normalize(head)), rest.strip()
        if canonical and not past_sections:
            starts.append(Start("section", canonical, index, inline=inline))
            seen_section = True
            return True
        enclosure = None if numbered else ENCLOSURE_TITLE.match(name)
        back = not numbered and (key in BACK_NAMES or (in_glossary and PART_TITLE.match(key)))
        toc = not numbered and key in TOC_NAMES
        if heading_level and heading_level != top and not (enclosure or back or toc):
            return False  # a deeper heading with no known name is body: a sub-heading inside an enclosure
        if heading_level and not seen_section and not past_sections and not (enclosure or back or toc):
            return False  # an unknown heading above the first section is cover-region text, not an enclosure
        if heading_level and not (enclosure or back or toc):
            if index < last_section or prefixed:
                return False  # body: before the sections end, or a sub-heading in a document that names its enclosures
            enclosure_title, number = name, None  # legacy style: an unprefixed top-level heading after the sections
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

---

## md_section_agent/agent.py

### REPLACE `imports from rules`  (near line 25)

```python
from rules import (  # noqa: E402
    BOLD_FIELD_LINE,
    SECTION_ALIASES,
    BOLD_TITLE,
    BOLD_TITLE_INLINE,
    ENCLOSURE_TITLE,
    FENCE_LINE,
    HEADING_LINE,
    MARKUP,
    SIGNATURE_LINE,
    DlaiDocument,
    Start,
    normalize,
)
```

### REPLACE `title_inline`  (near line 627)

```python
def title_inline(line: str) -> str:
    """Body text sitting on the title line, after the title"""
    inline = BOLD_TITLE_INLINE.match(line.lstrip())
    if inline:
        return inline.group("rest").strip()
    heading = HEADING_LINE.match(line)
    if heading and ":" in heading.group(2):  # "# DEFINITIONS: See Glossary."
        head, _, rest = heading.group(2).partition(":")
        return rest.strip() if normalize(head) in SECTION_ALIASES else ""
    field = BOLD_FIELD_LINE.match(line.strip())
    return field.group(2).strip() if field else ""
```

---

## Tests: replace `md_to_docx/tests/check.py` with the copy in the zip (45 checks).
