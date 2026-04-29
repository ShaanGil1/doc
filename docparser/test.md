```python
"""
llm.py

LLM connection setup and prompt building.

  build_llm()              constructs the Gemini client. Edit GEMINI_MODEL
                           or swap the langchain class to change provider.

  SYSTEM_PROMPT            instructions sent to the LLM every call.

  build_payload()          converts a .docx, extracts metadata, assembles
                           the user message. Returns system + user_message
                           + markdown_lines + word_count.

  build_retry_message()    used when the LLM returns sections we couldn't
                           locate; tells the LLM what failed.
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from .models import (
    MAX_DOCUMENT_WORDS,
    MIN_SECTION_WORDS,
    MAX_SECTION_WORDS,
)


# =====================================================================
# LLM client config
# =====================================================================
# Model choice notes (as of 2026):
#
#   "gemini-2.5-flash"      ~$0.005 per ~10-page doc, more reliable
#                            structured output. Recommended default.
#   "gemini-2.5-flash-lite" ~$0.001 per ~10-page doc, cheapest tier,
#                            occasionally returns slightly off match_text.
#   "gemini-2.5-pro"        more expensive, only worth it if flash is
#                            unreliable on a particular doc style.
#
# To switch to Anthropic:
#     from langchain_anthropic import ChatAnthropic
#     return ChatAnthropic(model='claude-haiku-4-5', temperature=0)
# To switch to OpenAI:
#     from langchain_openai import ChatOpenAI
#     return ChatOpenAI(model='gpt-5-nano', temperature=0)

GEMINI_MODEL = 'gemini-2.5-flash'
TEMPERATURE = 0   # deterministic structured output


def build_llm():
    """Construct and return the LLM client used by run_sectioning().

    The Gemini key is read from os.environ['GOOGLE_API_KEY'] by langchain
    automatically - we don't pass it explicitly. The route file
    (working_draft_docx.py) is responsible for ensuring that env var is
    set before this function is called, either from the actual
    environment or by copying GOOGLE_API_KEY_FOR_LOCAL into os.environ.

    To swap models or providers, change GEMINI_MODEL above or replace
    ChatGoogleGenerativeAI with another langchain client class. The rest
    of the pipeline only uses .with_structured_output() and .invoke(),
    which most langchain LLMs support.
    """
    return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=TEMPERATURE)


# =====================================================================
# System prompt
# =====================================================================

SYSTEM_PROMPT = f"""\
You are a document structure analyzer. Identify section boundaries for
an editing workflow where each section gets edited independently by a
human writer.

CORE RULES:
- Output sections in document order. Never exceed 50 sections.
- Produce exactly ONE flat level of sections (no nesting).
- Aim for {MIN_SECTION_WORDS}-{MAX_SECTION_WORDS} words per section.
  Smaller is better when there's a natural break - prefer two coherent
  sections over one long mixed section.

TITLE RULES (read these carefully - violations are the #1 problem):

The title field is for IDENTIFICATION, not summary. The title MUST be
copied from the document, not invented or paraphrased.

  1. Copy the heading text VERBATIM from the document.
  2. Strip ONLY leading numbering (e.g. "5.", "C4.1.", "AP2.2.1.").
  3. Strip ONLY leading markdown decorators (<u>, **, ##).
  4. Keep every other word exactly as written - same words, same order.
  5. DO NOT paraphrase. DO NOT summarize. DO NOT invent words.
  6. DO NOT use words that don't appear in the heading line.
  7. If the heading is empty, vague, or just numbers, copy the first 4-7
     distinctive words from the section's first sentence VERBATIM.

GOOD title examples:
  Heading "5. TRADING PARTNER ELIMINATION REVIEW PROCESS"
  -> title: "TRADING PARTNER ELIMINATION REVIEW PROCESS"

  Heading "C4.1.1. Purpose"
  -> title: "Purpose"

  Heading "<u>1. PURPOSE</u>"
  -> title: "PURPOSE"

BAD title examples (NEVER do this):
  Heading "5. TRADING PARTNER ELIMINATION REVIEW PROCESS"
  Bad: "Trading Partner Process Overview"   <- paraphrased
  Bad: "Eliminating Trading Partners"        <- invented words
  Bad: "Section 5: Process Description"      <- added words

SECTION BOUNDARY RULES:

- A section starts at a heading or top-level structural marker.
- Numbered/lettered/bulleted lists are SINGLE COHERENT UNITS. Never
  start a new section in the middle of a list (e.g. between items 2
  and 3 of a numbered list, or between a. and b.).
- Sub-items belonging to a parent section stay INSIDE that section.
- Sections under {MIN_SECTION_WORDS} words should be folded into a
  neighbor.

THE ONLY EXCEPTION TO SIZE LIMITS:
- Large tables stay as one section even if oversized. Splitting a table
  mid-row destroys it.
- Everything else (appendices, definition lists, change logs, etc.)
  follows the normal size guidance. If they're long, break them up.

USING THE STRUCTURAL METADATA:
The user message includes the document markdown AND a metadata block
listing paragraphs with their depth in the document's structure
(extracted directly from the .docx XML). Lower depth = more top-level.

- Treat depth=0 paragraphs as the strongest candidates for section
  boundaries. Their text is the title source (subject to TITLE RULES).
- depth=1 and below usually belong INSIDE the parent section, not as
  separate sections.
- Some paragraphs have no depth shown (author didn't use Word lists).
  For those, fall back to text shape: "C4.1 GENERAL", "**APPENDIX A**",
  "1.1 Introduction" patterns are likely section boundaries.

The metadata is a HINT, not a rule. Use document context. If depth=0
paragraphs are too granular (every bullet at depth=0), fall back to
text shape.

OUTPUT FORMAT:
- title: per TITLE RULES above. 3-7 words ideal, hard cap 100 chars.
- section_match_text: EXACT verbatim copy of the markdown line where
  the section starts. Even one character off will fail to match. Copy
  precisely. Must be at least 8 characters.
"""


# =====================================================================
# Payload + retry builders
# =====================================================================

def build_payload(markdown, metadata_rows, max_words=MAX_DOCUMENT_WORDS):
    """Assemble the LLM payload from already-converted markdown and
    extracted metadata.

    Pure assembly - no I/O. The caller (run_sectioning) is responsible
    for calling convert_to_markdown and extract_paragraph_depths first
    and passing in the results.

    Returns a dict with the four pieces downstream code needs:
        system          system prompt text (passed as system role)
        user_message    markdown + metadata, passed as user role
        markdown_lines  the markdown split into lines, used by
                        match_sections to map LLM-returned text back
                        to line numbers
        word_count      total word count, used by run_sectioning to
                        compute adaptive thresholds

    Raises ValueError if the document exceeds max_words. The cap exists
    because LLM call cost and quality both degrade on very long inputs,
    and our domain (DoD policy issuances) doesn't typically need more
    than 5000 words.
    """
    markdown_lines = markdown.split('\n')
    word_count = sum(len(line.split()) for line in markdown_lines)

    if word_count > max_words:
        raise ValueError(
            f'Document is {word_count} words (~{word_count // 400} pages). '
            f'Limit is {max_words} words. Split the doc or raise the limit.'
        )

    structured_rows = [r for r in metadata_rows if r['depth'] is not None]

    message_parts = [
        f'Document markdown (~{word_count} words):',
        '',
        markdown,
    ]
    if structured_rows:
        metadata_lines = [f'- depth={r["depth"]}: {r["text"]}' for r in structured_rows[:200]]
        if len(structured_rows) > 200:
            metadata_lines.append(f'... ({len(structured_rows) - 200} more)')
        message_parts.extend([
            '',
            '---',
            '',
            'STRUCTURAL METADATA (paragraph depths from the .docx XML):',
            '\n'.join(metadata_lines),
        ])

    return {
        'system': SYSTEM_PROMPT,
        'user_message': '\n'.join(message_parts),
        'markdown_lines': markdown_lines,
        'word_count': word_count,
    }


def build_retry_message(original_message, sections_with_failures, attempt, max_retries):
    """Build a retry user-message that tells the LLM which match texts
    it returned couldn't be located in the document.

    This is called when request_sections() got a response from the LLM
    but matched zero of the LLM's section_match_text values to actual
    lines in the markdown. Common cause: the LLM paraphrased the line
    instead of copying it verbatim, or it added/removed markdown
    decorators (** or ##) that the original line didn't have.

    The retry message appends a list of failed match texts to the
    original message and asks the LLM to copy them EXACTLY this time.
    The original message stays at the front so the LLM still sees the
    full document; only the instruction at the end changes.
    """
    failed_sections = [s for s in sections_with_failures if not s.matched]
    failed_block = '\n'.join(f'  - "{s.match_text}"' for s in failed_sections)
    return f"""{original_message}

RETRY (attempt {attempt + 2}/{max_retries}): The following section_match_text
values could NOT be found in the document. They must be EXACT copies.
Re-analyze and provide corrected values.

Failed matches:
{failed_block}

Copy each line EXACTLY, including any markdown # or ** at the start."""
```
