"""
Purpose : Example of what a writer side node would look like. Can run
          standalone as a single-pass suggestion generator, or as part of
          the write -> review loop when review_requested=True.
"""

from typing import Optional, TypedDict
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class PolicySectionState(TypedDict):
    # Inputs
    section_text         : str           # section user is currently typing in
    additional_context   : Optional[str] # upstream context as an override if needed
    review_requested     : bool          # flag set upstream  if False, reviewer exits immediately after first pass

    # Working fields 
    reviews              : list          # all reviews accumulated across every cycle
    prior_review         : list          # reviews from the most recent cycle only used as context on next pass
    routing              : Optional[str] # routing decision written by reviewer_node, read by route_after_review
    retry_count_writer   : int           # number of completed writer -> reviewer cycles
    max_retries          : int           # how many times the loop can repeat set by caller, not hardcoded
    suggestions          : list          # all suggestions accumulated across every cycle

    # Observability
    traversal            : list[str]     # ordered log of every node visit including retries


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class Suggestion(BaseModel):
    original_text  : str                        # verbatim phrase from the section that needs changing
    suggestion     : str                        # the rewrite
    confidence     : Optional[float] = Field(default=None, ge=0.0, le=1.0)
    written_reason : Optional[str]   = None     # explanation if actor had to be inferred


class WriterResult(BaseModel):
    suggestions : list[Suggestion] = Field(default_factory=list)
    # Empty list means no changes needed for this pass


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

_base_llm = ChatGoogleGenerativeAI(
    model="place gemini model here",
    temperature=0.2,              # Example value
    project="your-gcp-project",   # Example value, might need to use different connection/service
)

writer_llm = _base_llm.with_structured_output(
    schema=WriterResult.model_json_schema(),
    method="json_schema",
)


# ---------------------------------------------------------------------------
# Prompts Random Example DO NOT USE
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a policy writer. Write a clear, concise, and accurate policy section.
  - Use plain language - no jargon unless the term is defined in the section.
  - Be complete - do not omit obligations, exceptions, or effective dates.
  - Do not add information not grounded in the source material.
"""

USER_PROMPT = """\
{context_block}\
{feedback_block}\
Source material:
---
{section_text}
---
"""

FEEDBACK_BLOCK_TEMPLATE = """\
Your previous draft was reviewed. Address each issue below:
{formatted_feedback}
"""


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def writer_node(state: PolicySectionState) -> PolicySectionState:

    # 1. Guard - prevents runaway retries, max_retries set by caller in state
    if state.get("retry_count_writer", 0) >= state.get("max_retries", 3):
        state["traversal"] = state.get("traversal", []) + ["writer_node:aborted"]
        return state

    # 2. Conditional blocks - only added to the prompt if the field is populated
    context_block  = f"Additional context: {state['additional_context']}" if state.get("additional_context") else ""
    # TODO: format state["prior_review"], only populated if it has gone through a review 
    feedback_block = FEEDBACK_BLOCK_TEMPLATE.format(formatted_feedback=...) if state.get("prior_review") else ""

    # 3. Structured LLM call
    result = writer_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT.format(
            section_text   = state["section_text"],
            context_block  = context_block,
            feedback_block = feedback_block,
        )),
    ])

    # 4. Write back to state
    state["suggestions"] = state.get("suggestions", []) + [s.model_dump() for s in result.suggestions]
    state["traversal"]   = state.get("traversal", []) + [f"writer_node:attempt_{state.get('retry_count_writer', 0) + 1}"]

    return state