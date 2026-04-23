"""
Document sectioning via docling + AI.

Takes a document file (pdf, docx, etc.), converts it to markdown using docling,
then builds an AI prompt that asks the model to identify top-level section
boundaries suitable for independent editing.

The pipeline has three "tiers" based on how trustworthy the markdown headings are:
  - Tier 1: headings look clean. Send ONLY a structural outline (heading hierarchy
    with word counts) to the AI. Cheap and fast.
  - Tier 2: headings exist but are sketchy (one section dominates, or headings are
    suspiciously dense). Send the outline AND the full document content so the AI
    can verify the structure against the actual text.
  - Tier 3: no usable headings at all. Send raw content and let the AI find
    section boundaries from scratch.

Usage:
    payload = build_payload("path/to/doc.pdf")
    # payload["system"]         -> system prompt string
    # payload["messages"]       -> messages array for your API call
    # payload["tier"]           -> which tier was detected (1, 2, or 3)
    # payload["markdown_lines"] -> raw lines for splitting after AI responds
    #
    # after getting the AI response:
    # sections = parse_response(response_text, len(payload["markdown_lines"]))
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from docling.document_converter import DocumentConverter


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a document structure analyzer. Given a markdown document, identify \
top-level section boundaries. These sections will be independently edited by \
a human, so each should be a coherent, self-contained unit.

Rules:
- Produce exactly ONE flat level of sections. No nesting.
- Use markdown heading levels as your primary signal. The highest level present \
generally defines your sections. Lower headings stay inside their parent section.
- If a section would exceed ~40% of the document, break it at the next heading level.
- If there are no headings, look for numbering schemes (1. 2. 3., A. B. C., etc.) \
or natural topic transitions.
- Short sections are fine. "Purpose" with two sentences is a valid section.
- Target roughly one section per 300-800 words. Never exceed 100 sections.

Special elements to handle as SINGLE sections, not split apart:
- Tables of contents, lists of figures
- Definition/acronym lists
- Revision history and change logs
- Large tables (never split a table across sections)
- Appendices (keep whole unless they have clear internal structure)

Ignore for sectioning purposes:
- Repeated page headers/footers
- Classification markings like (U), (CUI), UNCLASSIFIED
- Signature blocks (fold into the final section)

If the document has sequentially numbered paragraphs (1 through 200) with no \
hierarchy, group related ones together. Do not make each paragraph a section.

Respond with ONLY a JSON array. No explanation, no code fences.
Each element: {"title": "...", "start_line": <1-indexed line number>}"""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class HeadingNode:
    """
    Represents a single markdown heading found during parsing.
    word_count tracks the words between this heading and the next one.
    children are lower-level headings nested under this one (used to
    roll up word counts for the outline).
    """
    level: int                                        # 1 for #, 2 for ##, etc.
    text: str                                         # the heading text itself
    start_line: int                                   # 1-indexed line in the markdown
    word_count: int = 0                               # words directly under this heading
    children: list[HeadingNode] = field(default_factory=list)


@dataclass
class Section:
    """A finalized section boundary, either from the AI or from fallback."""
    title: str
    start_line: int  # 1-indexed, where to split the markdown


# ---------------------------------------------------------------------------
# Conversion + heading parsing
# ---------------------------------------------------------------------------

# matches markdown headings: "# Title", "## Sub Title", etc.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")


def convert_to_markdown(file_path: str | Path) -> str:
    """
    Convert any docling-supported file (pdf, docx, etc.) to markdown.
    Docling normalizes messy inputs (scanned PDFs, weird formatting) into
    clean markdown which is what we want as the AI's input format.
    """
    converter = DocumentConverter()
    doc_result = converter.convert(str(file_path))
    return doc_result.document.export_to_markdown()


def parse_headings(lines: list[str]) -> list[HeadingNode]:
    """
    Walk markdown lines and extract every heading into a flat list.

    After finding all headings, goes back and counts the words between
    each heading and the next one. This word count is what shows up in
    the outline as [~N words].
    """
    headings: list[HeadingNode] = []
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            headings.append(HeadingNode(
                level=len(match.group(1)),     # number of # chars = heading level
                text=match.group(2).strip(),
                start_line=i + 1,              # 1-indexed for the AI
            ))

    # second pass: count words between each heading and the next
    for idx, h in enumerate(headings):
        # content runs from the line after this heading to the line before the next
        end = headings[idx + 1].start_line - 1 if idx + 1 < len(headings) else len(lines)
        content = lines[h.start_line:end]
        h.word_count = sum(len(l.split()) for l in content)

    return headings


def build_tree(headings: list[HeadingNode]) -> list[HeadingNode]:
    """
    Nest a flat list of headings into a tree based on heading level.

    Uses a stack: for each heading, pop everything off the stack that's
    at the same level or deeper, then attach to whatever's on top (the
    parent). If the stack is empty this is a root node.

    The tree is only used to roll up word counts and produce the indented
    outline string. It never gets sent to the AI directly.
    """
    roots: list[HeadingNode] = []
    stack: list[HeadingNode] = []
    for h in headings:
        # pop until we find a heading at a higher (lower number) level
        while stack and stack[-1].level >= h.level:
            stack.pop()
        # attach to parent if one exists, otherwise it's a root
        (stack[-1].children if stack else roots).append(h)
        stack.append(h)
    return roots


def _subtree_words(node: HeadingNode) -> int:
    """
    Total words under a heading INCLUDING all its children.
    So if "# Intro" has 20 words and its child "## Purpose" has 50 words,
    _subtree_words for Intro returns 70.
    """
    return node.word_count + sum(_subtree_words(c) for c in node.children)


