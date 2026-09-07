"""Every value the DLAI depends on: styles, sections, enclosures, cascade, cover, back matter, and the two switches."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docx.enum.text import WD_ALIGN_PARAGRAPH

ASSETS = Path(__file__).parent / "assets"

LEFT, CENTER, RIGHT = (WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT)

BODY_FONT = "Times New Roman"
BODY_SIZE = 12.0
BODY_COLOR = "000000"
GAP = 12.0  # the 12pt after that shows up nearly everywhere
LINE_SPACING = 1.0  # 1.0 = single. python-docx defaults to 1.15


@dataclass(frozen=True)
class Style:
    name: str  # the name shown in Word's styles pane
    # ---- becomes a Word paragraph style -----------------------------------
    base: str = "Normal"
    font: Optional[str] = BODY_FONT
    size: Optional[float] = BODY_SIZE
    color: Optional[str] = BODY_COLOR
    bold: bool = False
    italic: bool = False
    underline: bool = False
    caps: bool = False
    align: object = LEFT
    before: float = 0.0
    after: float = GAP
    line: float = LINE_SPACING
    # ---- placement, applied per paragraph ---------------------------------
    numbered: bool = False  # takes a marker from CASCADE
    indent: bool = False  # indents by nesting level
    first_line: float = 0.0  # first-line indent, inches
    page_break: bool = False
    suffix: str = ""  # appended to the text, e.g. ":"
    lead_suffix: str = ":"  # after an underlined lead-in title
    lead_gap: str = " "  # between the lead-in and the text


UNDERLINE_STYLE = "DLAI Underline"  # character style for underlined runs

STYLES = {
    # ---- cover -------------------------------------------------------------
    "agency": Style("DLAI Agency", size=18.0, align=CENTER),
    "doc_type": Style("DLAI Title", base="Heading 1", size=22.0, bold=True, align=CENTER, after=36.0),
    "cover_line": Style("DLAI Cover Line", align=RIGHT, after=0.0),
    "cover_label": Style("DLAI Cover Label", underline=True),
    "cover_ref": Style("DLAI Cover Reference", after=0.0, numbered=True),
    # ---- required sections -------------------------------------------------
    # Normal base, not a Heading: sections are numbered body paragraphs and stay out of the navigation pane
    "section": Style("DLAI Section", caps=True, underline=True, before=24.0, numbered=True, indent=True, suffix=":"),
    # underline applies to a heading's own text; on a lead-in paragraph the
    # guard in write() puts it on the title only, never the prose
    "subsection": Style("DLAI Subsection", underline=True, before=GAP, numbered=True, indent=True, suffix=":"),
    "prose": Style("DLAI Prose", before=GAP, numbered=True, indent=True),
    # the exception: flush left, unnumbered, term underlined
    "definition": Style("DLAI Definition", before=GAP, suffix=":"),
    # ---- signature block ---------------------------------------------------
    "signature": Style("DLAI Signature", after=0.0, first_line=3.0),
    "encl_label": Style("DLAI Enclosure Label", before=GAP, after=0.0),
    "encl_item": Style("DLAI Enclosure Item", after=0.0, first_line=0.25),
    # ---- table of contents -------------------------------------------------
    # not named "TOC 1/2/3": Word layers its built-in indents onto those names and the dot leaders drift
    "toc_title": Style(
        "DLAI ToC Heading",
        base="Heading 1",
        size=14.0,
        underline=True,
        caps=True,
        align=CENTER,
        after=24.0,
        page_break=True,
    ),
    "toc_1": Style("DLAI ToC 1", caps=True, after=0.0),
    "toc_2": Style("DLAI ToC 2", caps=True, after=0.0),
    "toc_3": Style("DLAI ToC 3", caps=True, after=0.0),
    # ---- enclosure pages ---------------------------------------------------
    "enclosure": Style(
        "DLAI Enclosure Heading", base="Heading 2", caps=True, underline=True, align=CENTER, after=24.0, page_break=True
    ),
    "encl_h2": Style(
        "DLAI Enclosure Sub", base="Heading 3", before=GAP, underline=True, numbered=True, indent=True, suffix=":"
    ),
    "encl_h3": Style(
        "DLAI Enclosure Sub 2", base="Heading 4", before=GAP, underline=True, numbered=True, indent=True, suffix=":"
    ),
    # ---- glossary ----------------------------------------------------------
    "glossary_part": Style(
        "DLAI Glossary Part", base="Heading 3", caps=True, underline=True, align=CENTER, before=GAP, after=24.0
    ),
    # PART II: "Term.  Definition text.", term underlined, one per paragraph
    "glossary_definition": Style("DLAI Glossary Definition", before=GAP, lead_suffix=".", lead_gap="  "),
    # one abbreviation row: term, tab, meaning. Column and grouping come from
    # GLOSSARY_COLUMNS, applied per paragraph
    "glossary_entry": Style("DLAI Glossary Entry", after=0.0),
    # ---- appendices ---------------------------------------------------------
    # its own page, reading "APPENDICES:" with the body below it
    "appendices": Style(
        "DLAI Appendices",
        base="Heading 2",
        caps=True,
        underline=True,
        align=CENTER,
        after=GAP,
        page_break=True,
        suffix=":",
    ),
    # authored back matter prose: flush left, unnumbered, no suffix
    "flat": Style("DLAI Flat", before=GAP),
}


PAGE = {
    "width_in": 8.5,
    "height_in": 11.0,
    "margin_in": 1.0,
    "header_align": RIGHT,
    "footer_align": CENTER,
    "break_after_cover": False,
}

# repeats to fill Word's 9 levels: 1. -> a. -> (1) -> (a) -> then again with the marker underlined
CASCADE = (("decimal", "{}."), ("lowerLetter", "{}."), ("decimal", "({})"), ("lowerLetter", "({})"))
CASCADE_REPEAT_UNDERLINE = True
INDENT_STEP_IN = 0.25
NUMBER_SUFFIX = "tab"


# name -> extra spellings to accept. Matching uppercases and strips
# punctuation first, so only genuine misspellings belong here.
# ---- the required sections, in the order they are written ------------------
# one spec per section: aliases, body/lead-in styles, and optional. Print order is dict order.
# optional=True: absent means left out entirely (no heading, no placeholder, numbering closes up)
@dataclass(frozen=True)
class Section:
    aliases: tuple = ()
    body_key: str = "prose"
    lead_key: str = "subsection"
    optional: bool = False


SECTIONS = {
    "PURPOSE": Section(),
    "SUMMARY OF CHANGES": Section(("SUMMARY OF CHANGE",)),
    "APPLICABILITY": Section(("SCOPE AND APPLICABILITY",)),
    "DEFINITIONS": Section(("DEFINATIONS",), body_key="flat", lead_key="definition"),
    "POLICY": Section(),
    "RESPONSIBILITIES": Section(("RESPONSIBILITY",)),
    "PROCEDURES": Section(("PROCEEDURES", "PROCEDURE")),
    "INFORMATION REQUIREMENTS": Section(("INFORMATION REQUIRMENTS",)),
    "RELEASABILITY": Section(("RELEASEABILITY",)),
    "INTERNAL CONTROLS": Section(("INTERNAL CONTROL",)),
    "EXPIRATION DATE": Section(("EXPIRATION", "EXPIRATION DATES")),
    "SIGNATURE BLOCK": Section(("SIGNATURE",)),
}
# name -> aliases, for anything that still wants the old shape
REQUIRED_SECTIONS = {name: spec.aliases for name, spec in SECTIONS.items()}
MISSING_PLACEHOLDER = "section not found"

# matched like a section so it is never taken for an enclosure; its lines feed the signature block
SIGNATURE_SECTION = "SIGNATURE BLOCK"


# ---- enclosures ---------------------------------------------------------------
# per-enclosure formatting keyed by normalised title; "*" is the default; enabled=False parks an override
@dataclass(frozen=True)
class Enclosure:
    cascade: tuple = None
    indent_in: float = None
    enabled: bool = True


ENCLOSURES = {
    "*": Enclosure(),
    # DoD references are lettered (a) (b) (c) at the top level. Off until the
    # template sheet says otherwise; flip enabled to True to use it
    "REFERENCES": Enclosure(cascade=(("lowerLetter", "({})"),), indent_in=0.5, enabled=False),
}

# A colon marks a lead-in title; a period does not. The bounds stop a long
# sentence that merely ends in a colon from being read as a title.
LEAD_IN = {"max_chars": 60, "max_words": 8, "stop_chars": ".!?;"}

COVER = {
    "agency_name": "Defense Logistics Agency",
    "doc_type": "DLAI",
    "effective_text": "Effective: See date of Digital Signature",
    "effective_pattern": "Effective: %s",  # used when the input supplies one
    "seal": (str(ASSETS / "seal.png"), 1.5, 1.23),  # path, width, height
    "rule": (str(ASSETS / "rule.png"), 6.5, 0.16),
    # (printed label, cover field it accepts). Trailing double space is
    # deliberate and part of the label
    "labels": (("OPR:  ", "opr"), ("Subject:  ", "subject"), ("References:  ", None)),
    "label_space_before_pt": GAP,
    "ref_count": 6,
    "ref_pattern": "Placeholder Reference %d",
    "ref_cascade": (("lowerLetter", "{}."),),
    "ref_indent_in": 0.5,
}

BACK = {
    "sig_lines": ("your name", "item 1", "item 2"),
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

# glossary PART I: term, tab, meaning at column_in; sorted; blank line between initial letters
GLOSSARY_COLUMNS = {"keywords": ("ABBREVIATION", "ACRONYM"), "column_in": 2.0, "group_gap_pt": GAP}

# glossary PART II: one "Term.  text" paragraph per definition, term underlined, sorted when sort is on
GLOSSARY_DEFINITIONS = {"keywords": ("DEFINITION",), "sort": True}

# ---- how the document is split into blocks ---------------------------------
# "regex" is the deterministic reading; "llm" is the section agent, which registers itself when imported
BOUNDARY_PROVIDER = "regex"

# a code block in any body is a formatting accident: True raises ConversionError, False makes it a finding
STRICT_NO_CODE_BLOCKS = True

# back matter titles and their spellings; only authored pages are written, in this order
BACK_MATTER = {
    "APPENDICES": ("APPENDIX",),
    "GLOSSARY": (),
    "TABLES": ("TABLE", "TABLE(S)"),
    "FIGURES": ("FIGURE", "FIGURE(S)"),
}
# An authored table of contents is dropped; the pipeline generates its own
TOC_TITLES = ("TABLE OF CONTENTS", "CONTENTS")
