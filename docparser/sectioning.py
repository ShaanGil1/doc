"""
sectioning.py

Split a .docx into editable top-level sections using docparser.convert
as the parser and an LLM with structured output to identify the
section boundaries.

The main flow lives in run_sectioning() near the top of this file.
Reading that function gives you the whole pipeline. Everything below
is the helpers it calls into.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .converter import convert as docx_to_markdown


# =====================================================================
# Configuration
# =====================================================================
# Edit these in one place. Function signatures pull defaults from here,
# and internal calls use the parameters (not hardcoded values), so a
# change here flows through the whole pipeline.
#
# Per-call overrides still work:
#   run_sectioning(llm, path, max_section_words=300)

MAX_DOCUMENT_WORDS = 5000   # hard cap on .docx size; ValueError if exceeded
MIN_SECTION_WORDS = 60      # sections under this get merged into a neighbor
MAX_SECTION_WORDS = 400     # sections over this get split at sentence boundaries
MAX_RETRIES = 3             # retries when zero AI sections match
MIN_SUBSTRING_LENGTH = 8    # AI match_text minimum length for substring fallback


# =====================================================================
# Structured output models
# =====================================================================
# These classes describe what the LLM must return. langchain wraps them
# into a function-calling schema via with_structured_output().

class SectionItem(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=100,
        description=(
            'Short descriptive name for this section, 3-7 words ideal. '
            'Used for display and navigation. Prefer the original heading '
            'text when available, lightly cleaned up.'
        )
    )
    section_match_text: str = Field(
        min_length=MIN_SUBSTRING_LENGTH,
        description=(
            'EXACT text of a line from the document where this section '
            'starts. Used only for locating the section. Must be a '
            'verbatim copy with no changes. Must be at least '
            f'{MIN_SUBSTRING_LENGTH} characters long.'
        )
    )


class Sections(BaseModel):
    sections: list[SectionItem] = Field(
        min_length=1,
        max_length=50,
        description='List of section boundaries in document order.'
    )


# =====================================================================
# System prompt
# =====================================================================

SYSTEM_PROMPT = f"""\
You are a document structure analyzer. Given a markdown document, identify
top-level section boundaries for an editing workflow.

WORKFLOW CONTEXT:
These sections will be edited independently by a human writer. Each section
should be a coherent topic worth a focused editing pass - large enough to
hold a complete thought, small enough that the writer isn't overwhelmed.

CORE RULES:
- Output sections in document order. Never exceed 50 sections.
- Produce exactly ONE flat level of sections. No nesting.

SIZE GUIDANCE:
- Aim for {MIN_SECTION_WORDS}-{MAX_SECTION_WORDS} words per section. This is
  your goal range.
- Prioritize topic coherence over hitting the size target. If a topic
  naturally needs more space to be a complete thought, keep it whole.
  Oversized sections will be split automatically afterward at sentence
  boundaries, so don't force unnatural splits to hit a word count.
- Short sections (under {MIN_SECTION_WORDS} words) should be folded into
  a neighbor.

GRANULARITY GUIDANCE:
- When the document has multi-level numbering (e.g., 1, 1.1, 1.1.1, or
  C4.1, C4.1.1, C4.1.1.1), use SECOND-level numbering as section
  boundaries by default. Deeper subsections should be grouped under
  their parent, not split out.

KEEP THESE AS SINGLE SECTIONS (do not split apart):
- Tables of contents, lists of figures
- Definition/acronym lists, revision history, change logs
- Large tables
- Appendices (keep whole unless they have clear internal structure)
- Fold signature blocks into the final section.

PARSER LIMITATIONS:
The markdown was produced by a parser with known failure modes. The parser
uses # markers when it can detect structure from the source document, but
many documents use hand-typed numbering or bold formatting for structure
that doesn't translate to # markers. Watch for these patterns and treat
them as real section boundaries even when they appear without # markers:

1. Bolded standalone short lines that act as document divisions. The
   pattern (not specific words to match):
     **CHAPTER 4**
     **APPENDIX A**
     **PART III**
     **DIVISION 2.1**
   These are typically top-level headers that lost their # during parsing.

