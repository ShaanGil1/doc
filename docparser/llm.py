from langchain_google_genai import ChatGoogleGenerativeAI

from .models import (
    MAX_DOCUMENT_WORDS,
    MIN_SECTION_WORDS,
    MAX_SECTION_WORDS,
)

GEMINI_MODEL = 'gemini-2.5-flash'
TEMPERATURE = 0  


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
You are a document structure analyzer. Identify top-level section
boundaries for an editing workflow.

WORKFLOW CONTEXT:
Sections_LLM will be edited independently by a human writer. Each section
should be a coherent topic worth a focused editing pass.

CORE RULES:
- Output sections in document order. Never exceed 50 sections.
- Produce exactly ONE flat level of sections.

SIZE GUIDANCE:
- Aim for {MIN_SECTION_WORDS}-{MAX_SECTION_WORDS} words per section.
- Prioritize topic coherence over hitting size targets. Oversized
  sections are split automatically afterward.
- Sections_LLM under {MIN_SECTION_WORDS} words should be folded into a neighbor.

KEEP THESE AS SINGLE SECTIONS:
- Tables of contents, lists of figures
- Definition/acronym lists, revision history, change logs
- Large tables
- Appendices
- Fold signature blocks into the final section.

USING THE STRUCTURAL METADATA:
The user message includes the document markdown AND a metadata block
listing paragraphs with their depth in the document's structure
(extracted directly from the .docx XML). Lower depth = more top-level.

- Treat depth=0 paragraphs as the strongest candidates for section
  boundaries. Their text is the title.
- depth=1 and below usually belong INSIDE the parent section, not as
  separate sections.
- Some paragraphs have no depth shown at all (the author didn't use
  Word's list features). For those, fall back to text shape: lines like
  "C4.1 GENERAL", "**APPENDIX A**", "1.1 Introduction", "5 April 2012
  Update" are likely section boundaries even without depth metadata.

The metadata is a HINT, not a rule. Use document context to decide. If
depth=0 paragraphs are too granular (every bullet has depth=0), fall
back to text shape.

OUTPUT FORMAT:
- title: short descriptive name (3-7 words). Display only, can be paraphrased.
- section_match_text: EXACT verbatim copy of the markdown line where the
  section starts. Even one character off will fail to match. Must be at
  least 8 characters.
"""

def build_payload(markdown, metadata_rows, max_words=MAX_DOCUMENT_WORDS):
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
        metadata_lines = [f'- depth={r["depth"]}: {r["text"]}' for r in structured_rows]
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
    #Build a retry user-message that tells the LLM which match texts it returned couldn't be located in the document.
    failed_sections = [s for s in sections_with_failures if not s.matched]
    failed_block = '\n'.join(f'  - "{s.match_text}"' for s in failed_sections)
    return f"""{original_message}
        RETRY (attempt {attempt + 2}/{max_retries}): The following section_match_text
        values could NOT be found in the document. They must be EXACT copies.
        Re-analyze and provide corrected values.

        Failed matches:
        {failed_block}

        Copy each line EXACTLY, including any markdown # or ** at the start."""
