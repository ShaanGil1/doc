"""
Document sectioning via docling + AI.

Converts documents to markdown, analyzes heading structure, and uses an LLM
with structured output to identify section boundaries for independent editing.

Usage:
    from langchain_anthropic import ChatAnthropic
    from sectioning import Sections, build_payload, match_sections, split_markdown, run_sectioning

    # option A: full pipeline with retries
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")
    result = run_sectioning(llm, "path/to/doc.pdf")
    chunks = result["sections"]   # list of {"title": str, "content": str}
    reliable = result["reliable"] # False if matching was poor

    # option B: step by step
    payload = build_payload("path/to/doc.pdf")
    struct_llm = llm.with_structured_output(Sections)
    result = struct_llm.invoke([
        ("system", payload["system"]),
        ("user", payload["user_message"]),
    ])
    sections = match_sections(result.sections, payload["markdown_lines"])
    chunks = split_markdown(sections, payload["markdown_lines"])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field
from docling.document_converter import DocumentConverter


# ---------------------------------------------------------------------------
# Prompt (base + tier-specific additions)
# ---------------------------------------------------------------------------

_BASE_PROMPT = """\
You are a document structure analyzer. Given a markdown document, identify \
top-level section boundaries. These sections will be independently edited by \
a human, so each should be a coherent, self-contained unit.

Core rules:
- Produce exactly ONE flat level of sections. No nesting.
- Short sections are fine. "Purpose" with two sentences is a valid section.
- Target roughly one section per 300-800 words. Never exceed 100 sections.

Handle these as SINGLE sections (do not split apart):
- Tables of contents, lists of figures
- Definition/acronym lists, revision history, change logs
- Large tables
- Appendices (keep whole unless they have clear internal structure)

Fold signature blocks into the final section.

If the document has sequentially numbered paragraphs with no hierarchy, \
group related ones together. Do not make each paragraph its own section.

For each section you MUST provide TWO separate fields:
- title: a short descriptive name for the section (used for display only, \
can be whatever label makes sense)
- section_match_text: used ONLY for locating the section in the document. \
This must be the EXACT text of a single line from the document, copied \
VERBATIM. Do not paraphrase, do not truncate, do not add or remove any \
characters. We use exact string matching, so even one character off will fail. \
The match text MUST be at least 8 characters long. If the boundary line is \
shorter than 8 characters (like "A." or "1."), use the next non-empty line \
in the document as your match text instead."""


_TIER_PROMPTS = {
    1: """
You are receiving a STRUCTURAL OUTLINE of the document showing the heading \
hierarchy and word counts. The headings are reliable.

Use markdown heading levels as your primary signal. The highest heading level \
present generally defines your top-level sections. Lower-level headings should \
be included as content within their parent section, NOT as separate sections.

Exception: if a top-level section would exceed ~40% of the document based on \
the word counts shown, break it at the next heading level down.

Your section_match_text should be the full heading line exactly as it appears \
in the document, including any markdown # prefixes.""",

    2: """
You are receiving a structural outline AND the full document content. The \
outline's heading structure may be unreliable (some headings might be noise, \
or the hierarchy might be inconsistent).

Cross-reference the outline against the actual content. Use your judgment to \
determine which headings represent real section boundaries versus formatting \
artifacts. Look for patterns like:
- Headings that are clearly structural (numbered sections, titled divisions)
- Headings that are just formatted text (bold lines misidentified as headings)
- Inconsistent heading levels that suggest the document was converted poorly

If the outline conflicts with what you see in the content, trust the content.

Your section_match_text should be copied exactly from the FULL CONTENT section, \
not from the outline (which may have been reformatted).""",

    3: """
You are receiving raw document content with NO reliable heading structure.

Look for section boundaries using these signals (in priority order):
1. Numbering schemes: "1." "2." "3.", "A." "B." "C.", "1.1" "1.2", etc.
2. Uppercase or emphasized lines that act as informal headings
3. Topic transitions signaled by blank lines and subject changes
4. Structural markers like "SUBJECT:", "PURPOSE:", "REFERENCES:", etc.

When using a numbering scheme, identify the TOP-LEVEL numbers as section \
boundaries. Sub-numbers (like 1.1, 1.2 under section 1) should be grouped \
with their parent, not made into separate sections.

Your section_match_text should be the complete first line of where each \
section begins, copied exactly.""",
}


