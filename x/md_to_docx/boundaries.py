"""Where each block starts. A provider returns rules.Start entries; assemble() turns them into a DlaiDocument.
PROVIDERS["regex"] is the deterministic reading below; the section agent registers PROVIDERS["llm"]."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import config as cfg
from rules import (
    BACK_NAMES,
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


def preprocess(text: str) -> List[str]:
    """Line endings, BOM, leading tabs, __bold__ -> **bold**. Nothing is removed, so line numbers stay 1:1 with the
    input."""
    lines = (text or "").lstrip("\ufeff").splitlines()
    return [UNDERSCORE_BOLD.sub(r"**\1**", indent_tabs(line)) for line in lines]


def indent_tabs(line: str) -> str:
    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)].expandtabs(4) + stripped


def regex_boundaries(lines: List[str]) -> Tuple[List[Start], str]:
    """Block starts from the deterministic rules. Returns (starts, mode)
    where mode is "heading" when the input has # headings, else "bold"."""
    in_fence = False
    for line in lines:
        if FENCE_LINE.match(line):
            in_fence = not in_fence
        elif not in_fence and HEADING_LINE.match(line):
            return heading_starts(lines), "heading"
    return bold_starts(lines), "bold"


def cover_start(line: str, index: int) -> Optional[Start]:
    match = BOLD_FIELD_LINE.match(line.strip())
    key = COVER_FIELDS.get(normalize(match.group(1))) if match else None
    return Start("cover", key, index, inline=match.group(2).strip()) if key else None


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


PROVIDERS = {"regex": regex_boundaries}


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
        elif kind == "signature":
            content = [l for l in body if not FENCE_LINE.match(l)]
            content = [l.strip() for l in content if l.strip()]
            signature = [unescape(l) for l in content[1:]]  # first line is the marker
            findings.append("SIGNATURE BLOCK taken from the fenced block " "(%d line(s))" % len(signature))
            if start.end is not None:
                leftover(lines[start.end + 1 : next_line])
        elif kind == "section" and start.name == cfg.SIGNATURE_SECTION:
            signature = [unescape(l.strip()) for l in body if l.strip()]
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


def build_document(text: str, provider: str = None) -> DlaiDocument:
    """Text in, DlaiDocument out. A provider returns (starts, mode) or (starts, mode, findings)."""
    name = provider or cfg.BOUNDARY_PROVIDER
    if name not in PROVIDERS:
        raise KeyError(
            "boundary provider %r is not registered; import the "
            "package that provides it first (e.g. md_section_agent)" % name
        )
    lines = preprocess(text)
    result = PROVIDERS[name](lines)
    starts, mode = result[0], result[1]
    doc = assemble(lines, starts, mode)
    if len(result) > 2:
        doc.findings[0:0] = list(result[2])
    return doc
