"""
Purpose : Show the top-level interaction graph that ties together intake,
          researcher, writer, and reviewer subgraphs into the full
          write-review loop.

Read this first to understand the overall flow 
"""
from typing import Optional, TypedDict
from langgraph.graph import StateGraph, END


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------
class TopLevelState(TypedDict):
    intake_form        : dict              # raw form data from the frontend
    document_metadata  : Optional[dict]    # derived by intake (doc type, audience, etc.)
    writer_state       : dict              # stores writer subgraph vars (if needed across cycles)
    # ... add more here (researcher_state, reviewer_state, citation_state, etc.) ...
    max_review_cycles  : int               # caller-controlled budget
    traversal          : list[str]
    errors             : list[str]


# ---------------------------------------------------------------------------
# Intake node (only node with logic shown at this level)
# ---------------------------------------------------------------------------
# Processes the intake form, derives metadata, checks sufficiency.

def intake_node(state: TopLevelState) -> TopLevelState:
    # TODO: process intake_form, extract document type, audience, scope
    state["document_metadata"] = {"doc_type": "policy", "audience": "internal"}
    state["traversal"] = state.get("traversal", []) + ["intake_node"]
    return state

# ... add more subgraphs and agents here (researcher, writer, reviewer, citation, etc.) ...
# In the real codebase each is a compiled graph with its own state:
#   from researcher.main_graph import researcher_graph
#   from writer.main_graph import writer_graph
#   from reviewer.main_graph import reviewer_graph
#   from citation.main_graph import citation_graph


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

def route_after_review(state) -> str:
    if state["review_passed"]:
        return "exit"
    if state["review_cycle"] >= state.get("max_review_cycles", 3):
        return "exit"
    return "writer_subgraph"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
#
#  intake_node
#       |
#       v
#  researcher_subgraph
#       |
#       v
#  writer_subgraph  <-----------+
#       |                       |
#       v                       |
#  reviewer_subgraph            |
#       |                       |
#       +---> (failed) ---------+  (loop back, up to max_review_cycles)
#       |                       
#       +---> (passed) --> END  
#

def build_write_review_loop() -> StateGraph:
    graph = StateGraph(TopLevelState)

    graph.add_node("intake_node",          intake_node)
    graph.add_node("researcher_subgraph",  researcher_subgraph)
    graph.add_node("writer_subgraph",      writer_subgraph)
    graph.add_node("reviewer_subgraph",    reviewer_subgraph)

    graph.set_entry_point("intake_node")

    # Linear: intake -> research -> write -> review
    graph.add_edge("intake_node",          "researcher_subgraph")
    graph.add_edge("researcher_subgraph",  "writer_subgraph")
    graph.add_edge("writer_subgraph",      "reviewer_subgraph")

    # After review: exit or loop back to writer
    graph.add_conditional_edges(
        "reviewer_subgraph",
        route_after_review,
        {
            "writer_subgraph" : "writer_subgraph",
            "exit"            : END,
        },
    )

    return graph.compile()

write_review_loop = build_write_review_loop()