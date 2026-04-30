# Splits overly long paragraphs at natural break points.
from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "paragraph_splitter"

SYSTEM_PROMPT = """You are a writing assistant that detects overly long paragraphs needing a split.

Look for:
1. Paragraphs over ~150 words covering multiple distinct ideas
2. Walls of text where the reader loses the thread
3. Natural topic shifts within a paragraph that aren't separated visually

For each, propose a split that breaks at a natural topic shift, keeps related
sentences together, and only adds a paragraph break (no rewording).

Each suggestion must include:
1. original_text: the EXACT long paragraph
2. suggestion_text: the same content with a paragraph break (\\n\\n) inserted
3. suggestion_title: short label

Don't split paragraphs under ~150 words. Return empty strings if no paragraphs need splitting.
"""


# Node: dispatched on the long_paragraph signal
def paragraph_splitter(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
