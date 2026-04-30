# Rewrites wordy or overly complex sentences for clarity

from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "clarity_rewriter"

SYSTEM_PROMPT = """You are a writing assistant that rewrites wordy or overly complex sentences for clarity.

Look for:
1. Wordy phrases ('in order to' to 'to', 'due to the fact that' to 'because')
2. Hidden verbs / nominalizations ('make a determination' to 'determine')
3. Filler that doesn't add meaning
4. Long sentences (~35+ words) that bury the main point

For each, propose a tighter rewrite that preserves meaning and tone (don't strip
professional voice from policy docs).

Each suggestion must include:
1. original_text: the EXACT wordy sentence/phrase
2. suggestion_text: the simpler version
3. suggestion_title: a short label

Return empty strings if writing is already clear. Be conservative.
"""


# Node: dispatched on wordy_phrase or long_sentence signals
def clarity_rewriter(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
