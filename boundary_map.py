"""What the model fills in: one optional {line, starts_with} per known block, a list for the enclosures. Starts only."""

from __future__ import annotations

import re
from typing import List, Optional, Type

from pydantic import BaseModel, Field, create_model

import config as cfg  # md_to_docx/config.py

COVER_KEYS = ("opr", "subject", "references", "effective")
FIXED_KINDS = (
    "signature",
    "table_of_contents",
    "appendices",
    "glossary",
    "glossary_part_abbreviations",
    "glossary_part_definitions",
    "tables",
    "figures",
)

# what to look for, per field. These become the schema descriptions the model
# reads, which small models lean on far more than the prose instruction
COVER_HINTS = {
    "opr": "the bold cover label OPR or 'Office of Primary Responsibility'",
    "subject": "the bold cover label SUBJECT",
    "references": (
        "the bold cover label REFERENCES on the cover page, before section 1, with its "
        "list of references on the same line or the lettered lines under it. Report it even "
        "though an ENCLOSURE 1: REFERENCES also exists later; that one is an enclosure"
    ),
    "effective": "the bold cover label EFFECTIVE or EFFECTIVE DATE, if present",
}
FIXED_HINTS = {
    "signature": (
        "the signature block: the opening ``` fence whose next line names the signature block, or a SIGNATURE BLOCK "
        "title"
    ),
    "table_of_contents": "a title reading TABLE OF CONTENTS (the plain lines under it are not blocks)",
    "appendices": "the bold or # title reading APPENDICES, after the last enclosure",
    "glossary": "the bold or # title reading GLOSSARY, after the last enclosure",
    "glossary_part_abbreviations": "the glossary part titled PART I ... ABBREVIATIONS AND ACRONYMS",
    "glossary_part_definitions": "the glossary part titled PART II ... DEFINITIONS",
    "tables": "a title reading TABLES after the enclosures, if present",
    "figures": "a title reading FIGURES after the enclosures, if present",
}


def field_name(section: str) -> str:
    return "section_" + re.sub(r"[^a-z0-9]+", "_", section.lower()).strip("_")


SECTION_FIELDS = {field_name(name): name for name in cfg.SECTIONS if name != cfg.SIGNATURE_SECTION}


class Where(BaseModel):
    """One block start. `line` is the number printed at the left of the line;
    `starts_with` is the first few words of that same line, copied exactly"""

    line: int = Field(description="the number shown at the start of the line where this block's title is")
    starts_with: str = Field(description="the first 3 to 8 words of that line, copied exactly as written")


class EnclosureWhere(Where):
    title: str = Field(description="the enclosure's title, e.g. References, without any 'Enclosure 1:' prefix")


def build_schema() -> Type[BaseModel]:
    """The output model in document order, every field described; built from the converter's SECTIONS."""

    def opt(description):
        return (Optional[Where], Field(default=None, description=description))

    fields = {}
    for key in COVER_KEYS:
        fields["cover_" + key] = opt(COVER_HINTS[key])
    for name, section in SECTION_FIELDS.items():
        fields[name] = opt(
            "the %s section titled %s (numbered, bold; its text may share the line)"
            % ("optional" if cfg.SECTIONS[section].optional else "required", section)
        )
    fields["signature"] = opt(FIXED_HINTS["signature"])
    fields["table_of_contents"] = opt(FIXED_HINTS["table_of_contents"])
    fields["enclosures"] = (
        List[EnclosureWhere],
        Field(default_factory=list, description="every enclosure title, in document order, after the signature block"),
    )
    for kind in (
        "appendices",
        "glossary",
        "glossary_part_abbreviations",
        "glossary_part_definitions",
        "tables",
        "figures",
    ):
        fields[kind] = opt(FIXED_HINTS[kind])
    return create_model("BoundaryMap", **fields)


BoundaryMap = build_schema()
