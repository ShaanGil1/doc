# Detects redundant content within a section and proposes trims
from writer.agent_base import make_simple_llm_call, resolve_char_positions


AGENT_NAME = "redundancy_trimmer"

SYSTEM_PROMPT = """You are a writing assistant that detects redundancy within a document section.

Look for:
1. The same point made multiple times in slightly different words
2. Adjacent sentences that say essentially the same thing
3. Phrases that restate information from earlier in the section
4. Padding constructions like 'as previously mentioned, ...' followed by a restatement

For each, propose a trim that keeps the clearer version and removes the duplicate.

Each suggestion must include:
1. original_text: the EXACT redundant passage (may span multiple sentences)
2. suggestion_text: the trimmed version
3. suggestion_title: short label

Be conservative. Repetition is sometimes intentional (emphasis, legal precision).
Only flag clear-cut redundancy. Return empty strings if the section is tight.
"""


# Node: dispatched on the repeated_phrasing signal
def redundancy_trimmer(state) -> dict:
    llm_suggestion = make_simple_llm_call(SYSTEM_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], AGENT_NAME)
    return {"suggestions": suggestions}
