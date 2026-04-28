import math
import re

import mammoth
from docx import Document
from docx.oxml.ns import qn
from markdownify import markdownify

from .llm import build_payload, build_retry_message

from .models import (
    Sections_LLM,
    MatchedSection,
    MAX_RETRIES,
    MIN_SECTION_WORDS,
    MAX_SECTION_WORDS,
    MAX_DOCUMENT_WORDS,
)


# Document extraction
def convert_to_markdown(docx_path):
    # Convert .docx to HTML with mammoth, then HTML to markdown with markdownify.
    with open(str(docx_path), 'rb') as docx_file:
        html = mammoth.convert_to_html(docx_file).value
    return markdownify(html, heading_style='ATX')


def extract_paragraph_depths(docx_path):
    # Walk the .docx and return depth metadata for every non-empty paragraph.
    # Returns a list of {'text': str, 'depth': int or None}
    # The 'depth' value is the structural nesting level of the paragraph,
    # derived from .docx XML using ilvl and leading-tab count:

    document = Document(str(docx_path))
    rows = []

    # Top-level paragraphs
    for paragraph in document.paragraphs:
        row = paragraph_to_row(paragraph)
        if row is not None:
            rows.append(row)

    # For tables 
    def walk_table(table):
        for table_row in table.rows:
            seen_cells = []
            for cell in table_row.cells:
                if cell._tc in seen_cells:
                    continue
                seen_cells.append(cell._tc)
                for paragraph in cell.paragraphs:
                    row = paragraph_to_row(paragraph)
                    if row is not None:
                        rows.append(row)
                for nested_table in cell.tables:
                    walk_table(nested_table)

    for table in document.tables:
        walk_table(table)

    return rows

# Grab the text and depth for a paragraph, Trim to help LLM w/ overall struct 
def paragraph_to_row(paragraph):
    text = paragraph.text.strip()
    if not text:
        return None

    list_level = word_list_level(paragraph)
    tab_count = len(paragraph.text) - len(paragraph.text.lstrip('\t'))

    if list_level is None and tab_count == 0:
        depth = None
    else:
        depth = max(list_level or 0, tab_count)

    return {'text': text[:100], 'depth': depth}

# ilvl values
def word_list_level(paragraph):
    paragraph_props = paragraph._p.find(qn('w:pPr'))
    if paragraph_props is None:
        return None
    num_props = paragraph_props.find(qn('w:numPr'))
    if num_props is None:
        return None
    ilvl_element = num_props.find(qn('w:ilvl'))
    if ilvl_element is None:
        return None
    raw_value = ilvl_element.get(qn('w:val'))
    try:
        return int(raw_value) if raw_value is not None else None
    except ValueError:
        return None

# LLM call + line matching

# Call the LLM to get section boundaries, with retry on no-match.
def request_sections(llm, payload, max_retries=MAX_RETRIES):

    structured_llm = llm.with_structured_output(Sections_LLM)
    user_message = payload['user_message']
    lines = payload['markdown_lines']
    best_attempt_sections = None
    best_attempt_match_count = 0

    for attempt in range(max_retries):
        try:
            response = structured_llm.invoke([
                ('system', payload['system']),
                ('user', user_message),
            ])
        except Exception:
            continue

        if response is None or not response.sections:
            continue

        all_sections = match_sections(response.sections, lines)
        match_count = sum(1 for s in all_sections if s.matched and s.match_text)

        if match_count > best_attempt_match_count:
            best_attempt_sections = all_sections
            best_attempt_match_count = match_count

        if match_count > 0:
            return all_sections

        user_message = build_retry_message(
            payload['user_message'], all_sections, attempt, max_retries,
        )

    if best_attempt_match_count > 0:
        return best_attempt_sections
    return []


def match_sections(ai_sections, lines):
    # Match the sections
    sections = []
    cursor = 0

    for item in ai_sections:
        match_text = item.section_match_text
        if not match_text:
            continue

        line_index = find_matching_line(match_text, lines, search_from=cursor)
        if line_index is None:
            sections.append(MatchedSection(item.title, -1, match_text, matched=False))
        else:
            sections.append(MatchedSection(item.title, line_index + 1, match_text, matched=True))
            cursor = line_index + 1

    matched_only = [s for s in sections if s.matched]
    # Some edge casing likely never triggers
    if not matched_only or matched_only[0].start_line > 1:
        sections.insert(0, MatchedSection('Introduction', 1, '', matched=True))
    return sections


def find_matching_line(match_text, lines, search_from=0):
    # Locate match_text in lines using a 3-stage fallback.

    stripped_match = match_text.strip()
    if not stripped_match:
        return None

    # exact line match
    for i in range(search_from, len(lines)):
        if lines[i].strip() == stripped_match:
            return i

    # substring match (handles LLM dropping '## ' prefix etc.).
    if len(stripped_match) >= 8:
        for i in range(search_from, len(lines)):
            stripped_line = lines[i].strip()
            if len(stripped_line) < 8:
                continue
            if stripped_match in lines[i] or stripped_line in stripped_match:
                return i

    # normalized match (whitespace/punctuation/case differences)
    normalized_match = re.sub(r'[^a-z0-9]', '', stripped_match.lower())
    if len(normalized_match) >= 4:
        for i in range(search_from, len(lines)):
            normalized_line = re.sub(r'[^a-z0-9]', '', lines[i].lower())
            if normalized_line == normalized_match:
                return i
    return None

