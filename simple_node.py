"""
Purpose : To show case a simple node which would be an atomic part of the agentic system
"""
from typing import Optional, TypedDict
from pydantic import BaseModel, Field
from models import Suggestion
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class WriterState(TypedDict):
    # Inputs
    section_text            : str            # the section currently being edited
    reviewer_notes          : Optional[str]  # populated by the reviewer agent if it ran upstream
    additional_instructions : Optional[str]  # only populated if the user typed something, (some sort of injection explicit overrides)
    # Outputs (Be sure to make Suggestion parent class of ToneSuggestion)
    suggesitons : list[Suggestion]   # serialized ToneSuggestion objects
    traversal   : list[str]          # ordered log of nodes that have run
# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class ToneSuggestion(BaseModel):
    original_text  : str             # verbatim phrase from the section that needs changing
    suggestion     : str             # the active-voice rewrite
    confidence     : Optional[float] = Field(default=None, ge=0.0, le=1.0)
    written_reason : Optional[str]   = None  # explanation if actor had to be inferred


class ToneAdjusterResponse(BaseModel):
    suggestions: list[ToneSuggestion]  # empty list if no passive constructions found


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

_base_llm = ChatGoogleGenerativeAI(
    model="place gemini model here",
    temperature=0.2,              # Example value
    project="your-gcp-project",   # Example value, might need to use different connection/service
)

llm = _base_llm.with_structured_output(
    schema=ToneAdjusterResponse.model_json_schema(),
    method="json_schema",
)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a policy editor. Find passive voice constructions in the section below
and suggest active voice rewrites. Do not change meaning or factual content.
If you must infer too much, lower your confidence and explain in written_reason.
"""

USER_PROMPT = """\
{reviewer_block}
{instructions_block}
Section text:
---
{section_text}
---
"""


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def tone_adjuster_node(state: WriterState) -> WriterState:
    try:
        # 1. Read
        section_text = state["section_text"]

        # 2. Conditional blocks only added to the prompt if the field is populated
        reviewer_block     = f"Reviewer notes: {state['reviewer_notes']}\n" if state.get("reviewer_notes") else ""
        instructions_block = f"Extra instructions: {state['additional_instructions']}\n" if state.get("additional_instructions") else ""

        # 3. Structured LLM call
        result = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=USER_PROMPT.format(
                section_text       = section_text,
                reviewer_block     = reviewer_block,
                instructions_block = instructions_block,
            )),
        ])

        # 4. Write back to state
        state["suggestions"] = [s for s in result["suggestions"]]
        state["traversal"] = state.get("traversal", []) + ["tone_adjuster"]

    except Exception as e:
        state["errors"]   = state.get("errors", []) + [str(e)]
        state["feedback"] = "tone_adjuster_node failed - see errors for detail"
        state["traversal"] = state.get("traversal", []) + ["tone_adjuster:error"]

    return state