def _build_system_prompt(tier: int) -> str:
    return _BASE_PROMPT + "\n" + _TIER_PROMPTS[tier]


# ---------------------------------------------------------------------------
# Structured output models
#
# Pass Sections to llm.with_structured_output(Sections)
# ---------------------------------------------------------------------------

class SectionItem(BaseModel):
    title: str = Field(description="Short descriptive name for this section (display only).")
    section_match_text: str = Field(
        description="EXACT text of a line from the document where this section starts. "
        "Used only for locating the section, must be a verbatim copy."
    )

class Sections(BaseModel):
    sections: list[SectionItem] = Field(
        description="List of section boundaries in document order."
    )


# ---------------------------------------------------------------------------
# Internal data
# ---------------------------------------------------------------------------

@dataclass
class HeadingNode:
    level: int
    text: str
    start_line: int
    word_count: int = 0
    children: list[HeadingNode] = field(default_factory=list)

@dataclass
class MatchedSection:
    title: str
    start_line: int    # 1-indexed, -1 if unmatched
    match_text: str
    matched: bool = True


# ---------------------------------------------------------------------------
# Conversion + heading parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def convert_to_markdown(file_path: str | Path) -> str:
    converter = DocumentConverter()
    return converter.convert(str(file_path)).document.export_to_markdown()


def parse_headings(lines: list[str]) -> list[HeadingNode]:
    headings: list[HeadingNode] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append(HeadingNode(len(m.group(1)), m.group(2).strip(), i + 1))

    for idx, h in enumerate(headings):
        end = headings[idx + 1].start_line - 1 if idx + 1 < len(headings) else len(lines)
        h.word_count = sum(len(l.split()) for l in lines[h.start_line:end])

    return headings


def build_tree(headings: list[HeadingNode]) -> list[HeadingNode]:
    roots: list[HeadingNode] = []
    stack: list[HeadingNode] = []
    for h in headings:
        while stack and stack[-1].level >= h.level:
            stack.pop()
        (stack[-1].children if stack else roots).append(h)
        stack.append(h)
    return roots


def _subtree_words(node: HeadingNode) -> int:
    return node.word_count + sum(_subtree_words(c) for c in node.children)


def format_outline(roots: list[HeadingNode], indent: int = 0) -> str:
    parts = []
    for node in roots:
        prefix = "  " * indent
        hashes = "#" * node.level
        parts.append(f"{prefix}{hashes} {node.text} [~{_subtree_words(node)} words]")
        if node.children:
            parts.append(format_outline(node.children, indent + 1))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------

def detect_tier(headings: list[HeadingNode], roots: list[HeadingNode], total_words: int) -> int:
    """
    1 = headings look reasonable, send outline only
    2 = headings exist but something is off, send outline + content
    3 = no usable headings, send content only
    """
    if not headings:
        return 3

    # less than 10 words per heading = not real headings
    if total_words / len(headings) < 10:
        return 3

    # one root holds 60%+ of the doc = lopsided, AI needs content to fix it.
    # skip for single-root-with-children (title heading pattern)
    if roots and not (len(roots) == 1 and roots[0].children):
        root_words = [_subtree_words(r) for r in roots]
        total = sum(root_words)
        if total > 0 and max(root_words) / total > 0.6:
            return 2

    return 1


# ---------------------------------------------------------------------------
# Build payload
# ---------------------------------------------------------------------------

