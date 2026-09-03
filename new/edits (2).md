# DLAI pipeline edits, round 2 (everything since the 25-block file)

Starting point: the build_dlai layout file fully applied. Every block below is the complete final text of the thing it names. If you already did an item from the chat, compare and move on. Files in the order you would walk them top to bottom; no `dlai.` prefixes anywhere.

Covers: sections off the navigation pane, Appendices centered, no break after the cover, section breaks instead of page breaks with the black square gone, `write_cover` reading the authored references, the two-column glossary, and list depth read from the marker shape instead of the author's indentation.


---

## config.py

### 1. `section` style: no Heading base

**Where:** `STYLES`, the `"section"` entry  
**Action:** replace the entry (drops `base="Heading 3"`, so sections leave the navigation pane)

```python
    # Normal, not a Heading base: the required sections are numbered body
    # paragraphs, not outline headings, so they stay out of the navigation
    # pane and never pick up keep-with-next
    "section":     Style("DLAI Section", caps=True, underline=True,
                         before=24.0, numbered=True, indent=True, suffix=":"),
```

### 2. `glossary_entry` style (new)

**Where:** `STYLES`, right after the `"glossary_part"` entry  
**Action:** insert

```python
    # one abbreviation row: term, tab, meaning. Column and grouping come from
    # GLOSSARY_COLUMNS, applied per paragraph
    "glossary_entry": Style("DLAI Glossary Entry", after=0.0),
```

### 3. `appendices` style: centered

**Where:** `STYLES`, the `"appendices"` entry  
**Action:** replace the entry (adds `align=CENTER`)

```python
    "appendices":  Style("DLAI Appendices", base="Heading 2", caps=True,
                         underline=True, align=CENTER, after=GAP,
                         page_break=True, suffix=":"),
```

### 4. no break after the cover

**Where:** `PAGE`, the `"break_after_cover"` entry  
**Action:** change `True` to `False` so PURPOSE follows the references on the cover page

```python
    "break_after_cover": False,
```

### 5. `GLOSSARY_COLUMNS` (new)

**Where:** module level, right above `BACK_MATTER`  
**Action:** insert

```python
# PART I of the glossary is two columns: the abbreviation, a tab, and its
# meaning starting at column_in (2.0 = four default tab stops), with wrapped
# lines aligned under the meaning. Rows are sorted by abbreviation, one blank
# line between initial letters, none within a letter. Applies to any glossary
# part whose title contains one of the keywords; other parts are
# "Term: definition" lines
GLOSSARY_COLUMNS = {"keywords": ("ABBREVIATION", "ACRONYM"),
                    "column_in": 2.0, "group_gap_pt": GAP}
```


---

## helpers.py

### 6. `define_style`

**Where:** module level  
**Action:** replace the whole function (two new keyword arguments, `keep_with_next` and `keep_together`, applied at the end of the paragraph block; this is what removes the black square while keeping the Heading bases)

