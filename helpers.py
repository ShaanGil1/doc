from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional
from docx import Document
from docx.oxml import OxmlElement, parse_xml   # build an element, or parse literal XML
from docx.oxml.ns import nsdecls, qn           # xmlns declarations / 'w:shd' -> '{uri}shd'
from docx.shared import Inches, Pt


# =========================================== #
# OPTIONS
# =========================================== #
# Incase other things are needed for whatever reasons
PAGE_SIZES_IN_INCHES = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}

# The default values here are what python-docx's built-in template uses
@dataclass
class DocxOptions:
    # page setup. Ignored entirely when you pass your own document=
    page: str = "letter"                    # key into PAGE_SIZES_IN_INCHES above
    margin_in: float = 1.0                  # same margin on all four sides

    # fonts
    body_font: Optional[str] = None         # None = keep the template's Calibri
    body_size_pt: Optional[float] = None    # None = keep the template's 11pt
    code_font: str = "Consolas"             # used for `code` and code blocks
    code_size_pt: float = 9.0

    # colors. Bare RRGGBB hex, no leading '#'. That is what OOXML wants
    link_color: str = "0563C1"              # Word's default hyperlink blue
    code_fill: str = "F2F2F2"               # code background
    quote_bar: str = "BFBFBF"               # vertical bar beside blockquotes
    table_header_fill: str = "EDEDED"       # header row background

    # input handling
    strip_front_matter: bool = True         # drop a leading --- ... --- block


# =========================================================================== #
# ELEMENT ORDERING
#
# THE PROBLEM: WordprocessingML is a SEQUENCE schema, not a set schema. The
# children of <w:pPr> must appear in one specific order
# =========================================================================== #
SCHEMA_CHILD_ORDER = {
    # paragraph properties: of these, we insert keepLines, numPr, pBdr, shd
    "pPr": (
        "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr "
        "suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap "
        "overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd "
        "snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc "
        "textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr "
        "sectPr pPrChange"
    ).split(),
    # run properties: of these, we insert rFonts, noProof, shd
    "rPr": (
        "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow "
        "emboss imprint noProof snapToGrid vanish webHidden color spacing w kern "
        "position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em "
        "lang eastAsianLayout specVanish oMath rPrChange"
    ).split(),
    # table cell properties: of these, we insert shd
    "tcPr": (
        "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar "
        "textDirection tcFitText vAlign hideMark headers tcPrChange"
    ).split(),
    # table row properties: of these, we insert tblHeader
    "trPr": (
        "cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight "
        "tblHeader tblCellSpacing jc hidden ins del trPrChange"
    ).split(),
}

def local_name(tag: str) -> str:
    """Strip the namespace off an element tag and return the bare name"""
    return tag.split("}")[-1].split(":")[-1]

def insert_in_schema_order(parent_element, new_element):
    """Insert new_element under parent_element at the position the schema wants"""
    expected_order = SCHEMA_CHILD_ORDER.get(local_name(parent_element.tag))
    if not expected_order:
        parent_element.append(new_element)
        return new_element
    try:
        our_rank = expected_order.index(local_name(new_element.tag))
    except ValueError:
        parent_element.append(new_element)
        return new_element

    for existing_child in parent_element:
        child_name = local_name(existing_child.tag)
        if child_name in expected_order and expected_order.index(child_name) > our_rank:
            existing_child.addprevious(new_element)
            return new_element

    parent_element.append(new_element)
    return new_element


def add_element(parent_element, tag: str, **attributes):
    """Create <tag a="1"/> and place it correctly under parent_element"""
    existing = parent_element.find(qn(tag))
    if existing is not None:
        return existing
    new_element = OxmlElement(tag)
    for attribute_name, value in attributes.items():
        new_element.set(qn("w:" + attribute_name), str(value))
    return insert_in_schema_order(parent_element, new_element)


