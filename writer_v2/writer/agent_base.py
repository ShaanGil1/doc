# Shared helpers for writer sub-agents.

from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from llm_client import llm_client
from shared.models import LLMSuggestion, Suggestion


# Structured LLM call (input/output shape is uniform for writer agents so we reuse this)
# If we need more complex shapes later (e.g. multiple suggestions per call), branch from here
def make_simple_llm_call(system_prompt: str, section_content: str) -> Optional[LLMSuggestion]:
    structured_llm = llm_client.with_structured_output(LLMSuggestion)
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Section_Input content:\n\n{section_content}"),
    ])
    if result is None or not result.original_text or not result.original_text.strip():
        return None
    return result


# Build a Suggestion from the LLMSuggestion (locates the snippet via string search)
# Falls back to (0, 0) if the LLM hallucinated a snippet that isn't in the section
def resolve_char_positions(
    llm_suggestion: Optional[LLMSuggestion],
    section_content: str,
    section_id: str,
    sub_agent_name: str,
) -> List[Suggestion]:
    if llm_suggestion is None:
        return []
    position = section_content.find(llm_suggestion.original_text) if llm_suggestion.original_text else -1
    start, end = (position, position + len(llm_suggestion.original_text)) if position >= 0 else (0, 0)
    return [Suggestion(
        source_agent="writer",
        sub_agent=sub_agent_name,
        suggestion_title=llm_suggestion.suggestion_title,
        suggestion_text=llm_suggestion.suggestion_text,
        original_text=llm_suggestion.original_text,
        section_id=section_id,
        start_char=start,
        end_char=end,
    )]
