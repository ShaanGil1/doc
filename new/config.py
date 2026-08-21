"""
config.py - every value the DLAI depends on.
"""
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
GAP = 12.0              # the 12pt after that shows up nearly everywhere


@dataclass(frozen=True)
class Style:
    name: str                       # the name shown in Word's styles pane
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
    # ---- placement, applied per paragraph ---------------------------------
    numbered: bool = False          # takes a marker from CASCADE
    indent: bool = False            # indents by nesting level
    first_line: float = 0.0         # first-line indent, inches
    page_break: bool = False
    suffix: str = ""                # appended to the text, e.g. ":"


UNDERLINE_STYLE = "DLAI Underline"   # character style for underlined runs

STYLES = {
    # cover
    "agency":      Style("DLAI Agency", size=18.0, align=CENTER),
    "doc_type":    Style("DLAI Title", base="Heading 1", size=22.0, bold=True, align=CENTER, after=36.0),
    "cover_line":  Style("DLAI Cover Line", align=RIGHT, after=0.0),
    "cover_label": Style("DLAI Cover Label", underline=True),
    "cover_ref":   Style("DLAI Cover Reference", after=0.0, numbered=True),

    # required sections 
    "section":     Style("DLAI Section", base="Heading 3", caps=True, underline=True, before=24.0, numbered=True, indent=True, suffix=":"),
    # underline applies to a heading's own text; on a lead-in paragraph
    "subsection":  Style("DLAI Subsection", underline=True, before=GAP, numbered=True, indent=True, suffix=":"),
    "prose":       Style("DLAI Prose", before=GAP, numbered=True, indent=True),
    # the exception: flush left, unnumbered, term underlined
    "definition":  Style("DLAI Definition", before=GAP, suffix=":"),

    # signature block 
    "signature":   Style("DLAI Signature", after=0.0, first_line=3.0),
    "encl_label":  Style("DLAI Enclosure Label", before=GAP, after=0.0),
    "encl_item":   Style("DLAI Enclosure Item", after=0.0, first_line=0.25),

    # table of contents
    "toc_title":   Style("TOC Heading", base="Heading 1", size=14.0, underline=True, caps=True, align=CENTER, after=24.0, page_break=True),
    "toc_1":       Style("TOC 1", caps=True, after=0.0),
    "toc_2":       Style("TOC 2", caps=True, after=0.0),
    "toc_3":       Style("TOC 3", caps=True, after=0.0),

    # enclosure pages
    "enclosure":   Style("DLAI Enclosure Heading", base="Heading 2", caps=True, align=CENTER, after=24.0, page_break=True),
    "encl_h2":     Style("DLAI Enclosure Sub", base="Heading 3", before=GAP, underline=True, numbered=True, indent=True, suffix=":"),
    "encl_h3":     Style("DLAI Enclosure Sub 2", base="Heading 4", before=GAP, underline=True, numbered=True, indent=True, suffix=":"),

    # glossary
    "glossary_part": Style("DLAI Glossary Part", base="Heading 3", caps=True, align=CENTER, before=GAP, after=24.0),
}


PAGE = {
    "width_in": 8.5, "height_in": 11.0, "margin_in": 1.0,
    "header_align": RIGHT, "footer_align": CENTER,
    "break_after_cover": True,
}

# Markers repeat to fill Word's 9 levels: 1. -> a. -> (1) -> (a) -> 1. ...
CASCADE = (("decimal", "{}."), ("lowerLetter", "{}."), ("decimal", "({})"), ("lowerLetter", "({})"))
INDENT_STEP_IN = 0.25
NUMBER_SUFFIX = "tab"

# name -> extra spellings to accept. Matching uppercases and strips
REQUIRED_SECTIONS = {
    "PURPOSE": (),
    "SUMMARY OF CHANGES": ("SUMMARY OF CHANGE",),
    "APPLICABILITY": ("SCOPE AND APPLICABILITY",),
    "DEFINITIONS": ("DEFINATIONS",),
    "POLICY": (),
    "RESPONSIBILITIES": ("RESPONSIBILITY",),
    "PROCEDURES": ("PROCEEDURES", "PROCEDURE"),
    "INFORMATION REQUIREMENTS": ("INFORMATION REQUIRMENTS",),
    "RELEASABILITY": ("RELEASEABILITY",),
    "INTERNAL CONTROLS": ("INTERNAL CONTROL",),
}
MISSING_PLACEHOLDER = "this is missing"

# Sections whose body sits flush left and unnumbered instead of following the cascade
FLAT_SECTIONS = ("DEFINITIONS",)

# A colon marks a lead-in title; a period does not
LEAD_IN = {"max_chars": 60, "max_words": 8, "stop_chars": ".!?;"}

COVER = {
    "agency_name": "Defense Logistics Agency",
    "doc_type": "DLAI",
    "effective_text": "Effective: See date of Digital Signature",
    "seal": (str(ASSETS / "seal.png"), 1.5, 1.23),      # path, width, height
    "rule": (str(ASSETS / "rule.png"), 6.5, 0.16),
    "labels": ("OPR:  ", "Subject:  ", "References:  "),
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
    "glossary_parts": ("PART I: ABBREVIATIONS AND ACRONYMS",
                       "PART II: DEFINITIONS"),
    "trailing_lists": ("TABLES", "FIGURES"),
}