```python
def define_style(document, style_name: str, based_on: Optional[str] = None,
                 character: bool = False, font=None, size_pt=None, color=None,
                 bold=None, italic=None, underline=None, all_caps=None,
                 align=None, space_before_pt=None, space_after_pt=None,
                 line_spacing=None, keep_with_next=None, keep_together=None):
    """Create or update a named style and return it.

    Putting formatting on a STYLE rather than on each paragraph is what lets
    someone open the .docx in Word, edit the style once, and restyle every
    paragraph using it. It also fixes list numbering for free: Word draws an
    auto-number from the paragraph mark, which inherits from the style, so a
    style that says black gives a black "1." with nothing done per paragraph.

    Anything left as None is inherited from the based_on style"""
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import RGBColor

    wanted_type = (WD_STYLE_TYPE.CHARACTER if character
                   else WD_STYLE_TYPE.PARAGRAPH)
    try:
        style = document.styles[style_name]
    except KeyError:
        style = document.styles.add_style(style_name, wanted_type)

    if based_on:
        try:
            style.base_style = document.styles[based_on]
        except KeyError:
            pass

    if font:
        style.font.name = font
        replace_element(style.element.get_or_add_rPr(), "w:rFonts", parse_xml(
            '<w:rFonts %s w:ascii="%s" w:hAnsi="%s" w:cs="%s" w:eastAsia="%s"/>'
            % ((nsdecls("w"),) + (font,) * 4)))
    if size_pt is not None:
        style.font.size = Pt(size_pt)
    if color is not None:
        style.font.color.rgb = RGBColor.from_string(color)
    # Written even when False. None means "inherit", which is how a built-in
    # style's bold and colour leak into anything based on it
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    if underline is not None:
        style.font.underline = underline
    if all_caps is not None:
        style.font.all_caps = all_caps

    if not character:
        paragraph_format = style.paragraph_format
        if align is not None:
            paragraph_format.alignment = align
        if space_before_pt is not None:
            paragraph_format.space_before = Pt(space_before_pt)
        if space_after_pt is not None:
            paragraph_format.space_after = Pt(space_after_pt)
        if line_spacing is not None:
            paragraph_format.line_spacing = line_spacing
        # Written even when False: a Heading base carries keep-with-next and
        # keep-together, and either one makes Word show a black square beside
        # the paragraph when formatting marks are on
        if keep_with_next is not None:
            paragraph_format.keep_with_next = keep_with_next
        if keep_together is not None:
            paragraph_format.keep_together = keep_together
    return style
```


---

## dlai.py

### 7. import

**Where:** the import block, next to `from docx.shared import Inches, Pt`  
**Action:** add one line

```python
from docx.enum.section import WD_SECTION
```

### 8. `create_styles`

**Where:** section 1, RENDERING  
**Action:** replace the whole function (the `define_style` call passes `keep_with_next=False, keep_together=False`)

```python
def create_styles(document):
    """Turn every entry in config.STYLES into a real Word style"""
    for spec in cfg.STYLES.values():
        helpers.define_style(
            document, spec.name, based_on=spec.base, font=spec.font,
            size_pt=spec.size, color=spec.color, bold=spec.bold,
            italic=spec.italic, all_caps=spec.caps,
            align=spec.align, space_before_pt=spec.before,
            space_after_pt=spec.after, line_spacing=spec.line,
            keep_with_next=False, keep_together=False)
    # Runs that need underlining inside an otherwise plain paragraph, which is
    # every lead-in title. A character style keeps it reviewer editable
    helpers.define_style(document, cfg.UNDERLINE_STYLE, character=True,
                         underline=True)
```

### 9. `write`

**Where:** section 1  
**Action:** replace the whole function (the `page_break` check moved above `add_paragraph` and now calls `new_page`; the `page_break_before` line is gone)

```python
def write(document, key: str, text: str = "", level: int = 0,
          lead_in: str = "", num_id: int = 0):
    """One paragraph in the named style. `lead_in` is an underlined title
    opening the paragraph, with `text` as the prose that follows it"""
    spec = cfg.STYLES[key]
    if spec.page_break:
        new_page(document)
    paragraph = document.add_paragraph(style=spec.name)
    paragraph_format = paragraph.paragraph_format

    if spec.first_line:
        paragraph_format.first_line_indent = Inches(spec.first_line)
    if spec.indent:
        paragraph_format.left_indent = Inches(cfg.INDENT_STEP_IN * (level + 1))
        paragraph_format.first_line_indent = Inches(-cfg.INDENT_STEP_IN)

    if lead_in:
        run = paragraph.add_run(lead_in + ":")
        run.style = document.styles[cfg.UNDERLINE_STYLE]
        if text:
            paragraph.add_run(" ")
    if text:
        run = paragraph.add_run(text + ("" if lead_in else spec.suffix))
        # Underline goes on the RUN, not the paragraph style. The auto-number
        # inherits the paragraph style, so underlining there would underline
        # the "1." too
        if spec.underline and not lead_in:
            run.style = document.styles[cfg.UNDERLINE_STYLE]

    if spec.numbered and num_id:
        helpers.Numbering.apply_to_paragraph(paragraph, num_id, level)
    return paragraph
```

### 10. `new_page` (new)

**Where:** right after `write`, before `write_image`  
**Action:** insert