2. Lines starting with an alphanumeric code followed by a brief title.
   The pattern is: letter prefix (1-3 chars) + numbers + separators +
   title text. Examples (any letters, any numbers, this is the shape):
     **X1. PURPOSE**
     **AB2.3 SCOPE**
     **010101 GENERAL**
   The code is the section number; the text after is the section title.

3. Numbered Word-rendered markers in headings are normal, not noise. You
   may see lines like "## 1. Agenda" or "### a. Discuss" or
   "#### (1) This change". The "1.", "a.", "(1)" are markers the parser
   correctly preserved from Word's auto-numbering. Use the full line
   (including the marker) when reporting section_match_text.

TITLE GUIDANCE:
- Keep titles concise. 3-7 words is ideal.
- Use the original heading text when available, lightly cleaned. Don't
  pad titles with explanatory suffixes ("Process", "Information",
  "Reporting", "Procedures") unless those words appear in the original
  heading.

OUTPUT FORMAT:
For each section provide TWO separate fields:

- title: a short descriptive name. Display only. Can be paraphrased.

- section_match_text: used ONLY for locating the section. Must be the
  EXACT text of a single line from the document, copied VERBATIM. Do not
  paraphrase, truncate, or add or remove any characters. Even one
  character off will fail to match.

  The match text MUST be at least {MIN_SUBSTRING_LENGTH} characters long.
  If the boundary line is shorter (like "A." or "1."), use the next
  non-empty line in the document as your match text instead.
"""


# =====================================================================
# Internal data shapes
# =====================================================================

@dataclass
class MatchedSection:
    title: str
    start_line: int     # 1-indexed; -1 if unmatched
    match_text: str
    matched: bool = True


# =====================================================================
# MAIN PIPELINE
# =====================================================================
# Read this function to see the whole flow. Everything else in this
# file is a helper that this function calls.

def run_sectioning(
    llm,
    docx_path,
    max_retries=MAX_RETRIES,
    max_words=MAX_DOCUMENT_WORDS,
    min_section_words=MIN_SECTION_WORDS,
    max_section_words=MAX_SECTION_WORDS,
):
    """Full pipeline: parse, prompt, match, merge tiny, split oversized.

    Args:
        llm: any langchain-compatible LLM with .with_structured_output()
        docx_path: path to a .docx file
        max_retries: retries when zero AI-returned sections match
        max_words: hard cap on total document size; raises ValueError
        min_section_words: floor; sections under this get auto-merged
        max_section_words: ceiling; sections over this get auto-split

    Returns:
        {'sections': [{'title', 'content'}, ...], 'reliable': bool}
    """
    # 1. Parse the .docx into markdown and build the LLM payload
    payload = build_payload(docx_path, max_words=max_words)
    lines = payload['markdown_lines']
    user_message = payload['user_message']

    # 2. Set up the structured-output LLM client
    structured_llm = llm.with_structured_output(Sections)

    # 3. Call the LLM, retrying on zero-match failure
    best_attempt = None
    for attempt in range(max_retries):
        llm_response = call_llm_safely(structured_llm, payload['system'], user_message)
        if llm_response is None or not llm_response.sections:
            continue

        all_sections = match_sections(llm_response.sections, lines)
        ai_matched_count = count_ai_matches(all_sections)

        # Track best attempt across retries in case we exhaust the budget
        if best_attempt is None or ai_matched_count > best_attempt['matched_count']:
            best_attempt = {'sections': all_sections, 'matched_count': ai_matched_count}

        if ai_matched_count > 0:
            chunks = finalize_sections(
                all_sections, lines, min_section_words, max_section_words,
            )
            return {'sections': chunks, 'reliable': True}

        # Zero matches: retry with feedback
        user_message = build_retry_message(
            payload['user_message'], all_sections, attempt, max_retries,
        )

    # 4. All retries exhausted: return best partial result, or fall back to whole doc
    if best_attempt and best_attempt['matched_count'] > 0:
        chunks = finalize_sections(
            best_attempt['sections'], lines, min_section_words, max_section_words,
        )
        return {'sections': chunks, 'reliable': False}

    return {
        'sections': [{'title': 'Document', 'content': '\n'.join(lines)}],
        'reliable': False,
    }


def finalize_sections(matched_sections, lines, min_section_words, max_section_words):
    """Run the deterministic post-processing: merge undersized, then split oversized."""
    merged = merge_undersized(matched_sections, lines, min_words=min_section_words)
    return split_markdown(merged, lines, max_section_words=max_section_words)


# =====================================================================
# Step 1: Build the LLM payload
# =====================================================================

def build_payload(docx_path, max_words=MAX_DOCUMENT_WORDS):
    """Convert the .docx, enforce size cap, format the user message."""
    markdown = docx_to_markdown(str(docx_path))
    lines = markdown.split('\n')
    word_count = sum(len(line.split()) for line in lines)

    if word_count > max_words:
        raise ValueError(
            f'Document is {word_count} words (~{word_count // 400} pages). '
            f'Limit is {max_words} words. Split the document or raise the '
            f'limit by passing max_words= to run_sectioning.'
        )

    user_message = f'Document (~{word_count} words):\n\n{markdown}'

    return {
        'system': SYSTEM_PROMPT,
        'user_message': user_message,
        'markdown_lines': lines,
        'word_count': word_count,
    }


# =====================================================================
# Step 2: Call the LLM
# =====================================================================

def call_llm_safely(structured_llm, system_prompt, user_message):
    """Wraps the LLM call so transient errors return None instead of raising.
    The retry loop in run_sectioning treats None as a failed attempt.
    """
    try:
        return structured_llm.invoke([
            ('system', system_prompt),
            ('user', user_message),
        ])
    except Exception:
        return None


# =====================================================================
# Step 3: Match AI section boundaries to line numbers
# =====================================================================
# The AI returns section_match_text strings which we have to locate back
# in the source markdown. The chain goes exact -> substring -> normalized
# because the AI sometimes drops the '## ' prefix or paraphrases punctuation.

def normalize_for_matching(text):
    """Lowercase + strip non-alphanumeric for fuzzy comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def find_matching_line(match_text, lines, search_from=0):
    """Locate a line that matches the AI's match_text.

    Three-stage fallback because the AI occasionally drops the # prefix
    or paraphrases punctuation. Returns line index or None.
    """
    stripped = match_text.strip()
    if not stripped:
        return None

    # Stage 1: exact match (handles ~95% of cases)
    for line_index in range(search_from, len(lines)):
        if lines[line_index].strip() == stripped:
            return line_index

    # Stage 2: substring match (handles AI dropping '## ' prefix etc.)
    if len(stripped) >= MIN_SUBSTRING_LENGTH:
        for line_index in range(search_from, len(lines)):
            line_stripped = lines[line_index].strip()
            if len(line_stripped) < MIN_SUBSTRING_LENGTH:
                continue
            if stripped in lines[line_index] or line_stripped in stripped:
                return line_index

    # Stage 3: normalized match (whitespace/punctuation/case differences)
    normalized = normalize_for_matching(stripped)
    if normalized and len(normalized) >= 4:
        for line_index in range(search_from, len(lines)):
            if normalize_for_matching(lines[line_index]) == normalized:
                return line_index

    return None


