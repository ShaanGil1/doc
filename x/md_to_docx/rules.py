"""The vocabulary shared by detection and rendering: regexes, normalise, alias tables, Start / Block / DlaiDocument."""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, NamedTuple, Optional

import config as cfg


class ConversionError(Exception):
    """The input cannot be rendered as intended. Raised, not returned as a
    finding, so a build never quietly produces a wrong document"""


# ---- normalisation ----------------------------------------------------------
MARKUP = re.compile(r"[*_`~#]+")
# "## 1. Purpose" and "## 1.2) Purpose" both mean the section, not a new name
LEADING_NUMBER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
TRAILING_PUNCTUATION = re.compile(r"[\s:.\-–—;,]+$")
WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """'Summary of  Changes :' and '**SUMMARY OF CHANGES**' both become
    'SUMMARY OF CHANGES'"""
    text = MARKUP.sub("", unicodedata.normalize("NFKC", text or ""))
    text = LEADING_NUMBER.sub("", WHITESPACE.sub(" ", text).strip())
    return TRAILING_PUNCTUATION.sub("", text).upper()


def unescape(text: str) -> str:
    return ESCAPED.sub(r"\1", text)


# ---- alias tables from config -----------------------------------------------
SECTION_ALIASES = {
    normalize(alias): name for name, spec in cfg.SECTIONS.items() for alias in (name,) + tuple(spec.aliases)
}
BACK_NAMES = {normalize(alias): name for name, extra in cfg.BACK_MATTER.items() for alias in (name,) + tuple(extra)}
TOC_NAMES = {normalize(name) for name in cfg.TOC_TITLES}
# label -> the key write_cover looks for
COVER_FIELDS = {
    "OPR": "opr",
    "OFFICE OF PRIMARY RESPONSIBILITY": "opr",
    "OFFICE OF PRIMARY RESPONSIBILITY (OPR)": "opr",
    "SUBJECT": "subject",
    "EFFECTIVE DATE": "effective",
    "EFFECTIVE": "effective",
    "REFERENCES": "references",
}


# ---- what a line can be ------------------------------------------------------
# Cover values and signature lines are taken from the raw text and printed
# as plain runs, so markdown escapes like \[ would otherwise show their slash
ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
# A labelled field, e.g. "**OPR:** J6 Logistics". Colon inside or outside
BOLD_FIELD_LINE = re.compile(r"^\s*\*\*\s*(.+?)\s*:?\s*\*\*\s*:?\s*(.*)$")
HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*)$")
# "1. **PURPOSE:**", "**1. PURPOSE:**", "**Enclosure 1: References**  "
BOLD_TITLE = re.compile(r"^(?P<num>\d+[.)]\s+)?\*\*\s*(?P<inner>\d+[.)]\s+)?" r"(?P<name>[^*]+?)\s*:?\s*\*\*\s*:?\s*$")
# the same title with its body on the same line, colon required, text after
BOLD_TITLE_INLINE = re.compile(
    r"^(?P<num>\d+[.)]\s+)\*\*\s*(?P<name>[^*:]+?)" r"\s*(?::\s*\*\*|\*\*\s*:)\s*(?P<rest>\S.*)$"
)
# __bold__ means the same as **bold** in markdown; preprocess rewrites it so
# every rule only has to know one delimiter
UNDERSCORE_BOLD = re.compile(r"__(?=\S)([^_\n]+?)(?<=\S)__")
ENCLOSURE_TITLE = re.compile(r"^ENCLOSURE\s*(\d+)?\s*[:.\-–—]\s*(.+)$", re.I)
PART_TITLE = re.compile(r"^PART\s+(?:[IVXLC]+|\d+)\b", re.I)
FENCE_LINE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
RULE_LINE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
SIGNATURE_MARK = re.compile(r"SIGNATURE\s*BLOCK", re.I)
# "1." "a." "(1)" "(a)": depth is read from the shape, never the indent; lowercase only, so "A. Smith" is prose
LIST_MARKER = re.compile(
    r"^\s*(?:(?P<number>\d+)[.)]|(?P<letter>[a-z])[.)]" r"|\((?P<pnumber>\d+)\)|\((?P<pletter>[a-z])\))\s+(?=\S)"
)
MARKER_DEPTH = {"number": 0, "letter": 1, "pnumber": 2, "pletter": 3}
# "FSA        Financial Services Activity", "FSA\tFinancial ...", "FSA: Financial ..."
GLOSSARY_ENTRY = re.compile(r"^(?P<term>[^\s\[:][^:\t]*?)(?:\t+|\s{2,}|:\s+)(?P<text>\S.*)$")


# ---- the document model ------------------------------------------------------
class Start(NamedTuple):
    """One block boundary: kind, name, 0-based line of the title, inline text after the title, enclosure number,
    matched (False for an unknown numbered bold title), and end (last line of a fenced signature)."""

    kind: str
    name: str
    line: int
    inline: str = ""
    number: Optional[int] = None
    matched: bool = True
    end: Optional[int] = None


class Block(NamedTuple):
    title: str  # as it will be displayed (heading text, part title)
    lines: List[str]  # body lines, verbatim from the input
    source: int  # 1-based line number of the title, for findings


class Glossary(NamedTuple):
    preamble: Block  # lines under the GLOSSARY title
    abbreviations: Optional[Block]  # PART I, two columns
    definitions: Optional[Block]  # PART II, "Term.  text"
    other: List[Block]  # any other part, printed flat


class DlaiDocument(NamedTuple):
    cover: Dict[str, str]  # opr / subject / references / effective
    sections: Dict[str, Optional[Block]]  # every name in cfg.SECTIONS
    signature: List[str]  # lines, [] when none was found
    enclosures: List[Block]
    appendices: Optional[Block]
    glossary: Optional[Glossary]
    tables: Optional[Block]
    figures: Optional[Block]
    normalize: bool  # bold-mode input: list markers are
    # rewritten; # input is parsed raw
    offset: int  # heading level offset for # input
    findings: List[str]
