"""Support functions for the docparser converter.

Four sections, in order:
  1. Emphasis      - bold/italic preservation across paragraph runs
  2. Markers       - inline shape detection from paragraph text
  3. Numbering     - Word numbering metadata + counter rendering
  4. Tables        - cell dedup, content-vs-data classification, markdown rendering

Each section is self contained. The main file imports specific names from here.
"""

import re

from docx.oxml.ns import qn


# =============================================================================
# 1. Emphasis
# =============================================================================
# Word stores bold/italic on each "run" within a paragraph (a run is a stretch
# of text with consistent formatting). We wrap the inner text in markdown
# emphasis markers and keep whitespace OUTSIDE the markers so adjacent text
# doesn't accidentally collide with the asterisks.

def format_with_emphasis(paragraph):
    formatted_parts = []
    for run in paragraph.runs:
        run_text = run.text
        if not run_text or not run_text.strip():
            formatted_parts.append(run_text)
            continue
        leading_whitespace = run_text[:len(run_text) - len(run_text.lstrip())]
        trailing_whitespace = run_text[len(run_text.rstrip()):]
        inner_text = run_text.strip()
        if run.bold and run.italic:
            formatted_parts.append(f'{leading_whitespace}***{inner_text}***{trailing_whitespace}')
        elif run.bold:
            formatted_parts.append(f'{leading_whitespace}**{inner_text}**{trailing_whitespace}')
        elif run.italic:
            formatted_parts.append(f'{leading_whitespace}*{inner_text}*{trailing_whitespace}')
        else:
            formatted_parts.append(run_text)
    combined = ''.join(formatted_parts) if formatted_parts else paragraph.text
    # Adjacent runs of the same style sometimes collide and produce **** or ******
    return re.sub(r'\*{4,6}', '', combined)


# =============================================================================
# 2. Markers
# =============================================================================
# We look at the start of each paragraph for things like "1.", "(a)",
# "C4.1.1.", and canonicalize to a shape pattern. Order in which unique shapes
# first appear in the doc IS the depth hierarchy: first shape -> depth 1,
# second shape -> depth 2, and so on. This is the strategy that catches
# hand-numbered DoD docs (DLM manuals, DoDIs, FMR-style outlines) where Word
# stored no metadata because the author typed the markers themselves.

INLINE_MARKER_PATTERN = re.compile(
    r'^[\(\[]?'
    r'(?:[A-Za-z]*\d+|[A-Za-z]+)'
    r'(?:[.\-:](?:[A-Za-z]*\d+|[A-Za-z]+))*'
    r'[\)\]]?[.:\)]?'
    r'(?=[ \t]|$)'
)

BULLET_CHARS = set('-*\u2022\u2023\u25e6\u2043\u2219')
SEPARATOR_CHARS = set('.-:()[]')
SHAPE_TOKENS = ('<N>', '<a>', '<A>', '<i>', '<I>')


def classify_letter_run(letters):
    # Multi-letter Roman numerals like "II" or "iii" -> <I>/<i>
    # Single letters like "a" or "B" -> <A>/<a>
    # Anything else (e.g. "C" in C4.1.1, "AP" in AP2.2.1) is kept literal
    if len(letters) >= 2 and all(c in 'IVXLCDM' for c in letters):
        return '<I>'
    if len(letters) >= 2 and all(c in 'ivxlcdm' for c in letters):
        return '<i>'
    if len(letters) == 1:
        return '<a>' if letters.islower() else '<A>'
    return letters