```python
def new_page(document):
    """Start the next paragraph on a new page with a next-page section break,
    which is what the template uses. Header, footer and page numbering carry
    on from the previous section. Not the "page break before" paragraph
    property: that one makes Word show a black square beside the paragraph
    whenever formatting marks are on"""
    document.add_section(WD_SECTION.NEW_PAGE)
```

### 11. `paragraph_lines`, `GLOSSARY_ENTRY`, `glossary_entry` (new)

**Where:** section 2, right after `heading_level`  
**Action:** insert the whole block

```python
def paragraph_lines(node) -> List[str]:
    """The paragraph's source lines, split at soft and hard breaks, with the
    spaces inside each line intact. Markdown folds consecutive lines into one
    paragraph; a two-column glossary needs them back one per row"""
    inline = logic.find_inline_child(node)
    lines, current = [], []
    for child in (inline.children if inline is not None else []):
        if child.type in ("softbreak", "hardbreak"):
            lines.append("".join(current))
            current = []
        elif child.children:
            spans: list = []
            logic.collect_spans(child, {}, spans)
            current.append(logic.spans_text(spans))
        else:
            current.append(child.content or "")
    lines.append("".join(current))
    return [line.strip() for line in lines if line.strip()]


# "FSA        Financial Services Activity", "FSA\tFinancial ...", "FSA: Financial ..."
GLOSSARY_ENTRY = re.compile(
    r"^(?P<term>[^\s\[:][^:\t]*?)(?:\t+|\s{2,}|:\s+)(?P<text>\S.*)$")


def glossary_entry(line: str):
    """(term, meaning) for a two-column glossary row, else None. The term ends
    at the first tab, run of two or more spaces, or colon. A bracketed
    placeholder is never a row"""
    match = GLOSSARY_ENTRY.match(line)
    return (match.group("term").strip(), match.group("text").strip()) if match else None
```

### 12. `LIST_MARKER` and `MARKER_DEPTH`

**Where:** the regex block above `promote_bold_titles`, where `LETTER_MARKER` was  
**Action:** delete the `LETTER_MARKER` line and put this in its place

Anchored to the start of the line, only whitespace allowed before the marker, at least one space after it, then text. Letters are lowercase only, so `A. Smith wrote this` is not an item.

```python
# "1. text", "a. text", "(1) text", "(a) text". Markdown only knows the first,
# and the depth is read from the shape, not the indent: the cascade order is
# fixed, so "a." is always one level under "1." however the author indented it.
# Letters are lowercase only, as the cascade is, so a sentence opening
# "A. Smith ..." is not an item
LIST_MARKER = re.compile(
    r"^\s*(?:(?P<number>\d+)[.)]|(?P<letter>[a-z])[.)]"
    r"|\((?P<pnumber>\d+)\)|\((?P<pletter>[a-z])\))\s+(?=\S)")
MARKER_DEPTH = {"number": 0, "letter": 1, "pnumber": 2, "pletter": 3}
```

### 13. `resolve_marker` (new)

**Where:** right above `promote_bold_titles`  
**Action:** insert

```python
def resolve_marker(line: str, base: int) -> Optional[str]:
    """Rewrite a list line so markdown nests it at the depth its marker shape
    says. `base` is the cascade level of the top of this body: 1 inside a
    required section (its "1." was the title, so "a." is the first level),
    0 inside an enclosure. Returns None for a line that is not a list item"""
    match = LIST_MARKER.match(line)
    if not match:
        return None
    shape = next(name for name, value in match.groupdict().items() if value)
    depth = max(0, MARKER_DEPTH[shape] - base)
    return "    " * depth + "1. " + line[match.end():]
```

### 14. `promote_bold_titles`

**Where:** section 2  
**Action:** replace the whole function (the `indent` bookkeeping is gone; list lines are re-indented from their marker shape by `resolve_marker`, every other body line is flush left)

