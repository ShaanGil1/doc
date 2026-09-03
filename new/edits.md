# DLAI pipeline edits, copy-paste form

Every block below is the complete final text of the thing it names. Replace the whole method or entry with the block, or insert it where the **Where** line says. Files are in the order you would walk them top to bottom. Nothing is abbreviated; each block compiles as shown.


---

## config.py

### 1. `enclosure` style gets an underline

**Where:** `STYLES`, the `"enclosure"` entry  
**Action:** replace the entry

```python
    "enclosure":   Style("DLAI Enclosure Heading", base="Heading 2", caps=True,
                         underline=True, align=CENTER, after=24.0,
                         page_break=True),
```

### 2. two new styles: `appendices` and `flat`

**Where:** `STYLES`, right after the `"glossary_part"` entry, before the closing `}`  
**Action:** insert

```python
    # ---- appendices ---------------------------------------------------------
    # its own page, reading "APPENDICES:" with the body below it
    "appendices":  Style("DLAI Appendices", base="Heading 2", caps=True,
                         underline=True, after=GAP, page_break=True,
                         suffix=":"),
    # authored back matter prose: flush left, unnumbered, no suffix
    "flat":        Style("DLAI Flat", before=GAP),
```

### 3. `CASCADE_REPEAT_UNDERLINE` flag

**Where:** right after `CASCADE = (...)`, before `INDENT_STEP_IN`  
**Action:** replace the `CASCADE` comment and tuple with this (adds the flag)

```python
# Markers repeat to fill Word's 9 levels: 1. -> a. -> (1) -> (a) -> 1. ...
# The second time round, the marker itself is underlined, so level five reads
# as an underlined 1. and level six as an underlined a.
CASCADE = (("decimal", "{}."), ("lowerLetter", "{}."),
           ("decimal", "({})"), ("lowerLetter", "({})"))
CASCADE_REPEAT_UNDERLINE = True
```

### 4. `EXPIRATION DATE` is required, and the placeholder wording

**Where:** `REQUIRED_SECTIONS`, after `"INTERNAL CONTROLS"`, and `MISSING_PLACEHOLDER` just below the dict  
**Action:** insert the one line into the dict; replace the `MISSING_PLACEHOLDER` line

```python
    "EXPIRATION DATE": ("EXPIRATION", "EXPIRATION DATES"),

MISSING_PLACEHOLDER = "section not found"
```

### 5. ToC row for appendices and its title

**Where:** `BACK`, the `"toc_levels"` entry  
**Action:** replace the `toc_levels` entry and add `appendices_title` right after it

```python
    "toc_levels": (("enclosure", 1), ("encl_h2", 2), ("encl_h3", 3),
                   ("glossary_part", 2), ("appendices", 1)),
    "appendices_title": "Appendices",
```

### 6. remove `trailing_lists`, add `BACK_MATTER` and `TOC_TITLES`

**Where:** delete the `"trailing_lists"` entry from `BACK` (the last entry in the dict). Then after the closing `}` of `BACK`, at the end of the file  
**Action:** append

```python
# Back matter titles, name -> extra spellings. Only the pages the author wrote
# are written, apart from GLOSSARY which falls back to BACK["glossary_parts"].
# Written in this order after the enclosures
BACK_MATTER = {
    "APPENDICES": ("APPENDIX",),
    "GLOSSARY": (),
    "TABLES": ("TABLE", "TABLE(S)"),
    "FIGURES": ("FIGURE", "FIGURE(S)"),
}
# An authored table of contents is dropped; the pipeline generates its own
TOC_TITLES = ("TABLE OF CONTENTS", "CONTENTS")
```


---

## helpers.py

All three are methods of `class Numbering`. Each gains the `underline_repeat` keyword; only `build_level_definition` does anything with it.

### 7. `Numbering.create_list`

**Where:** `class Numbering`  
**Action:** replace the whole method

```python
    def create_list(self, is_ordered: bool, start_number: int = 1,
                    cascade=None, suffix: Optional[str] = None,
                    underline_repeat: bool = False) -> int:
        """Return a numId for a brand new list.

        cascade replaces the 1./a./i. marker sequence for this list only.
        suffix is what separates marker from text: 'tab', 'space' or 'nothing'.
        Leaving it None omits the element, which is Word's own default of tab.
        underline_repeat underlines the marker once the cascade has wrapped,
        so the second "1." (level five) is not mistaken for level one"""
        if not is_ordered:
            if self.shared_bullet_num_id is None:
                self.shared_bullet_num_id = self.numbering_root.add_num(
                    self.create_abstract_definition(is_ordered=False)).numId
            return self.shared_bullet_num_id
        return self.numbering_root.add_num(
            self.create_abstract_definition(
                True, start_number, cascade, suffix, underline_repeat)).numId
```