# Post-processing:
def section_is_mostly_table(content):
    # Heuristic: if >= 70% markdown table and we should avoid splitting it

    table_words = 0
    total_words = 0
    for line in content.split('\n'):
        word_count = len(line.split())
        total_words += word_count
        if line.strip().startswith('|'):
            table_words += word_count
    if total_words == 0:
        return False
    return table_words / total_words >= 0.7


def merge_and_split_sections(matched_sections, lines, min_words, max_words):
    # Merge sections smaller than min_words into neighbors, then split sections larger than max_words at sentence boundaries
    sections = sorted(
        [s for s in matched_sections if s.matched],
        key=lambda s: s.start_line,
    )
    if not sections:
        return []

    # Helper
    def words_at(i):
        start = sections[i].start_line - 1
        end = sections[i + 1].start_line - 1 if i + 1 < len(sections) else len(lines)
        return sum(len(line.split()) for line in lines[start:end])

    # Merge undersized sections
    if len(sections) > 1:
        i = 0
        while i < len(sections):
            if words_at(i) >= min_words:
                i += 1
                continue
            if i == 0 and len(sections) > 1:
                # First section too small - extend the next section back to line 1
                next_section = sections[1]
                sections[1] = MatchedSection(
                    title=next_section.title,
                    start_line=sections[0].start_line,
                    match_text=next_section.match_text,
                    matched=True,
                )
                sections.pop(0)
            elif i > 0:
                sections.pop(i)  # fold this section back into the previous one
            else:
                i += 1

    # Split oversized at sentence boundaries
    output = []
    for index, section in enumerate(sections):
        start = section.start_line - 1
        end = sections[index + 1].start_line - 1 if index + 1 < len(sections) else len(lines)
        content = '\n'.join(lines[start:end]).strip()

        # Table-dominant sections are kept whole regardless of word count
        if section_is_mostly_table(content):
            output.append({'title': section.title, 'content': content})
            continue

        sentence_seperator = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

        sentences = [s for s in sentence_seperator.split(content) if s.strip()]
        total_words = sum(len(s.split()) for s in sentences)

        if total_words <= max_words or len(sentences) < 2:
            output.append({'title': section.title, 'content': content})
            continue

        # Pick split points at sentence boundaries closest to even word distribution
        num_parts = math.ceil(total_words / max_words)
        target = total_words / num_parts
        cumulative = [0]
        for s in sentences:
            cumulative.append(cumulative[-1] + len(s.split()))

        split_points = [0]
        for part_index in range(1, num_parts):
            ideal = part_index * target
            previous = split_points[-1]
            best = previous + 1
            best_diff = abs(cumulative[best] - ideal)
            for candidate in range(previous + 2, len(sentences)):
                diff = abs(cumulative[candidate] - ideal)
                if diff < best_diff:
                    best_diff = diff
                    best = candidate
            split_points.append(best)
        split_points.append(len(sentences))

        for n in range(len(split_points) - 1):
            piece = ' '.join(sentences[split_points[n]:split_points[n + 1]])
            output.append({
                'title': f'{section.title} ({n + 1}/{num_parts})',
                'content': piece,
            })

    return output

# Main pipeline
def run_sectioning(
    llm,
    docx_path,
    max_retries=MAX_RETRIES,
    max_words=MAX_DOCUMENT_WORDS,
    min_section_words=None,
    max_section_words=None,
):
    # Convert a .docx into editable sections. The whole pipeline.
    # 1. convert_to_markdown() turns the .docx into markdown text.
    # 2. build_payload() converts the docx, extracts metadata, assembles the LLM user message.
    # 3. request_sections() calls the LLM with retries on no-match.
    # 4. merge_and_split_sections() merges undersized sections into neighbors and splits oversized

    markdown = convert_to_markdown(str(docx_path))
    metadata_rows = extract_paragraph_depths(docx_path)
    payload = build_payload(markdown, metadata_rows, max_words=max_words)
    matched_sections = request_sections(llm, payload, max_retries=max_retries)

    if not matched_sections:
        return [{'title': 'Document', 'content': '\n'.join(payload['markdown_lines'])}]

    # Adaptive thresholds: shrink for short docs so legitimate sections
    adaptive_min, adaptive_max = adaptive_thresholds(payload['word_count'])
    final_min = min_section_words if min_section_words is not None else adaptive_min
    final_max = max_section_words if max_section_words is not None else adaptive_max

    return merge_and_split_sections(
        matched_sections,
        payload['markdown_lines'],
        min_words=final_min,
        max_words=final_max,
    )

# Change if params feel off
def adaptive_thresholds(total_words):
    min_words = min(MIN_SECTION_WORDS, max(20, total_words // 15))
    max_words = min(MAX_SECTION_WORDS, max(150, total_words // 5))
    return min_words, max_words