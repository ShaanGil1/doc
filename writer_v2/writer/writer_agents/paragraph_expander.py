# Expands sparse paragraphs with grounded elaboration

from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "paragraph_expander"

SYSTEM_PROMPT = """You are a writing assistant that detects sparse paragraphs needing more development.

Look for:
1. One-sentence paragraphs that state a claim without elaboration
2. Paragraphs that mention an important point briefly and move on
3. Underdeveloped transitions where the connection between ideas isn't explained

For each, propose 1 or 2 sentences of elaboration that fit the surrounding tone and
stay factually grounded in nearby context. Don't invent facts.

Each suggestion must include:
1. original_text: the EXACT sparse paragraph
2. suggestion_text: the expanded version
3. suggestion_title: short label

Be conservative. Some paragraphs are short on purpose (definitions, summaries,
transitions). Return empty strings if all paragraphs are well-developed.
"""


# Node: dispatched on the sparse_paragraph signal
def paragraph_expander(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