### 8. `Numbering.create_abstract_definition`

**Where:** `class Numbering`  
**Action:** replace the whole method

```python
    def create_abstract_definition(self, is_ordered: bool, start_number: int = 1,
                                   cascade=None, suffix: Optional[str] = None,
                                   underline_repeat: bool = False) -> int:
        """Build one <w:abstractNum> covering all 9 levels. Returns its id."""
        definition_id = self.next_abstract_id
        self.next_abstract_id += 1

        definition = OxmlElement("w:abstractNum")
        definition.set(qn("w:abstractNumId"), str(definition_id))
        add_element(definition, "w:multiLevelType", val="hybridMultilevel")

        for level in range(NESTING_LEVELS):
            # Only the outermost level
            definition.append(self.build_level_definition(
                level, is_ordered, start_number if level == 0 else 1,
                cascade, suffix, underline_repeat))

        existing_definitions = self.numbering_root.findall(qn("w:abstractNum"))
        if existing_definitions:
            existing_definitions[-1].addnext(definition)
        else:
            self.numbering_root.insert(0, definition)
        return definition_id
```

### 9. `Numbering.build_level_definition`

**Where:** `class Numbering`  
**Action:** replace the whole method (the underline rule is the `marker_font_xml` conditional)

```python
    @staticmethod
    def build_level_definition(level: int, is_ordered: bool, start_number: int,
                               cascade=None, suffix: Optional[str] = None,
                               underline_repeat: bool = False):
        """One <w:lvl>: everything about how depth `level` looks"""
        if is_ordered:
            markers = cascade or DEFAULT_ORDERED_CASCADE
            number_format, marker_shape = markers[level % len(markers)]
            marker_text = marker_shape.format("%%%d" % (level + 1))
            # second time round the cascade the marker is underlined
            marker_font_xml = ('<w:rPr><w:u w:val="single"/></w:rPr>'
                               if underline_repeat and level >= len(markers)
                               else "")
        else:
            marker_font = BULLET_MARKERS[level % 3][1]
            number_format, marker_text = "bullet", BULLET_MARKERS[level % 3][0]
            marker_font_xml = (
                '<w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s" w:hint="default"/>'
                '</w:rPr>' % (marker_font, marker_font))
        left_indent = TWIPS_PER_LEVEL * (level + 1)
        # w:suff belongs between numFmt and lvlText. The other way round, Word
        # treats the whole numbering definition as corrupt
        suffix_xml = '<w:suff w:val="%s"/>' % suffix if suffix else ""

        return parse_xml(
            '<w:lvl %s w:ilvl="%d">'
            '<w:start w:val="%d"/>'
            '<w:numFmt w:val="%s"/>'
            '%s'
            '<w:lvlText w:val="%s"/>'
            '<w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="%d" w:hanging="%d"/></w:pPr>'
            '%s'
            '</w:lvl>'
            % (nsdecls("w"), level, start_number, number_format, suffix_xml,
               marker_text, left_indent, TWIPS_PER_LEVEL, marker_font_xml))
```


---

## dlai.py

### 10. `new_cascade_list`

**Where:** section 1, RENDERING  
**Action:** replace the whole function

```python
def new_cascade_list(numbering, cascade=None) -> int:
    """A fresh numId each call, which is what makes numbering restart"""
    return numbering.create_list(True, cascade=cascade or cfg.CASCADE,
                                 suffix=cfg.NUMBER_SUFFIX,
                                 underline_repeat=cfg.CASCADE_REPEAT_UNDERLINE)
```

### 11. `split_lead_in`

**Where:** section 2, READING THE MARKDOWN  
**Action:** replace the whole function (one added condition: a line starting with `[` is never a lead-in)