def match_sections(ai_sections, lines):
    """Resolve AI section list to line positions.

    Returns ALL sections (matched and unmatched) so the retry logic can
    see which match texts failed. Inserts an auto Preamble section if
    the first matched section starts after line 1.
    """
    sections = []
    cursor = 0

    for item in ai_sections:
        if isinstance(item, SectionItem):
            title = item.title
            match_text = item.section_match_text
        else:
            title = item.get('title', 'Untitled')
            match_text = item.get('section_match_text', '')
        if not match_text:
            continue

        found_index = find_matching_line(match_text, lines, search_from=cursor)
        if found_index is not None:
            sections.append(MatchedSection(title, found_index + 1, match_text, True))
            cursor = found_index + 1
        else:
            sections.append(MatchedSection(title, -1, match_text, False))

    # Auto-insert Preamble if line 1 isn't covered by any matched section
    matched_only = [section for section in sections if section.matched]
    if not matched_only or matched_only[0].start_line > 1:
        sections.insert(0, MatchedSection('Preamble', 1, '', True))

    return sections


def count_ai_matches(matched_sections):
    """Count sections that matched AND came from the AI (not auto-Preamble)."""
    return sum(
        1 for section in matched_sections
        if section.matched and section.match_text
    )


def build_retry_message(original_message, failed_sections, attempt, max_retries):
    """Construct a retry message that tells the AI which match texts failed."""
    failed = [section for section in failed_sections if not section.matched]
    failed_text_block = '\n'.join(f'  - "{section.match_text}"' for section in failed)
    return (
        f'{original_message}\n\n'
        f'RETRY (attempt {attempt + 1}/{max_retries}): The following '
        f'section_match_text values could NOT be found in the document. '
        f'They must be EXACT copies of lines from the document. Please '
        f're-analyze and provide corrected values.\n\n'
        f'Failed matches:\n{failed_text_block}\n\n'
        f'Remember: copy the line EXACTLY as it appears, including any '
        f'markdown formatting like # or ** at the start.'
    )


