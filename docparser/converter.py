"""Convert .docx documents to markdown.

Strategy: each paragraph is classified by which signal layer matches first.
Order is important because some paragraphs have multiple signals.

  1. Heading style       (Heading 1-6, Title, Subtitle) -> use directly
  2. Inline marker shape ('1.', 'C4.1.1.', '(a)') -> depth by first-
                          appearance order. Catches hand-numbered DoD docs.
  3. Word numbering      (numPr) -> ilvl gives depth, lvlText gives the
                          rendered marker like '1.', 'a.', '(1)'. Catches
                          Word-managed numbered/bulleted lists.

Tables: data tables render as markdown tables. Content tables (cells with
list items) are descended into. Fully-merged rows promote their first plain
paragraph to a heading - this is what catches DoD appendices where the
AP2.2.X section markers live inside a merged cell.

Usage:
    from docparser import convert
    markdown = convert('/path/to/file.docx')
"""

import re

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .utils import (
    detect_inline_marker,
    format_table_as_markdown,
    format_with_emphasis,
    get_numbering_position,
    get_unique_cells_in_row,
    load_numbering_data,
    render_numbering_marker,
    table_contains_structured_paragraphs,
)


def heading_style_level(paragraph):
    """Returns 1-6 if the paragraph uses a Heading/Title/Subtitle style, else None."""
    style_name = (paragraph.style.name or '').lower()
    for heading_level in range(1, 7):
        if style_name.startswith(f'heading {heading_level}'):
            return heading_level
    if style_name == 'title':
        return 1
    if style_name == 'subtitle':
        return 2
    return None


def classify_paragraph(paragraph, numbering_data, counter_state):
    """Inspect one paragraph and return an item dict describing what it is.

    Walk through the three signal layers in priority order:
      1. Heading style wins outright. If the author typed a Heading 1, that's
         what they meant. No depth tracking, no marker detection needed.
      2. Inline marker shape next. This catches paragraphs where the author
         typed the marker themselves (DLM manuals: 'C4.1.1.', DoDIs: '1.',
         FMR: '010101.A.1.a'). Depth is assigned later from the order in
         which unique shapes first appeared in the doc.
      3. Word numbering metadata last. This catches paragraphs where Word
         is generating the marker for us. We render the marker text from
         the lvlText template, increment the counter, and the depth comes
         from ilvl directly.

    Falls through to 'body' if none of the layers match.
    """
    paragraph_text = paragraph.text
    if not paragraph_text.strip():
        return {'kind': 'blank'}

    matched_heading_level = heading_style_level(paragraph)
    if matched_heading_level:
        return {
            'kind': 'heading',
            'depth': matched_heading_level,
            'text': format_with_emphasis(paragraph).strip(),
        }

    inline_marker = detect_inline_marker(paragraph_text)
    if inline_marker:
        raw_marker, shape_pattern, _, is_bullet = inline_marker
        if is_bullet:
            return {'kind': 'bullet', 'text': format_with_emphasis(paragraph).strip()}
        return {
            'kind': 'list-shape',
            'shape': shape_pattern,
            'text': format_with_emphasis(paragraph).strip(),
        }

    num_id, ilvl = get_numbering_position(paragraph)
    if num_id is not None and num_id in numbering_data:
        level_info = numbering_data[num_id].get(ilvl, {})
        if level_info.get('is_bullet', False):
            return {'kind': 'bullet', 'text': format_with_emphasis(paragraph).strip()}
        rendered_marker = render_numbering_marker(numbering_data, num_id, ilvl, counter_state)
        return {
            'kind': 'list-numbered',
            'depth': int(ilvl) + 1,
            'rendered_marker': rendered_marker,
            'text': format_with_emphasis(paragraph).strip(),
        }

    return {'kind': 'body', 'text': format_with_emphasis(paragraph)}


def descend_merged_cell(cell, numbering_data, counter_state, items_collected, visit_function):
    """When a row is fully merged into one cell, the cell is acting as a
    section container. Promote its first plain paragraph (the one without
    its own classification signal) to a depth-2 heading. This is what
    catches v4a2's AP2.2.X items, which live as plain text inside merged
    cells with no inline marker and no numPr.

    Walk:
      1. Scan the cell's children for the first non-blank paragraph.
      2. Check if that paragraph has its own classification signal already
         (inline marker or numPr). If yes, leave it alone, normal walking
         will pick it up. If no, mark its index for promotion.
      3. Iterate children, emitting the promoted paragraph as a heading and
         passing everything else to the normal visit function.
    """
    cell_children = list(cell._tc.iterchildren())

    promoted_index = -1
    for child_index, child_element in enumerate(cell_children):
        if child_element.tag != qn('w:p'):
            continue
        candidate_paragraph = Paragraph(child_element, cell)
        if not candidate_paragraph.text.strip():
            continue
        if not detect_inline_marker(candidate_paragraph.text):
            paragraph_num_id, _ = get_numbering_position(candidate_paragraph)
            if not (paragraph_num_id is not None and paragraph_num_id in numbering_data):
                promoted_index = child_index
        break

    for child_index, child_element in enumerate(cell_children):
        if child_index == promoted_index:
            promoted_paragraph = Paragraph(child_element, cell)
            items_collected.append({
                'kind': 'heading',
                'depth': 2,
                'text': format_with_emphasis(promoted_paragraph).strip(),
            })
        else:
            visit_function(child_element, cell)