```python
def split_lead_in(text: str) -> Tuple[str, str]:
    """'Scope: rest' -> ('Scope', 'rest'). A colon is the only marker, so
    'Scope. rest' is an ordinary sentence and comes back as ('', text).

    A lead-in title always introduces prose, so a colon with nothing after it
    is punctuation, not a title. That is what keeps a line like "Each center
    performs the following:" from being underlined as one.

    The bounds stop a long sentence that merely contains a colon, such as
    'The requirements are as follows: a valid document', from qualifying"""
    position = text.find(":") if text else -1
    # "[INPUT REQUIRED: fill this in]" is a placeholder, not a titled line
    if position < 0 or text.lstrip().startswith("["):
        return "", text
    head, rest = text[:position], text[position + 1:].strip()
    if (not head.strip() or not rest
            or len(head) > cfg.LEAD_IN["max_chars"]
            or len(head.split()) > cfg.LEAD_IN["max_words"]
            or any(char in head for char in cfg.LEAD_IN["stop_chars"])):
        return "", text
    return head.strip(), rest
```

### 12. `COVER_FIELDS` and the new `unescape`

**Where:** right after `BOLD_FIELD_LINE = ...`, replacing the existing `COVER_FIELDS` dict  
**Action:** replace `COVER_FIELDS`; `ESCAPED` and `unescape` are new and go directly below it

```python
# label -> the key write_cover looks for
COVER_FIELDS = {"OPR": "opr",
                "OFFICE OF PRIMARY RESPONSIBILITY": "opr",
                "OFFICE OF PRIMARY RESPONSIBILITY (OPR)": "opr",
                "SUBJECT": "subject",
                "EFFECTIVE DATE": "effective", "EFFECTIVE": "effective",
                "REFERENCES": "references"}

# Cover values and signature lines are taken from the raw text and printed
# as plain runs, so markdown escapes like \[ would otherwise show their slash
ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
def unescape(text: str) -> str:
    return ESCAPED.sub(r"\1", text)
```

### 13. `split_cover`

**Where:** section 2  
**Action:** replace the whole function (bold-only lines no longer end the scan; values are unescaped)

```python
def split_cover(markdown_text: str) -> Tuple[str, Dict[str, str]]:
    """Pull "**OPR:** value" style lines off the top. Returns (rest, fields).

    Scanning stops at the first heading, so only the block above the body is
    considered. A value runs until the next line carrying ** or #, which lets
    it wrap across lines. A bold line that is not a known label, such as a
    document title above the fields, is skipped.
    """
    lines = (markdown_text or "").splitlines()
    fields: Dict[str, list] = {}
    current, cut = None, len(lines)

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            cut = index
            break
        match = BOLD_FIELD_LINE.match(stripped)
        if match:
            current = COVER_FIELDS.get(normalize(match.group(1)))
            if current:
                fields[current] = [match.group(2).strip()] if match.group(2).strip() else []
            continue
        if current:
            fields[current].append(stripped)

    return ("\n".join(lines[cut:]),
            {key: unescape("\n".join(value).strip())
             for key, value in fields.items()})
```

### 14. bold-title regexes and `promote_bold_titles` (new)

**Where:** right after `split_input`, before `take_section`  
**Action:** insert the whole block

```python
# ---- input authored without # headings ------------------------------------
# "1. **PURPOSE:**", "**1. PURPOSE:**", "**Enclosure 1: References**  "
BOLD_TITLE = re.compile(r"^(?P<num>\d+[.)]\s+)?\*\*\s*(?P<inner>\d+[.)]\s+)?"
                        r"(?P<name>[^*]+?)\s*:?\s*\*\*\s*:?\s*$")
ENCLOSURE_TITLE = re.compile(r"^ENCLOSURE\s*(\d+)?\s*[:.\-–—]\s*(.+)$", re.I)
PART_TITLE = re.compile(r"^PART\s+(?:[IVXLC]+|\d+)\b", re.I)
FENCE_LINE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
RULE_LINE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
SIGNATURE_MARK = re.compile(r"SIGNATURE\s*BLOCK", re.I)
# "a. text", "(1) text", "(a) text": list markers markdown does not know
LETTER_MARKER = re.compile(r"^(\s*)(?:[A-Za-z][.)]|\((?:\d+|[A-Za-z])\))\s+(?=\S)")
BACK_NAMES = {normalize(alias): name
              for name, extra in cfg.BACK_MATTER.items()
              for alias in (name,) + tuple(extra)}
TOC_NAMES = {normalize(name) for name in cfg.TOC_TITLES}


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
    go, the indent under a numbered title is removed so its body is not read
    as a code block, "a." and "(1)" markers become "1." so markdown nests the
    lists and the cascade relabels them, and a fenced block naming the
    signature block becomes a # SIGNATURE BLOCK section for take_section.

    Returns None when the text already has a # heading, or no title at all"""
    lines = [line.expandtabs(4) for line in (markdown_text or "").splitlines()]
    if any(HEADING_LINE.match(line) for line in lines):
        return None
    sections, enclosures, findings = [], [], []
    out, fence, indent, count, titles = sections, None, 0, 0, 0
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
                dropping, indent, titles = False, None, titles + 1
                continue
        if dropping:
            continue
        if not line.strip():
            out.append(line)
            continue
        leading = len(line) - len(line.lstrip(" "))
        indent = leading if indent is None else indent
        line = LETTER_MARKER.sub(r"\g<1>1. ", line[min(indent, leading):])
        out.append(line)

    if fence is not None:            # never closed: keep it rather than lose it
        out.extend(fence)
    if not titles:
        return None
    findings.insert(0, "bold mode: no # headings, titles identified from "
                       "bold lines")
    return "\n".join(sections), "\n".join(enclosures), findings
```