def canonicalize_marker_shape(marker):
    # Walk the marker character by character. Collapse digit runs into <N>,
    # letter runs into a shape token via classify_letter_run, and keep any
    # other characters (dots, parens, dashes) literal.
    # Trailing '.' or ':' is stripped so that 'C4.1.1' and 'C4.1.1.' end up
    # with the same shape and therefore the same depth.
    # Digit runs starting with '0' are kept literal so FMR codes like '010101'
    # don't collide with regular numbers like '1.'.
    canonical_parts = []
    cursor = 0
    while cursor < len(marker):
        current_char = marker[cursor]
        if current_char.isdigit():
            run_end = cursor
            while run_end < len(marker) and marker[run_end].isdigit():
                run_end += 1
            digit_run = marker[cursor:run_end]
            canonical_parts.append(digit_run if digit_run.startswith('0') else '<N>')
            cursor = run_end
        elif current_char.isalpha():
            run_end = cursor
            while run_end < len(marker) and marker[run_end].isalpha():
                run_end += 1
            canonical_parts.append(classify_letter_run(marker[cursor:run_end]))
            cursor = run_end
        else:
            canonical_parts.append(current_char)
            cursor += 1
    return ''.join(canonical_parts).rstrip('.:')


def detect_inline_marker(paragraph_text):
    """Returns (raw_marker, shape_pattern, remainder, is_bullet) or None.

    Filters out common false positives: phone numbers like 703-767-2117,
    inline abbreviations like 'e.g.,' or 'i.e.,', dates like '12 September
    2012', DLA codes like 'J-627', and anything suspiciously long.
    """
    if not paragraph_text:
        return None
    stripped = paragraph_text.lstrip('\t ')
    if not stripped:
        return None

    # Bullet character followed by whitespace
    if stripped[0] in BULLET_CHARS and len(stripped) > 1 and stripped[1] in ' \t':
        return stripped[0], 'bullet', stripped[2:].lstrip(), True

    pattern_match = INLINE_MARKER_PATTERN.match(stripped)
    if not pattern_match:
        return None

    raw_marker = pattern_match.group(0)
    remainder = stripped[pattern_match.end():].lstrip()

    # False-positive filters
    if remainder.startswith(','):
        return None  # "e.g.," / "i.e.," style abbreviations
    if len(raw_marker) > 40:
        return None  # suspiciously long, probably not a marker
    if not remainder.strip():
        return None  # empty content after marker (DLA codes like 'J-627')
    if not any(separator in raw_marker for separator in SEPARATOR_CHARS):
        return None  # plain word with no separator, not a marker

    shape_pattern = canonicalize_marker_shape(raw_marker)
    if not any(token in shape_pattern for token in SHAPE_TOKENS):
        return None  # shape contains no structural tokens, not a marker

    return raw_marker, shape_pattern, remainder, False


# =============================================================================
# 3. Numbering
# =============================================================================
# When Word renders a numbered or bulleted list, the marker text ('1.', 'a.',
# '(1)', '•') is NOT stored on the paragraph. It lives in numbering.xml and
# gets generated at display time. We extract:
#   - which (num_id, ilvl) pairs are bullets
#   - the format ('decimal', 'lowerLetter', 'lowerRoman', etc.) per level
#   - the lvlText template like '%1.', '(%1)', or '%2.%3' per level
# Then for each numbered paragraph we maintain a counter and substitute it
# into the template to get '1.', 'a.', '(1)', '1.a.' etc.
#
# Some docs (treasury memo) chain abstractNum A -> styleLink "name" ->
# abstractNum B. We resolve that indirection once during loading.

