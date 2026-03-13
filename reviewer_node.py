"""
Retry Loop Example (also shows how conditional edges work work) - reviewer_node.py
-----------------------------------
Purpose : Example of what a reviewer side node would look like and also some call back logic that it would have

The LLM has one job: find issues and describe them. It always returns a
reviews list. Empty means that no issues were found and therefore there is nothing to return

This logic could be applied in a variety of cases:

First Pass (No Rewrite Flag) -> Return Results 
First Pass (Rewrite Flag)    -> Route to Writer

Retry Pass means it is getting a call from the writer is performing a QA check almost

Retry Pass -> Review returns reviews -> Send back to writer with context
Retry Pass -> Review returns no reviews (empty list) -> Return Results 

The LLM never makes a routing decision. It never categorises the situation.
Prior review history is appended to the prompt as context so the LLM can
see what was previously flagged - but the code decides what to do next.
"""
from typing import Optional
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from writer_node import PolicySectionState, writer_node, MAX_RETRIES


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Review(BaseModel):
    error      : str                   # What error was triggered (usually would be the name of the reviewer agent for example if this was the tone review
                                       # it would return something like "Passive Voice"
    source_ref : Optional[str] = None  # phrase from source material that grounds this (If applicable only relevant for reviews that require grounding)
    draft_ref  : Optional[str] = None  # phrase from user text
    reason     : str                   # written explanation of why it wrong, could be as simple as "this is passive voice"


class ReviewResult(BaseModel):
    reviews : list[Review] = Field(default_factory=list)
    # Empty list means no issues found - the code routes on len(reviews)


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

_base_llm = ChatGoogleGenerativeAI(
    model="place gemini model here",
    temperature=0.2,              # Example value
    project="your-gcp-project",   # Example value, might need to use different connection/service
)

reviewer_llm = _base_llm.with_structured_output(
    schema=ReviewResult.model_json_schema(),
    method="json_schema",
)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert policy reviewer. Your job is to find issues in the draft
and describe them precisely. Do not decide what should happen next.

For every material issue, produce a Review:
  source_ref - phrase from source material that grounds this (if applicable)
  draft_ref  - the exact phrase from the draft that caused the problem (if applicable)
  error      - What error was triggered 
  reason     - What is the reason for this error being triggered

Return an empty reviews list if the draft is complete and accurate.
Do not {Insert Examples}. Only flag: {Insert Examples}
"""

USER_PROMPT = """\
Source material:
---
{section_text}
---
Reference Material:
---
{references}
---
{history_block}
"""

HISTORY_BLOCK_TEMPLATE = """\
Prior review history (for context - do not re-raise resolved issues):
{formatted_history}
"""


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def reviewer_node(state: PolicySectionState) -> PolicySectionState:

    # 1. Read
    prior_reviews = state.get("prior_review", "")

    # 2. Conditional block only added to the prompt if prior reviews exist
    # TODO: format prior_reviews into formatted_history (see Review schema above for fields)
    history_block = HISTORY_BLOCK_TEMPLATE.format(formatted_history=...) if prior_reviews else ""

    # 3. Structured LLM call
    result = reviewer_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT.format(
            section_text  = state["section_text"],
            references    = state.get("references", ""),
            draft         = state.get("draft", ""),
            history_block = history_block,
        )),
    ])
    review_requested= state.get("review_requested", [])
    first   = (state.get("retry_count_writer", 0) == 0)
    routing = None
    
    """
    First Pass (No Rewrite Flag) -> Return Results 
    First Pass (Rewrite Flag)    -> Route to Writer

    Retry Pass means it is getting a call from the writer is performing a QA check almost

    Retry Pass -> Review returns reviews -> Send back to writer with context
    Retry Pass -> Review returns no reviews (empty list) -> Return Results 
    """
    if first and not review_requested:
        routing = "exit"
    elif first and review_requested:
        routing = "writer_node"
    # Mean no reviews therefore no errors:
    elif len(result) == 0: 
        routing = "exit"
    # Error was found and not the first pass, send back to writer 
    else:
        routing = "writer_node"
    # Save it (keep in mind this is mock small example and we cannot use generic names for all of these as they will likely need to be shared)
    state["routing"] = routing

    # 4. Write back to state 
    state["reviewer_feedback"] = state.get("reviewer_feedback", []) + result
    state["prior_review"]      = result
    state["retry_count_writer"]= state.get("retry_count_writer", 0) + 1
    state["traversal"]         = state.get("traversal", []) + [f"reviewer_node:cycle_{state['retry_count_writer']}"]

    return state

def route_after_review(state) -> str:
    return state["routing"]

# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
#
#   writer_node  ->  reviewer_node  -> (conditional) -> exit 
#        ^                                     |
#        |------------ loop back --------------|
#

def build_retry_loop_graph() -> StateGraph:
    graph = StateGraph(PolicySectionState)
    graph.add_node("writer_node",  writer_node)
    graph.add_node("reviewer_node", reviewer_node)
    graph.set_entry_point("writer_node")
    graph.add_edge("writer_node", "reviewer_node")
    graph.add_conditional_edges(
        "reviewer_node",
        route_after_review,
        {
            "writer_node" : "writer_node",  # loop back to writer
            "exit"        : END,            # exit no reviews or review not requested
        },
    )
    return graph.compile()

retry_loop_graph = build_retry_loop_graph()