```python
def promote_bold_titles(markdown_text: str):
    """For input with no # headings: find the bold title lines and rewrite
    them as # headings, split into (sections, enclosures, findings).

    A title is a bold line at column 0 and nothing else. Before the first
    enclosure it is a required section, list number optional and matched by
    name; a numbered bold line matching nothing is still emitted so
    split_sections reports it. An enclosure must read "Enclosure N: name",
    since a bare bold line would match any bold word; the prefix is stripped.
    APPENDICES, GLOSSARY with its PART lines, TABLES and FIGURES are back
    matter and go with the enclosures for outline to peel off. Past the first
    enclosure or back matter title a numbered bold line is body text, because
    enclosure bodies use that shape for their own items.

    Along the way: an authored TABLE OF CONTENTS block is dropped, --- lines
    go, list markers are rewritten as "1." at the depth their shape implies
    (1. -> a. -> (1) -> (a)) whatever the author indented, so markdown nests
    them and the cascade relabels them, and a fenced block naming the
    signature block becomes a # SIGNATURE BLOCK section for take_section.

    Returns None when the text already has a # heading, or no title at all"""
    lines = [line.expandtabs(4) for line in (markdown_text or "").splitlines()]
    if any(HEADING_LINE.match(line) for line in lines):
        return None
    sections, enclosures, findings = [], [], []
    out, fence, count, titles = sections, None, 0, 0
    dropping = in_glossary = False

    for line in lines:
        if fence is not None:
            fence.append(line)
            if FENCE_LINE.match(line):
                body = [l.strip() for l in fence[1:-1] if l.strip()]
                if body and SIGNATURE_MARK.search(body[0]):
                    # always a section, wherever the author put the fence
                    sections.extend(["", "# " + cfg.SIGNATURE_SECTION, ""]
                                    + body[1:] + [""])
                    findings.append("SIGNATURE BLOCK taken from the fenced "
                                    "block (%d line(s))" % (len(body) - 1))
                elif not dropping:
                    out.extend(fence)
                fence = None
            continue
        if FENCE_LINE.match(line):
            fence = [line]
            continue
        if RULE_LINE.match(line):
            continue

        match = BOLD_TITLE.match(line)
        if match:
            name = match.group("name").strip()
            key = normalize(name)
            numbered = bool(match.group("num") or match.group("inner"))
            enclosure = None if numbered else ENCLOSURE_TITLE.match(name)
            back = not numbered and (key in BACK_NAMES or
                                     (in_glossary and PART_TITLE.match(key)))
            toc = not numbered and key in TOC_NAMES
            if enclosure:
                count += 1
                written = int(enclosure.group(1) or count)
                if written != count:
                    findings.append("ENCLOSURE numbering: '%s' written as %d, "
                                    "placed as %d" % (name, written, count))
                name = enclosure.group(2).strip()
            if enclosure or back or toc:
                out = enclosures
                # PART lines only mean something between GLOSSARY and the
                # next enclosure or back matter title
                in_glossary = BACK_NAMES.get(key) == "GLOSSARY" or (
                    in_glossary and bool(PART_TITLE.match(key)))
            if toc:
                dropping = True
                findings.append("TABLE OF CONTENTS block dropped; the table "
                                "is generated")
                continue
            if enclosure or back or (out is sections and
                                     (numbered or key in SECTION_ALIASES)):
                out.extend(["", "# " + name, ""])
                dropping, titles = False, titles + 1
                continue
        if dropping:
            continue
        if not line.strip():
            out.append(line)
            continue
        # A list line is re-indented from its marker shape; any other body
        # line loses its indent, so an indented paragraph under a title is
        # never read as a code block. Hard-break continuations still join
        # the item above them at any indent
        resolved = resolve_marker(line, 1 if out is sections else 0)
        out.append(resolved if resolved is not None else line.lstrip())

    if fence is not None:            # never closed: keep it rather than lose it
        out.extend(fence)
    if not titles:
        return None
    findings.insert(0, "bold mode: no # headings, titles identified from "
                       "bold lines")
    return "\n".join(sections), "\n".join(enclosures), findings
```

### 15. `write_cover`

**Where:** section 4, THE HARDCODED SHELL  
**Action:** replace the whole function (your `template_type` argument, `dict(cfg.COVER)` so the override does not stick, and the `supplied` references logic that reads `fields["references"]`)