def load_numbering_data(document):
    """Returns {num_id: {ilvl: {'numFmt', 'lvlText', 'is_bullet'}}}."""
    try:
        numbering_root = document.part.numbering_part.element
    except (AttributeError, NotImplementedError):
        return {}

    abstract_levels = {}            # abstract_id -> {ilvl: level_data}
    style_link_to_abstract = {}     # named link -> abstract_id
    abstract_to_linked_style = {}   # abstract_id -> named link to follow

    for abstract in numbering_root.findall(qn('w:abstractNum')):
        abstract_id = abstract.get(qn('w:abstractNumId'))
        levels = {}
        for level in abstract.findall(qn('w:lvl')):
            ilvl = level.get(qn('w:ilvl'))
            num_format_element = level.find(qn('w:numFmt'))
            level_text_element = level.find(qn('w:lvlText'))
            num_format = num_format_element.get(qn('w:val')) if num_format_element is not None else 'decimal'
            level_text = level_text_element.get(qn('w:val')) if level_text_element is not None else ''
            levels[ilvl] = {
                'numFmt': num_format,
                'lvlText': level_text,
                'is_bullet': num_format in ('bullet', 'none'),
            }
        abstract_levels[abstract_id] = levels

        style_link_element = abstract.find(qn('w:styleLink'))
        if style_link_element is not None:
            style_link_to_abstract[style_link_element.get(qn('w:val'))] = abstract_id
        num_style_link_element = abstract.find(qn('w:numStyleLink'))
        if num_style_link_element is not None:
            abstract_to_linked_style[abstract_id] = num_style_link_element.get(qn('w:val'))

    # Resolve indirection: abstract A's level data may live in abstract B
    for abstract_id, linked_name in abstract_to_linked_style.items():
        target_abstract_id = style_link_to_abstract.get(linked_name)
        if target_abstract_id and not abstract_levels.get(abstract_id) and target_abstract_id in abstract_levels:
            abstract_levels[abstract_id] = abstract_levels[target_abstract_id]

    num_id_to_levels = {}
    for num in numbering_root.findall(qn('w:num')):
        num_id = num.get(qn('w:numId'))
        abstract_reference = num.find(qn('w:abstractNumId'))
        if abstract_reference is not None:
            num_id_to_levels[num_id] = abstract_levels.get(abstract_reference.get(qn('w:val')), {})
    return num_id_to_levels


def get_numbering_position(paragraph):
    """Returns (num_id, ilvl_string) or (None, None).

    Walks up the paragraph's style chain for up to 5 levels because some docs
    define numbering on the style rather than directly on the paragraph.
    """
    numbering_props = paragraph._p.find(qn('w:pPr') + '/' + qn('w:numPr'))
    if numbering_props is None:
        try:
            current_style = paragraph.style
            for _ in range(5):
                if current_style is None:
                    break
                numbering_props = current_style.element.find(qn('w:pPr') + '/' + qn('w:numPr'))
                if numbering_props is not None:
                    break
                current_style = current_style.base_style
        except Exception:
            pass

    if numbering_props is None:
        return None, None
    num_id_element = numbering_props.find(qn('w:numId'))
    ilvl_element = numbering_props.find(qn('w:ilvl'))
    num_id = num_id_element.get(qn('w:val')) if num_id_element is not None else None
    ilvl = ilvl_element.get(qn('w:val')) if ilvl_element is not None else '0'
    if num_id in (None, '0'):
        return None, None
    return num_id, ilvl