def extract_items(document):
    """Walk the document body and return a flat list of classified items.

    Walk:
      1. Load Word numbering metadata up front (we need it for both bullet
         detection and rendering numbered markers).
      2. Set up an empty counter state dict that classify_paragraph will
         mutate as it encounters numbered paragraphs.
      3. Iterate body elements. Paragraphs go through classify_paragraph.
         Tables either render as data tables, or descend if they contain
         structural paragraphs.
      4. After collection, assign final depth values to inline-marker shapes
         based on the order in which unique shapes first appeared.
    """
    numbering_data = load_numbering_data(document)
    counter_state = {}
    items_collected = []

    def visit(element, parent):
        if element.tag == qn('w:p'):
            paragraph = Paragraph(element, parent)
            items_collected.append(classify_paragraph(paragraph, numbering_data, counter_state))
            return

        if element.tag != qn('w:tbl'):
            return

        table = Table(element, parent)
        if not table_contains_structured_paragraphs(table, numbering_data):
            items_collected.append({
                'kind': 'table',
                'text': format_table_as_markdown(table),
            })
            return

        # Content table: descend into cells, promoting fully-merged rows
        for row in table.rows:
            unique_cells = get_unique_cells_in_row(row)
            if len(unique_cells) == 1:
                descend_merged_cell(
                    unique_cells[0], numbering_data, counter_state, items_collected, visit,
                )
            else:
                for cell in unique_cells:
                    for child_element in cell._tc.iterchildren():
                        visit(child_element, cell)

    for body_element in document.element.body.iterchildren():
        visit(body_element, document)

    # Assign depth to each list-shape based on order of first appearance.
    # The first unique shape we saw becomes depth 1, second becomes 2, etc.
    shape_to_depth = {}
    for item in items_collected:
        if item['kind'] == 'list-shape' and item['shape'] not in shape_to_depth:
            shape_to_depth[item['shape']] = len(shape_to_depth) + 1
    for item in items_collected:
        if item['kind'] == 'list-shape':
            item['depth'] = shape_to_depth[item['shape']]

    return items_collected


def render_item_to_markdown_lines(item):
    """Turn one classified item dict into the corresponding markdown line(s).

    Each item kind has its own rendering rule:
      - blank       -> a single empty line (collapsed later)
      - body        -> the text itself
      - bullet      -> '- text'
      - table       -> the rendered markdown table with blank lines around it
      - heading     -> '#' x depth + text
      - list-shape  -> heading at depth+1 (a top-level shape becomes ##)
      - list-numbered -> heading at depth+1 with the rendered marker
                       prepended ('## 1. Agenda' instead of '## Agenda')
    """
    item_kind = item['kind']
    if item_kind == 'blank':
        return ['']
    if item_kind == 'body':
        return [item['text']]
    if item_kind == 'bullet':
        return ['- ' + item['text']]
    if item_kind == 'table':
        return ['', item['text'], '']

    if item_kind in ('heading', 'list-shape'):
        # heading uses depth as-is; list-shape shifts down by 1 since a
        # depth-1 list item should be ## (H2), not # (H1)
        depth_offset = 0 if item_kind == 'heading' else 1
        hash_marks = '#' * min(item['depth'] + depth_offset, 6)
        return ['', f'{hash_marks} {item["text"]}', '']

    if item_kind == 'list-numbered':
        # Prepend the rendered marker so the frontend sees '## 1. Agenda'
        # instead of just '## Agenda'. The marker is something Word would
        # have rendered itself ('1.', 'a.', '(1)', '1.a.').
        hash_marks = '#' * min(item['depth'] + 1, 6)
        rendered_marker = item.get('rendered_marker', '')
        if rendered_marker:
            return ['', f'{hash_marks} {rendered_marker} {item["text"]}', '']
        return ['', f'{hash_marks} {item["text"]}', '']

    return []


def convert(docx_path):
    """Read a .docx and return its markdown representation."""
    document = Document(str(docx_path))
    items_collected = extract_items(document)

    output_lines = []
    for item in items_collected:
        for line in render_item_to_markdown_lines(item):
            # Don't emit consecutive blank lines
            if line == '' and output_lines and output_lines[-1] == '':
                continue
            output_lines.append(line)

    # Collapse any runs of more than 2 newlines down to exactly 2
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(output_lines)).strip()
