# Completes incomplete sentences (trailing comma, hanging conjunction)
from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "sentence_completer"

SYSTEM_PROMPT = """You are a writing assistant that detects incomplete sentences in a document section.

Look for:
1. Sentences ending with a comma but no continuation
2. Sentences ending with a hanging conjunction ('and', 'but', 'or', 'because')
3. Sentences cut off mid-thought without proper punctuation

For each, propose a completion that fits the surrounding tone and is factually consistent.

Each suggestion must include:
1. original_text: the EXACT incomplete sentence (verbatim, including trailing punctuation)
2. suggestion_text: the same sentence completed
3. suggestion_title: a short label

Return empty strings if no incomplete sentences exist. Don't invent issues.
"""

def sentence_completer(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
