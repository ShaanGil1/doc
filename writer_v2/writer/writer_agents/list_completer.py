# Completes detected partial lists with next items matching the established pattern.

from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "list_completer"

SYSTEM_PROMPT = """You are a writing assistant that detects partial lists in a document section.

Look for:
1. Numbered/bulleted lists that stop short of completion
2. Lists with placeholder items like 'etc.' or '...' that could be filled in
3. Parallel structures where a clear pattern was set up but not finished

For each partial list, propose 1 to 3 next items matching the established pattern
semantically and stylistically (same grammar, same level of specificity).

Each suggestion must include:
1. original_text: the EXACT last item or placeholder
2. suggestion_text: the proposed completion
3. suggestion_title: short label

Be conservative. If you can't tell the pattern, return empty strings. Don't pad.
"""


# Node: dispatched on the list_pattern signal
def list_completer(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