def build_payload(file_path: str | Path) -> dict:
    """
    Returns:
        system:         tier-specific system prompt
        user_message:   user message string
        tier:           1, 2, or 3
        markdown_lines: raw lines for splitting after AI responds
    """
    markdown = convert_to_markdown(file_path)
    lines = markdown.split("\n")
    total_words = sum(len(l.split()) for l in lines)

    headings = parse_headings(lines)
    roots = build_tree(headings)
    tier = detect_tier(headings, roots, total_words)
    outline = format_outline(roots) if roots else None

    parts = [f"Document: ~{total_words} words.\n"]
    if tier == 1:
        parts.append("DOCUMENT STRUCTURE:\n")
        parts.append(outline)
    elif tier == 2:
        parts.append("DOCUMENT STRUCTURE (may be unreliable, verify against content):\n")
        parts.append(outline)
        parts.append("\nFULL CONTENT:\n")
        parts.append("\n".join(lines))
    else:
        parts.append("CONTENT:\n")
        parts.append("\n".join(lines))

    return {
        "system": _build_system_prompt(tier),
        "user_message": "\n".join(parts),
        "tier": tier,
        "markdown_lines": lines,
    }


# also expose build_payload_from_markdown for testing without docling
def build_payload_from_markdown(markdown: str) -> dict:
    """Same as build_payload but takes raw markdown instead of a file path."""
    lines = markdown.split("\n")
    total_words = sum(len(l.split()) for l in lines)

    headings = parse_headings(lines)
    roots = build_tree(headings)
    tier = detect_tier(headings, roots, total_words)
    outline = format_outline(roots) if roots else None

    parts = [f"Document: ~{total_words} words.\n"]
    if tier == 1:
        parts.append("DOCUMENT STRUCTURE:\n")
        parts.append(outline)
    elif tier == 2:
        parts.append("DOCUMENT STRUCTURE (may be unreliable, verify against content):\n")
        parts.append(outline)
        parts.append("\nFULL CONTENT:\n")
        parts.append("\n".join(lines))
    else:
        parts.append("CONTENT:\n")
        parts.append("\n".join(lines))

    return {
        "system": _build_system_prompt(tier),
        "user_message": "\n".join(parts),
        "tier": tier,
        "markdown_lines": lines,
    }


# ---------------------------------------------------------------------------
# Text matching
# ---------------------------------------------------------------------------

# if the AI returns match text shorter than this, skip substring matching.
# prevents short strings like "1." from false-matching random lines.
# the prompt tells the AI about this limit so it won't return short text.
_MIN_SUBSTRING_LEN = 8


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _find_line(match_text: str, lines: list[str], search_from: int = 0) -> int | None:
    stripped = match_text.strip()
    if not stripped:
        return None

    # exact match (should hit ~95% of the time)
    for i in range(search_from, len(lines)):
        if lines[i].strip() == stripped:
            return i

    # substring (AI dropped prefix like "## " or added trailing content)
    if len(stripped) >= _MIN_SUBSTRING_LEN:
        for i in range(search_from, len(lines)):
            line_stripped = lines[i].strip()
            if not line_stripped:
                continue
            if stripped in lines[i] or line_stripped in stripped:
                return i

    # normalized (whitespace/punctuation/case differences)
    normalized = _normalize(stripped)
    if normalized and len(normalized) >= 4:
        for i in range(search_from, len(lines)):
            if _normalize(lines[i]) == normalized:
                return i

    return None


def match_sections(
    ai_sections: list[SectionItem] | list[dict],
    lines: list[str],
) -> list[MatchedSection]:
    """
    Resolve AI output to line positions.
    Returns ALL sections (matched and unmatched) so retry logic can see failures.
    Auto-inserts a Preamble if no section covers line 1.
    """
    sections: list[MatchedSection] = []
    last = 0

    for item in ai_sections:
        if isinstance(item, SectionItem):
            title, mt = item.title, item.section_match_text
        else:
            title, mt = item.get("title", "Untitled"), item.get("section_match_text", "")

        if not mt:
            continue

        found = _find_line(mt, lines, search_from=last)
        if found is not None:
            sections.append(MatchedSection(title, found + 1, mt, True))
            last = found + 1
        else:
            sections.append(MatchedSection(title, -1, mt, False))

    # make sure line 1 is covered
    matched = [s for s in sections if s.matched]
    if not matched or matched[0].start_line > 1:
        sections.insert(0, MatchedSection("Preamble", 1, "", True))

    return sections


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3