# Roman numeral conversion for lowerRoman/upperRoman levels
ROMAN_PAIRS = [
    (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
    (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
    (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
]


def integer_to_roman(value):
    if value <= 0:
        return ''
    output = []
    for amount, letters in ROMAN_PAIRS:
        while value >= amount:
            output.append(letters)
            value -= amount
    return ''.join(output)


def render_count_value(count, num_format):
    """Turn an integer counter into the formatted text Word would render."""
    if count <= 0:
        return ''
    if num_format == 'decimal':
        return str(count)
    if num_format == 'lowerLetter':
        return chr(ord('a') + (count - 1) % 26)
    if num_format == 'upperLetter':
        return chr(ord('A') + (count - 1) % 26)
    if num_format == 'lowerRoman':
        return integer_to_roman(count).lower()
    if num_format == 'upperRoman':
        return integer_to_roman(count)
    return str(count)


def render_numbering_marker(numbering_data, num_id, ilvl, counter_state):
    """Update the counter state and return the rendered marker like '1.', 'a.',
    '(1)', '1.a.'.

    Walk through what's happening:
      1. Increment the counter at (num_id, ilvl) since this paragraph just
         consumed one number at that level.
      2. Reset all DEEPER levels under the same num_id back to zero. Word
         restarts child counters whenever a parent advances (so the second
         "1." restarts at "1.a." not "1.c.").
      3. Look up the lvlText template for this level. Templates look like
         '%1.' or '(%1)' or '%2.%3.' where %N references level N-1's count.
      4. Substitute each %N with the current count at that level, formatted
         per that level's numFmt (decimal / lowerLetter / lowerRoman / etc).
      5. If a parent level was never directly used (count 0) but the template
         references it, treat its count as 1. This happens when a sub-list
         appears under a different numId than its visual parent (treasury's
         agenda does this).
    """
    if num_id not in numbering_data or ilvl not in numbering_data[num_id]:
        return ''

    # Step 1: increment counter at this level
    counter_state[(num_id, ilvl)] = counter_state.get((num_id, ilvl), 0) + 1

    # Step 2: reset deeper counters under the same num_id
    current_level_index = int(ilvl)
    deeper_keys = [
        key for key in counter_state
        if key[0] == num_id and int(key[1]) > current_level_index
    ]
    for key in deeper_keys:
        del counter_state[key]

    # Step 3: look up the template
    level_text_template = numbering_data[num_id][ilvl]['lvlText']
    if not level_text_template:
        return ''

    # Step 4: substitute %1, %2, ..., %N with formatted counts
    rendered_marker = level_text_template
    for level_index in range(current_level_index + 1):
        level_count = counter_state.get((num_id, str(level_index)), 0)
        # Step 5: parent level never advanced? treat as 1 so '%1.%2.' renders
        # as '1.a.' instead of '.a.' when a sub-list crosses num_id boundaries
        if level_count == 0 and level_index < current_level_index:
            level_count = 1
        level_format = numbering_data[num_id].get(str(level_index), {}).get('numFmt', 'decimal')
        rendered_marker = rendered_marker.replace(
            f'%{level_index + 1}',
            render_count_value(level_count, level_format),
        )
    return rendered_marker


# =============================================================================
# 4. Tables
# =============================================================================
# python-docx returns the SAME _tc element for every column of a horizontally
# merged cell, so iterating row.cells naively will duplicate the content.
# We dedup by _tc identity.
#
# A "content table" is one whose cells contain structural paragraphs (with
# inline markers or numPr). These get descended into so that their list
# structure shows up in the output. Other tables render as flat markdown.

def get_unique_cells_in_row(row):
    seen_cell_elements = []
    unique_cells = []
    for cell in row.cells:
        if cell._tc not in seen_cell_elements:
            seen_cell_elements.append(cell._tc)
            unique_cells.append(cell)
    return unique_cells


def table_contains_structured_paragraphs(table, numbering_data):
    for row in table.rows:
        for cell in get_unique_cells_in_row(row):
            for paragraph in cell.paragraphs:
                if detect_inline_marker(paragraph.text):
                    return True
                num_id, _ = get_numbering_position(paragraph)
                if num_id is not None and num_id in numbering_data:
                    return True
    return False


def format_table_as_markdown(table):
    rows_of_text = [
        [cell.text.strip().replace('\n', ' ') for cell in get_unique_cells_in_row(row)]
        for row in table.rows
    ]
    if not rows_of_text:
        return ''
    column_count = max(len(row) for row in rows_of_text)
    pad_to_width = lambda row: (row + [''] * (column_count - len(row)))[:column_count]
    output_lines = [
        '| ' + ' | '.join(pad_to_width(rows_of_text[0])) + ' |',
        '| ' + ' | '.join('---' for _ in range(column_count)) + ' |',
    ]
    output_lines += ['| ' + ' | '.join(pad_to_width(row)) + ' |' for row in rows_of_text[1:]]
    return '\n'.join(output_lines)
