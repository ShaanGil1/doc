# Shared helpers for response agents (the reactive fixers)
from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from llm_client import llm_client
from shared.models import LLMSuggestion, ReviewerViolation, Suggestion


# Structured LLM call for fixing one violation (rule plugged into the prompt template)
# Returns [] if the LLM had nothing usable else [Suggestion]
def call_response_agent_llm(
    rule_description: str,
    violation: ReviewerViolation,
    section_content: str,
    section_id: str,
    sub_agent_name: str,
) -> List[Suggestion]:
    system_prompt = f"""You are a writing assistant fixing a specific rule violation in a document section.
    Rule being enforced:
    {rule_description}

    Reviewer flagged:
    Description: {violation.violation_description}
    Offending text: {violation.offending_text or '(see description)'}

    Propose a fix that:
    - Resolves the rule violation
    - Preserves meaning
    - Makes the minimum change necessary
    - Fits the surrounding tone

    Return:
    - original_text: EXACT offending substring (verbatim)
    - suggestion_text: your fix
    - suggestion_title: a short label

    If you can't propose a clean fix, return all empty strings.
    """

    structured_llm = llm_client.with_structured_output(LLMSuggestion)
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Section_Input content:\n\n{section_content}"),
    ])

    if result is None or not result.original_text or not result.original_text.strip():
        return []

    if (violation.offending_text == result.original_text
            and section_content[violation.start_char:violation.end_char] == result.original_text):
        start, end = violation.start_char, violation.end_char
    else:
        position = section_content.find(result.original_text)
        start, end = (position, position + len(result.original_text)) if position >= 0 else (0, 0)

    return [Suggestion(
        source_agent="reviewer",
        sub_agent=sub_agent_name,
        suggestion_title=result.suggestion_title,
        suggestion_text=result.suggestion_text,
        original_text=result.original_text,
        section_id=section_id,
        start_char=start,
        end_char=end,
    )]


# Package a non-LLM fix into a Suggestion
def build_fix_suggestion(
    violation: ReviewerViolation,
    fixed_text: Optional[str],
    suggestion_title: str,
    section_id: str,
    sub_agent_name: str,
) -> List[Suggestion]:
    if fixed_text is None or fixed_text == violation.offending_text:
        return []
    return [Suggestion(
        source_agent="reviewer",
        sub_agent=sub_agent_name,
        suggestion_title=suggestion_title,
        suggestion_text=fixed_text,
        original_text=violation.offending_text,
        section_id=section_id,
        start_char=violation.start_char,
        end_char=violation.end_char,
    )]