### 15. `take_section`

**Where:** section 2  
**Action:** replace the whole function (only the return line changed: lifted lines are unescaped)

```python
def take_section(markdown_text: str, *names: str) -> Tuple[str, List[str]]:
    """Lift one required section out as raw lines, before parsing.

    Line breaks matter for a signature block, and markdown folds consecutive
    lines into a single paragraph, so this works on the text rather than the
    parse tree. Returns the remaining markdown and the lines that were taken.
    """
    wanted = {normalize(n) for n in names}
    kept, taken = [], []
    inside, depth = False, 99

    for line in (markdown_text or "").splitlines():
        match = HEADING_LINE.match(line)
        if match:
            level = len(match.group(1))
            if inside and level <= depth:
                inside = False
            key = normalize(match.group(2))
            if not inside and (key in wanted
                               or SECTION_ALIASES.get(key) in wanted):
                inside, depth = True, level
                continue
        (taken if inside else kept).append(line)

    return "\n".join(kept), [unescape(line.strip()) for line in taken
                             if line.strip()]
```

### 16. `BackMatter` (new) and `Outline`

**Where:** right after `class TocEntry`, replacing the existing `class Outline`  
**Action:** insert `BackMatter`; replace `Outline` (gains the `back` field)

```python
class BackMatter(NamedTuple):
    """What the author supplied after the enclosures. Absent means not
    written, apart from the glossary which falls back to config"""
    pages: dict         # APPENDICES / TABLES / FIGURES -> [body nodes]
    glossary: Optional[tuple]   # ([preamble nodes], [(part title, [nodes])])


class Outline(NamedTuple):
    groups: list        # [(title node or None, [body nodes])] per enclosure
    offset: int         # subtract from a heading level to normalise it
    entries: list       # every TocEntry, in document order
    titles: list        # enclosure titles, for the signature block
    back: BackMatter
```

### 17. `outline`

**Where:** section 2  
**Action:** replace the whole function (peels back matter off the groups; rows come from `back_matter_plan`; returns `back`)

```python
def outline(markdown_text: str) -> Outline:
    """Everything the later pages need to know, worked out before writing.

    Grouping and the table of contents come from one pass, because the ToC
    rows and their bookmark names have to exist before the enclosures are
    written. Knowing them up front is what lets the document go down in
    reading order with nothing created out of place and moved back.

    Whatever the author used as their top heading level becomes the enclosure
    level, so an H1 led document and an H2 led one give the same structure and
    no rule has to ask "is there an H1?" """
    tree = logic.parse_markdown(markdown_text or "")
    levels = [heading_level(n) for n in tree.children if n.type == "heading"]
    offset = (min(levels) if levels else 1) - 1

    groups, title, body = [], None, []
    for node in tree.children:
        if node.type == "heading" and heading_level(node) - offset == 1:
            if title is not None or body:
                groups.append((title, body))
            title, body = node, []
        else:
            body.append(node)
    if title is not None or body:
        groups.append((title, body))

    # Back matter arrives as ordinary top-level groups (bold-mode input, or a
    # # heading named APPENDICES). Peel those off so they are written after
    # the enclosures in the fixed order rather than numbered among them
    kept, pages, glossary, parts = [], {}, None, []
    for title, body in groups:
        key = normalize(heading_text(title)) if title is not None else ""
        name = BACK_NAMES.get(key)
        if name == "GLOSSARY":
            glossary = body
        elif name:
            pages[name] = body
        elif glossary is not None and PART_TITLE.match(key):
            parts.append((heading_text(title), body))
        else:
            kept.append((title, body))
    groups = kept
    back = BackMatter(pages, (glossary, parts) if glossary is not None else None)

    entries, titles = [], []

    def add(level, text):
        entries.append(TocEntry(level, text, "DLAIREF%d" % (len(entries) + 1)))

    for index, (group_title, group_body) in enumerate(groups, start=1):
        name = heading_text(group_title) if group_title else "ENCLOSURE"
        titles.append(name)
        add(1, cfg.BACK["encl_display"] % (index, name))
        for node in group_body:
            if node.type == "heading":
                level = max(1, heading_level(node) - offset)
                if level <= cfg.BACK["toc_depth"]:
                    add(level, heading_text(node))

    # the same list write_back_matter walks, so the bookmark count agrees
    for part in back_matter_plan(back):
        add(part.level, part.title)

    return Outline(groups, offset, entries, titles, back)
```