# =====================================================================
# Step 4: Merge undersized sections
# =====================================================================

def merge_undersized(matched_sections, lines, min_words):
    """Drop sections under min_words by folding them into a neighbor.

    Sections at index 1+ fold backward into their previous section.
    If section 0 is undersized, section 1 absorbs it forward by extending
    its start_line back to the document beginning.
    """
    matched = sorted(
        [section for section in matched_sections if section.matched],
        key=lambda section: section.start_line,
    )
    if len(matched) <= 1:
        return matched

    def words_in_section(idx, sections):
        start = sections[idx].start_line - 1
        next_exists = idx + 1 < len(sections)
        end = sections[idx + 1].start_line - 1 if next_exists else len(lines)
        return sum(len(line.split()) for line in lines[start:end])

    result = list(matched)
    index = 0
    while index < len(result):
        if words_in_section(index, result) >= min_words:
            index += 1
            continue

        if index == 0 and len(result) > 1:
            # First section too small: extend the next one back to line 1
            next_section = result[1]
            result[1] = MatchedSection(
                title=next_section.title,
                start_line=result[0].start_line,
                match_text=next_section.match_text,
                matched=True,
            )
            result.pop(0)
        elif index > 0:
            result.pop(index)
        else:
            index += 1

    return result


# =====================================================================
# Step 5: Split oversized sections at sentence boundaries
# =====================================================================

SENTENCE_SEPARATOR = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def split_under_ceiling(content, max_words):
    """Split content into the minimum number of pieces each under max_words,
    cutting at sentence boundaries closest to evenly-spaced split points.
    """
    sentences = [s for s in SENTENCE_SEPARATOR.split(content) if s.strip()]
    total_words = sum(len(s.split()) for s in sentences)

    if total_words <= max_words or len(sentences) < 2:
        return [content]

    num_parts = math.ceil(total_words / max_words)
    target_per_part = total_words / num_parts

    cumulative_words = [0]
    for sentence in sentences:
        cumulative_words.append(cumulative_words[-1] + len(sentence.split()))

    split_points = [0]
    for part_index in range(1, num_parts):
        ideal_word_position = part_index * target_per_part
        previous = split_points[-1]
        best = previous + 1
        best_diff = abs(cumulative_words[best] - ideal_word_position)
        for boundary in range(previous + 2, len(sentences)):
            diff = abs(cumulative_words[boundary] - ideal_word_position)
            if diff < best_diff:
                best_diff = diff
                best = boundary
        split_points.append(best)
    split_points.append(len(sentences))

    return [
        ' '.join(sentences[split_points[i]:split_points[i + 1]])
        for i in range(len(split_points) - 1)
    ]


def split_markdown(sections, lines, max_section_words=MAX_SECTION_WORDS):
    """Cut markdown at section boundaries. Sections over max_section_words
    get split at sentence boundaries with (part_n/total) suffixed to titles.
    """
    matched = sorted(
        [section for section in sections if section.matched],
        key=lambda section: section.start_line,
    )
    chunks = []
    for index, section in enumerate(matched):
        start_line_index = section.start_line - 1
        next_section_exists = index + 1 < len(matched)
        end_line_index = (
            matched[index + 1].start_line - 1 if next_section_exists else len(lines)
        )
        content = '\n'.join(lines[start_line_index:end_line_index]).strip()

        pieces = split_under_ceiling(content, max_section_words)
        if len(pieces) == 1:
            chunks.append({'title': section.title, 'content': pieces[0]})
        else:
            total = len(pieces)
            for part_num, piece in enumerate(pieces, 1):
                chunks.append({
                    'title': f'{section.title} ({part_num}/{total})',
                    'content': piece,
                })
    return chunks