def format_outline(roots: list[HeadingNode], indent: int = 0) -> str:
    """
    Turn the heading tree into a readable outline string with word counts.
    This is what tier 1 sends to the AI instead of the full document.

    Example output:
        # Introduction [~70 words]
          ## Purpose [~50 words]
          ## Scope [~310 words]
        # Requirements [~2400 words]
    """
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
#
# Decides how much info to send to the AI based on heading quality.
# Tier 1 = outline only (cheap), Tier 2 = outline + content, Tier 3 = content only
# ---------------------------------------------------------------------------

def detect_tier(headings: list[HeadingNode], roots: list[HeadingNode], total_words: int) -> int:
    """
    Analyze heading quality and return the appropriate tier (1, 2, or 3).

    Tier 3 triggers:
      - No headings at all
      - All headings are the same level with 30+ of them (probably noise
        from bold lines or list items that docling misidentified as headings)

    Tier 2 triggers:
      - One top-level section holds >60% of the document (lopsided structure)
      - Less than 15 words per heading on average (headings are too dense,
        likely formatting artifacts rather than real structure)

    Otherwise: Tier 1 (headings look trustworthy)
    """
    if not headings:
        return 3

    # 30+ headings all at the same level is almost certainly not real structure
    levels = {h.level for h in headings}
    if len(levels) == 1 and len(headings) > 30:
        return 3

    # one section dominates the doc -- structure might be misleading
    if roots:
        root_words = [_subtree_words(r) for r in roots]
        total = sum(root_words)
        if total > 0 and max(root_words) / total > 0.6:
            return 2

    # headings are suspiciously dense -- more noise than signal
    if total_words > 0 and len(headings) > 0:
        if total_words / len(headings) < 15:
            return 2

    return 1


# ---------------------------------------------------------------------------
# Build what gets sent to the AI
# ---------------------------------------------------------------------------

def _number_lines(lines: list[str]) -> str:
    """
    Prepend [1], [2], etc. to each line so the AI can reference exact
    line numbers in its response. Makes parsing the response unambiguous.
    """
    return "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(lines))


def build_payload(file_path: str | Path) -> dict:
    """
    Full pipeline entry point. Converts the doc, analyzes structure,
    picks a tier, and assembles the system + user messages.

    Returns a dict with:
        system:         system prompt string (pass as system param in API call)
        messages:       messages array (pass directly to API)
        tier:           which tier was detected (1, 2, or 3)
        markdown_lines: the raw markdown split by line (use this to split
                        the doc into sections after the AI responds)
    """
    # step 1: convert document to markdown via docling
    markdown = convert_to_markdown(file_path)
    lines = markdown.split("\n")
    total_words = sum(len(l.split()) for l in lines)

    # step 2: parse headings and build the hierarchy tree
    headings = parse_headings(lines)
    roots = build_tree(headings)

    # step 3: decide how much to send to the AI
    tier = detect_tier(headings, roots, total_words)

    # step 4: format the outline (only used by tier 1 and 2)
    outline = format_outline(roots) if roots else None

    # step 5: assemble the user message based on tier
    parts = [f"Document: ~{total_words} words.\n"]

    if tier == 1:
        # clean headings -- just send the outline, no content needed
        parts.append("DOCUMENT STRUCTURE:\n")
        parts.append(outline)
    elif tier == 2:
        # sketchy headings -- send outline for context but include full content
        # so the AI can verify against the actual text
        parts.append("DOCUMENT STRUCTURE (may be unreliable, verify against content):\n")
        parts.append(outline)
        parts.append("\nFULL CONTENT:\n")
        parts.append(_number_lines(lines))
    else:
        # no usable headings -- AI has to figure it out from raw content
        parts.append("No heading structure detected.\n\nCONTENT:\n")
        parts.append(_number_lines(lines))

    return {
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "\n".join(parts)}],
        "tier": tier,
        "markdown_lines": lines,
    }


# ---------------------------------------------------------------------------
# Response parsing
#
# The AI returns a JSON array of {"title": ..., "start_line": ...}.
# This parses it defensively and falls back to a single "Document" section
# if anything goes wrong, so a bad AI response never blocks the user.
# ---------------------------------------------------------------------------

def parse_response(response_text: str, total_lines: int) -> list[Section]:
    """
    Parse the AI's JSON response into a list of Section objects.

    Handles: markdown code fences the AI might add despite instructions,
    out-of-range line numbers, duplicate entries, and total parse failure.
    Always returns at least one section.
    """
    # strip accidental code fences
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # AI returned something unparseable -- fall back to one big section
        return [Section(title="Document", start_line=1)]

    # pull out valid section entries, skip anything malformed
    sections = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "Untitled"))
        start = item.get("start_line")
        if isinstance(start, int) and 1 <= start <= total_lines:
            sections.append(Section(title=title, start_line=start))

    # sort by position in the document
    sections.sort(key=lambda s: s.start_line)

    # remove duplicate start lines (shouldn't happen but just in case)
    seen = set()
    sections = [s for s in sections if s.start_line not in seen and not seen.add(s.start_line)]

    # make sure line 1 is covered -- if the AI started at line 10,
    # prepend a "Preamble" section so no content gets orphaned
    if not sections or sections[0].start_line > 1:
        sections.insert(0, Section(title="Preamble", start_line=1))

    return sections if sections else [Section(title="Document", start_line=1)]