def _build_retry_message(
    original_message: str,
    failed_sections: list[MatchedSection],
    attempt: int,
) -> str:
    failed_texts = [s.match_text for s in failed_sections if not s.matched]
    feedback = (
        f"\n\nRETRY (attempt {attempt + 1}/{_MAX_RETRIES}): "
        f"The following section_match_text values could NOT be found in the document. "
        f"They must be EXACT copies of lines from the document. "
        f"Please re-analyze and provide corrected values.\n\n"
        f"Failed matches:\n"
    )
    for text in failed_texts:
        feedback += f'  - "{text}"\n'
    feedback += (
        "\nRemember: copy the line EXACTLY as it appears, including any "
        "markdown formatting like # or ## at the start."
    )
    return original_message + feedback


def run_sectioning(
    llm,
    file_path: str | Path,
    max_retries: int = _MAX_RETRIES,
) -> dict:
    """
    Full pipeline with retries. Pass any langchain-compatible LLM.

    Retries only when zero sections match (total failure).
    If all retries fail, returns the best result we got with a warning.

    Returns:
        sections: list of {"title": str, "content": str}
        reliable: bool, False if matching was poor
    """
    payload = build_payload(file_path)
    struct_llm = llm.with_structured_output(Sections)
    lines = payload["markdown_lines"]
    user_message = payload["user_message"]

    best_result = None

    for attempt in range(max_retries):
        try:
            result = struct_llm.invoke([
                ("system", payload["system"]),
                ("user", user_message),
            ])
        except Exception:
            continue

        if not result or not result.sections:
            continue

        all_sections = match_sections(result.sections, lines)
        ai_matched = [s for s in all_sections if s.matched and s.match_text]

        # keep track of the best result across attempts
        if best_result is None or len(ai_matched) > best_result["matched_count"]:
            best_result = {
                "sections": all_sections,
                "matched_count": len(ai_matched),
            }

        # if at least one AI section matched, we're good
        if ai_matched:
            return {
                "sections": split_markdown(all_sections, lines),
                "reliable": True,
            }

        # zero matches -- retry with feedback
        user_message = _build_retry_message(payload["user_message"], all_sections, attempt)

    # all retries failed -- return best result we got, or the whole doc
    if best_result and best_result["matched_count"] > 0:
        return {
            "sections": split_markdown(best_result["sections"], lines),
            "reliable": False,
        }

    return {
        "sections": [{"title": "Document", "content": "\n".join(lines)}],
        "reliable": False,
    }


# ---------------------------------------------------------------------------
# Split into sections
# ---------------------------------------------------------------------------

def split_markdown(
    sections: list[MatchedSection],
    lines: list[str],
) -> list[dict]:
    """
    Split markdown at section boundaries.
    Returns list of {"title": str, "content": str} with raw markdown.
    """
    matched = sorted([s for s in sections if s.matched], key=lambda s: s.start_line)

    result = []
    for i, section in enumerate(matched):
        start = section.start_line - 1
        end = matched[i + 1].start_line - 1 if i + 1 < len(matched) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        result.append({"title": section.title, "content": content})
    return result


# # raw text alternative -- strips markdown syntax.
# _MD_SYNTAX_RE = re.compile(r"^#{1,6}\s+|^\s*[-*+]\s|\*\*|__|\*|_|`{1,3}|^\|.*\|$|^---+$")
#
# def split_text(sections: list[MatchedSection], lines: list[str]) -> list[dict]:
#     matched = sorted([s for s in sections if s.matched], key=lambda s: s.start_line)
#     result = []
#     for i, section in enumerate(matched):
#         start = section.start_line - 1
#         end = matched[i + 1].start_line - 1 if i + 1 < len(matched) else len(lines)
#         cleaned = [_MD_SYNTAX_RE.sub("", l).strip() for l in lines[start:end]]
#         result.append({"title": section.title, "content": "\n".join(c for c in cleaned if c)})
#     return result