```python
def write_cover(document, numbering, doc_title: str, fields=None,
                template_type=None):
    """`fields` comes from split_cover. Anything absent falls back to the
    placeholder in config, so the cover still builds from nothing"""
    cover, fields = dict(cfg.COVER), fields or {}
    if template_type:
        cover["doc_type"] = template_type
    for path, _, _ in (cover["seal"], cover["rule"]):
        if not Path(path).is_file():
            raise FileNotFoundError(
                "Cover image missing: %s\nThe assets folder must sit next to "
                "config.py." % path)
    write_image(document, *cover["seal"])
    write(document, "agency", cover["agency_name"])
    write(document, "doc_type", cover["doc_type"])
    write(document, "cover_line", doc_title)
    effective = " ".join((fields.get("effective") or "").split())
    write(document, "cover_line",
          cover["effective_pattern"] % effective if effective
          else cover["effective_text"])
    write_image(document, *cover["rule"], key="agency")

    for index, (text, key) in enumerate(cover["labels"]):
        paragraph = write(document, "cover_label", text)
        value = " ".join((fields.get(key) or "").split()) if key else ""
        if value:
            # a plain run, so the label stays underlined and the value does not
            paragraph.add_run(value)
        if index == 0:
            paragraph.paragraph_format.space_before = Pt(
                cover["label_space_before_pt"])

    # one reference per line or per semicolon, falling back to placeholders
    supplied = [r.strip() for r in
                fields.get("references", "").replace(";", "\n").splitlines()
                if r.strip()]
    entries = supplied or [cover["ref_pattern"] % i
                           for i in range(1, cover["ref_count"] + 1)]

    num_id = new_cascade_list(numbering, cover["ref_cascade"])
    for index, entry in enumerate(entries, start=1):
        paragraph = write(document, "cover_ref", entry, num_id=num_id)
        paragraph_format = paragraph.paragraph_format
        paragraph_format.left_indent = Inches(cover["ref_indent_in"])
        paragraph_format.first_line_indent = Inches(-cfg.INDENT_STEP_IN)
        if index == len(entries):
            paragraph_format.space_after = Pt(cfg.GAP)
```

### 16. `write_glossary_columns` and `is_column_part` (new)

**Where:** section 4, right before `write_back_matter`  
**Action:** insert

```python
def write_glossary_columns(document, body, authored: bool, opts, numbering):
    """PART I rows: term, tab, meaning, sorted, grouped by initial letter.

    `body` is the authored [nodes] or the config tuple of strings. Lines that
    are not term/meaning pairs (a placeholder, say) print flush left after the
    rows; any block that is not a paragraph (a table) goes through DlaiWriter
    after that"""
    columns = cfg.GLOSSARY_COLUMNS
    lines, blocks = [], []
    if authored:
        for node in body:
            (lines.extend(paragraph_lines(node)) if node.type == "paragraph"
             else blocks.append(node))
    else:
        lines = list(body)

    rows, leftovers = [], []
    for line in lines:
        entry = glossary_entry(line)
        (rows if entry else leftovers).append(entry or line)
    rows.sort(key=lambda row: row[0].upper())

    previous = None
    for term, meaning in rows:
        initial = term[:1].upper()
        paragraph = write(document, "glossary_entry")
        fmt = paragraph.paragraph_format
        fmt.left_indent = Inches(columns["column_in"])
        fmt.first_line_indent = Inches(-columns["column_in"])
        fmt.tab_stops.add_tab_stop(Inches(columns["column_in"]))
        if previous is not None and initial != previous:
            fmt.space_before = Pt(columns["group_gap_pt"])
        paragraph.add_run(term)
        paragraph.add_run("\t")
        paragraph.add_run(meaning)
        previous = initial

    for line in leftovers:
        write(document, "flat", line)
    if blocks:
        DlaiWriter(document, opts, numbering, new_cascade_list(numbering),
                   base_level=-1, min_level=0, blocks=("subsection",),
                   body_key="flat", lead_key="definition"
                   ).write_blocks(blocks, logic.Position())


def is_column_part(title: str) -> bool:
    key = normalize(title)
    return any(word in key for word in cfg.GLOSSARY_COLUMNS["keywords"])
```

### 17. `write_back_matter`