def replace_element(parent_element, tag: str, replacement_element):
    """Remove any existing <tag> under parent_element"""
    existing = parent_element.find(qn(tag))
    if existing is not None:
        parent_element.remove(existing)
    return insert_in_schema_order(parent_element, replacement_element)


# Shading and borders
def set_shading(properties_element, fill_color: str):
    """Background fill for a paragraph, run or table cell. Used for code blocks, inline code and table headers"""
    replace_element(properties_element, "w:shd", parse_xml(
        '<w:shd %s w:val="clear" w:color="auto" w:fill="%s"/>'
        % (nsdecls("w"), fill_color)))


def shade_paragraph(paragraph, fill_color: str):
    """Shade a whole paragraph. Used for code blocks."""
    set_shading(paragraph._p.get_or_add_pPr(), fill_color)


def shade_run(run, fill_color: str):
    """Shade one run of text. Used for `inline code`."""
    set_shading(run._element.get_or_add_rPr(), fill_color)


def shade_table_cell(cell, fill_color: str):
    """Shade a table cell. Used for header rows."""
    set_shading(cell._tc.get_or_add_tcPr(), fill_color)


def set_paragraph_borders(paragraph, edges: dict):
    """Draw borders on a paragraph"""
    side_elements = "".join(
        '<w:%s w:val="%s" w:sz="%d" w:space="%d" w:color="%s"/>' % (
            side_name, spec.get("val", "single"), spec.get("sz", 6),
            spec.get("space", 4), spec.get("color", "auto"))
        for side_name in ("top", "left", "bottom", "right")
        if (spec := edges.get(side_name)) is not None)
    replace_element(paragraph._p.get_or_add_pPr(), "w:pBdr", parse_xml(
        "<w:pBdr %s>%s</w:pBdr>" % (nsdecls("w"), side_elements)))


def keep_paragraph_together(paragraph):
    """Ask Word not to split this paragraph across a page break"""
    add_element(paragraph._p.get_or_add_pPr(), "w:keepLines")


def apply_monospace_font(run, font_name: str, size_pt: float):
    """Make a run monospace, mainly used for code blocks"""
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run_properties = run._element.get_or_add_rPr()

    replace_element(run_properties, "w:rFonts", parse_xml(
        '<w:rFonts %s w:ascii="%s" w:hAnsi="%s" w:cs="%s" w:eastAsia="%s"/>'
        % ((nsdecls("w"),) + (font_name,) * 4)))

    add_element(run_properties, "w:noProof")


def mark_as_repeating_header(table_row):
    """Mark a row as a header so Word repeats it at the top of every page"""
    add_element(table_row._tr.get_or_add_trPr(), "w:tblHeader")


# =========================================================================== #
# LIST NUMBERING
# numbering lives in its own part of the zip, word/numbering.xml, intwo layers:
#
#   <w:abstractNum>  defining 9 nesting levels: what each level's marker looks like, 
#                    where it starts, how far it indents.
#   <w:num>          pointing at one abstractNum. Its numId is what
#                    a paragraph actually references
# =========================================================================== #

BULLET_MARKERS = [("\uf0b7", "Symbol"), ("o", "Courier New"), ("\uf0a7", "Wingdings")]
ORDERED_FORMATS = ["decimal", "lowerLetter", "lowerRoman"]   # 1. / a. / i.
NESTING_LEVELS = 9              # Word supports exactly 9 nesting levels
TWIPS_PER_LEVEL = 360           # 360 twips = 0.25 inch of extra indent per level