### 18. `BackPart` and `back_matter_plan` (new)

**Where:** right after `outline`, before the `# 3. WRITING THE MARKDOWN` banner  
**Action:** insert

```python
class BackPart(NamedTuple):
    key: str        # heading style: enclosure, appendices or glossary_part
    level: int      # table of contents level
    title: str
    body: object    # config entries (tuple of str) or authored [nodes]
    authored: bool


def back_matter_plan(back: BackMatter) -> List[BackPart]:
    """Everything after the enclosures, in the order it is written.

    One list feeds both outline (ToC rows, bookmark names) and
    write_back_matter, so they can never disagree on how many pages there
    are. Only pages the author supplied are written, apart from the glossary,
    which falls back to config.BACK["glossary_parts"]"""
    conf = cfg.BACK
    parts: List[BackPart] = []
    if "APPENDICES" in back.pages:
        parts.append(BackPart("appendices", 1, conf["appendices_title"],
                              back.pages["APPENDICES"], True))
    if back.glossary is not None:
        preamble, authored = back.glossary
        parts.append(BackPart("enclosure", 1, conf["encl_last"], preamble, True))
        parts += [BackPart("glossary_part", 2, title, body, True)
                  for title, body in authored]
    else:
        parts.append(BackPart("enclosure", 1, conf["encl_last"], (), False))
        parts += [BackPart("glossary_part", 2, title, entries, False)
                  for title, entries in conf["glossary_parts"]]
    for name in ("TABLES", "FIGURES"):
        if name in back.pages:
            parts.append(BackPart("enclosure", 1, name, back.pages[name], True))
    return parts
```

### 19. `DlaiWriter.write_paragraph`

**Where:** `class DlaiWriter`  
**Action:** replace the whole method (only the first statement changed: hard breaks become spaces)

```python
    def write_paragraph(self, node, position):
        # a hard line break separates words; without this "Overview:" and
        # the text on the next line run together
        spans = logic.inline_spans(logic.find_inline_child(node))
        text = " ".join("".join(" " if span.is_line_break else span.text
                                for span in spans).split())
        if not text:
            return None
        if position.list_depth < 0:
            self.after_prose = True
        lead_in, rest = split_lead_in(text)
        self.last_paragraph = write(
            self.document, self.lead_key if lead_in else self.body_key, rest,
            level=self.content_level(position), lead_in=lead_in,
            num_id=self.num_id)
        return self.last_paragraph
```

### 20. `write_back_matter`

**Where:** section 4, THE HARDCODED SHELL  
**Action:** replace the whole function (new signature: `back`, `opts`, `numbering`)

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
        if not part.authored:
            for entry in part.body:
                lead_in, rest = split_lead_in(entry)
                write(document, "definition", rest, lead_in=lead_in)
        elif part.body:
            DlaiWriter(document, opts, numbering, new_cascade_list(numbering),
                       base_level=-1, min_level=0, blocks=("subsection",),
                       body_key="flat", lead_key="definition"
                       ).write_blocks(part.body, logic.Position())