**Where:** section 4  
**Action:** replace the whole function (new first branch routes ABBREVIATIONS/ACRONYMS parts to the two-column writer)

```python
def write_back_matter(document, bookmarks: List[str], back: BackMatter,
                      opts, numbering):
    """Appendices, the glossary with its parts, then tables and figures.

    Which pages exist comes from back_matter_plan. Config entries are written
    as "Term: definition" lines; authored content goes through DlaiWriter
    flush left and unnumbered, with lead-in titles underlined"""
    for part in back_matter_plan(back):
        paragraph = write(document, part.key, part.title)
        helpers.add_bookmark(paragraph, bookmarks.pop(0))
        if part.key == "glossary_part" and is_column_part(part.title):
            write_glossary_columns(document, part.body, part.authored,
                                   opts, numbering)
        elif not part.authored:
            for entry in part.body:
                lead_in, rest = split_lead_in(entry)
                write(document, "definition", rest, lead_in=lead_in)
        elif part.body:
            DlaiWriter(document, opts, numbering, new_cascade_list(numbering),
                       base_level=-1, min_level=0, blocks=("subsection",),
                       body_key="flat", lead_key="definition"
                       ).write_blocks(part.body, logic.Position())
```

### 18. `write_required_sections`

**Where:** section 5, ASSEMBLY  
**Action:** replace the whole function (`new_page` before the first section's `write`, only when `break_after_cover` is on; the old `page_break_before` lines are gone)

```python
def write_required_sections(document, opts, numbering, sections_input: str):
    """Write the numbered sections. Returns (findings, signature lines).

    The signature section is matched like any other, so it is never mistaken
    for an enclosure, but it is not printed here. Its lines are handed back for
    write_signature_block to place further down the page.
    """
    # taken from the raw text so its line breaks survive
    sections_input, signature = take_section(sections_input,
                                             cfg.SIGNATURE_SECTION)
    slots, findings = split_sections(sections_input)
    slots.pop(cfg.SIGNATURE_SECTION, None)
    findings = [f for f in findings if cfg.SIGNATURE_SECTION not in f]
    num_id = new_cascade_list(numbering)

    for index, (name, nodes) in enumerate(slots.items()):
        if index == 0 and cfg.PAGE["break_after_cover"]:
            new_page(document)
        paragraph = write(document, "section", name, num_id=num_id)
        if not nodes:
            write(document, "prose", cfg.MISSING_PLACEHOLDER,
                  level=1, num_id=num_id)
            continue
        # DEFINITIONS is the one section that sits flush left and unnumbered:
        # "Term: definition" lines underlined, anything else plain
        flat = name in cfg.FLAT_SECTIONS
        DlaiWriter(document, opts, numbering, num_id, base_level=0,
                   min_level=1, blocks=("subsection",),
                   body_key="flat" if flat else "prose",
                   lead_key="definition" if flat else "subsection"
                   ).write_blocks(nodes, logic.Position())
    return findings, signature
```


---

## Not changed

`build_dlai`, `write_enclosures`, `write_signature_block`, `write_table_of_contents`, `outline`, `back_matter_plan`, `split_cover`, `take_section`, `DlaiWriter` and all of `logic.py` are as they were in the 25-block file.

## After pasting

- SOP string: `1. PURPOSE:` directly under References on page 1; 11 pages; PROCEDURES as a. Overview / a. Description with (1) to (5) under it / a. Inputs/Outputs with (1) (2); Enclosure 3 as 1. / a. / a. / 2. / a. / a. / 3.; PART I as two columns (DLA, FSA, then the placeholder); findings `bold mode`, `SIGNATURE BLOCK taken`, `TABLE OF CONTENTS block dropped`, MISSING POLICY.
- The same string with every sub-item indented four spaces, or none at all, or two, gives the identical document.
- demo.md: three MISSING (INFORMATION REQUIREMENTS, INTERNAL CONTROLS, EXPIRATION DATE), validator clean, config glossary PART I now two columns (DLA, DLAI, OPR, SOP).
- With formatting marks on: `Section Break (Next Page)` before the ToC, each enclosure, Appendices and Glossary; no black squares anywhere.