class Numbering:
    """Owns word/numbering.xml for one document"""
    def __init__(self, document):
        self.numbering_root = document.part.numbering_part.element
        self.shared_bullet_num_id: Optional[int] = None
        self.next_abstract_id = 1 + max(
            (int(definition.get(qn("w:abstractNumId")))
             for definition in self.numbering_root.findall(qn("w:abstractNum"))
             if definition.get(qn("w:abstractNumId")) is not None),
            default=-1,
        )

    def create_list(self, is_ordered: bool, start_number: int = 1) -> int:
        """Return a numId for a brand new list."""
        if not is_ordered:
            if self.shared_bullet_num_id is None:
                self.shared_bullet_num_id = self.numbering_root.add_num(
                    self.create_abstract_definition(is_ordered=False)).numId
            return self.shared_bullet_num_id
        return self.numbering_root.add_num(
            self.create_abstract_definition(True, start_number)).numId

    @staticmethod
    def apply_to_paragraph(paragraph, num_id: int, nesting_level: int):
        """Attach a paragraph to list `num_id` at depth `nesting_level`"""
        replace_element(paragraph._p.get_or_add_pPr(), "w:numPr", parse_xml(
            '<w:numPr %s><w:ilvl w:val="%d"/><w:numId w:val="%d"/></w:numPr>'
            % (nsdecls("w"), nesting_level, num_id)))

    def create_abstract_definition(self, is_ordered: bool, start_number: int = 1) -> int:
        """Build one <w:abstractNum> covering all 9 levels. Returns its id."""
        definition_id = self.next_abstract_id
        self.next_abstract_id += 1

        definition = OxmlElement("w:abstractNum")
        definition.set(qn("w:abstractNumId"), str(definition_id))
        add_element(definition, "w:multiLevelType", val="hybridMultilevel")

        for level in range(NESTING_LEVELS):
            # Only the outermost level 
            definition.append(self.build_level_definition(
                level, is_ordered, start_number if level == 0 else 1))

        existing_definitions = self.numbering_root.findall(qn("w:abstractNum"))
        if existing_definitions:
            existing_definitions[-1].addnext(definition)
        else:
            self.numbering_root.insert(0, definition)
        return definition_id

    @staticmethod
    def build_level_definition(level: int, is_ordered: bool, start_number: int):
        """One <w:lvl>: everything about how depth `level` looks"""
        if is_ordered:
            number_format, marker_text, marker_font_xml = (
                ORDERED_FORMATS[level % 3], "%%%d." % (level + 1), "")
        else:
            marker_font = BULLET_MARKERS[level % 3][1]
            number_format, marker_text = "bullet", BULLET_MARKERS[level % 3][0]
            marker_font_xml = (
                '<w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s" w:hint="default"/>'
                '</w:rPr>' % (marker_font, marker_font))
        left_indent = TWIPS_PER_LEVEL * (level + 1)

        return parse_xml(
            '<w:lvl %s w:ilvl="%d">'
            '<w:start w:val="%d"/>'
            '<w:numFmt w:val="%s"/>'
            '<w:lvlText w:val="%s"/>'
            '<w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="%d" w:hanging="%d"/></w:pPr>'
            '%s'
            '</w:lvl>'
            % (nsdecls("w"), level, start_number, number_format, marker_text,
               left_indent, TWIPS_PER_LEVEL, marker_font_xml))


# DOCUMENT SETUP
def new_document(opts: DocxOptions):
    """Create an empty document, w/ all the settings applied"""
    document = Document()
    page_width, page_height = PAGE_SIZES_IN_INCHES.get(
        opts.page.lower(), PAGE_SIZES_IN_INCHES["letter"])
    
    for section in document.sections:
        section.page_width = Inches(page_width)
        section.page_height = Inches(page_height)
        section.left_margin = section.right_margin = Inches(opts.margin_in)
        section.top_margin = section.bottom_margin = Inches(opts.margin_in)
    normal_style = document.styles["Normal"]

    if opts.body_font:
        normal_style.font.name = opts.body_font
        fonts = normal_style.element.rPr.rFonts
        for character_range in ("ascii", "hAnsi", "cs", "eastAsia"):
            fonts.set(qn("w:" + character_range), opts.body_font)

    if opts.body_size_pt:
        normal_style.font.size = Pt(opts.body_size_pt)
    zoom = document.settings.element.find(qn("w:zoom"))

    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")
    return document

def document_to_bytes(document) -> bytes:
    """Serialise to bytes in memory"""
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()