```


---

## dlai_to_docx.py

### 21. `dlai_to_docx`

**Where:** top of file  
**Action:** replace the whole function (promote call at the top, findings accumulate, `plan.back` passed to the back matter)

```python
def dlai_to_docx(
    markdown_input: str,
    sections_input: str = "",
    doc_title: str = "PLACEHOLDER TITLE",
) -> Tuple[bytes, List[str]]:
    """
    Convert two markdown strings into a DLAI .docx and return its raw bytes.

    markdown_input   the enclosures. Its shallowest heading level becomes the
                     enclosure title level and everything nests below it
    sections_input   the required sections before the ToC, matched loosely by
                     heading. Anything missing gets a placeholder
    doc_title        printed in the header and on the cover

    Returns (bytes, findings). Nothing touches the filesystem, so this is what
    a route hands straight back to the caller.
    """
    # No # headings anywhere: the titles are bold lines. promote_bold_titles
    # rewrites them as # headings and does the section/enclosure split, so
    # from here down nothing knows which way the document was authored
    findings: List[str] = []
    promoted = dlai.promote_bold_titles("\n".join(
        part for part in (sections_input, markdown_input) if part))
    if promoted:
        sections_input, markdown_input, findings = promoted

    # strip the "**OPR:** value" block off the top of either input
    sections_input, cover = dlai.split_cover(sections_input)
    markdown_input, more = dlai.split_cover(markdown_input)
    cover = {**more, **cover}

    opts = helpers.DocxOptions(body_font=cfg.BODY_FONT, body_size_pt=cfg.BODY_SIZE)
    document = Document()
    numbering = helpers.Numbering(document)

    # 1. read the enclosure markdown first, so every enclosure title and
    #    bookmark name is known before anything is written. That is what lets
    #    the rest go down in reading order instead of being moved afterwards
    plan = dlai.outline(markdown_input)
    bookmarks = [entry.bookmark for entry in plan.entries]

    # 2. page setup, the Word styles, then the hardcoded cover
    dlai.setup_page(document, doc_title)
    dlai.write_cover(document, numbering, doc_title, cover)

    # 3. the required sections, matched out of sections_input
    more, signature = write_required_sections(
        document, opts, numbering, sections_input)
    findings += more

    # 4. signature block and table of contents, both built from the plan
    dlai.write_signature_block(document, plan.titles, signature)
    dlai.write_table_of_contents(document, plan.entries)

    # 5. the enclosures themselves, then the fixed back matter
    write_enclosures(document, opts, numbering, plan, bookmarks)
    dlai.write_back_matter(document, bookmarks, plan.back, opts, numbering)

    # 6. tell Word to refresh page numbers on open, then serialise to bytes
    helpers.update_fields_on_open(document)
    return helpers.document_to_bytes(document), findings
```

### 22. `write_required_sections`

**Where:** below `dlai_to_docx`  
**Action:** replace the whole function (the last statement changed: DEFINITIONS uses `flat` for body, `definition` for lead-ins)

```python
def write_required_sections(document, opts, numbering, sections_input: str):
    """Write the numbered sections. Returns (findings, signature lines).

    The signature section is matched like any other, so it is never mistaken
    for an enclosure, but it is not printed here. Its lines are handed back for
    write_signature_block to place further down the page.
    """
    # taken from the raw text so its line breaks survive
    sections_input, signature = dlai.take_section(sections_input,
                                                  cfg.SIGNATURE_SECTION)
    slots, findings = dlai.split_sections(sections_input)
    slots.pop(cfg.SIGNATURE_SECTION, None)
    findings = [f for f in findings if cfg.SIGNATURE_SECTION not in f]
    num_id = dlai.new_cascade_list(numbering)

    for index, (name, nodes) in enumerate(slots.items()):
        paragraph = dlai.write(document, "section", name, num_id=num_id)
        if index == 0 and cfg.PAGE["break_after_cover"]:
            paragraph.paragraph_format.page_break_before = True
        if not nodes:
            dlai.write(document, "prose", cfg.MISSING_PLACEHOLDER,
                       level=1, num_id=num_id)
            continue
        # DEFINITIONS is the one section that sits flush left and unnumbered:
        # "Term: definition" lines underlined, anything else plain
        flat = name in cfg.FLAT_SECTIONS
        dlai.DlaiWriter(document, opts, numbering, num_id, base_level=0,
                        min_level=1, blocks=("subsection",),
                        body_key="flat" if flat else "prose",
                        lead_key="definition" if flat else "subsection"
                        ).write_blocks(nodes, logic.Position())
    return findings, signature
```


---

## After pasting

- `BOLD_ONLY_LINE` in dlai.py is no longer referenced. Delete it or leave it.
- `dlai_to_docx.py` needs no new imports; everything it calls is in `dlai`.
- Run `python3 dlai_to_docx.py demo.md out.docx "TITLE"` and expect exactly three MISSING findings (INFORMATION REQUIREMENTS, INTERNAL CONTROLS, EXPIRATION DATE) and `OK, no schema or reference problems`.
