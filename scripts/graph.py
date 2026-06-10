# Find_conflict subgraph. Pure wiring.
"""
Topology:
    START -> [Send fan-out, one per section] -> find_conflicts_for_section -> END

One Send is dispatched per section. LangGraph schedules the section branches
concurrently and reduces their flag outputs into state["flags"] via the `add`
reducer. Each branch does the whole per-section job: extract that section's
claims, look up sources per claim, consolidate (dedup) them, run one conflict
call over all the claims, and return the violations.

See state.py for the reducer wiring. See nodes/conflict_finder.py for the
per-section node and nodes/claim_extractor.py for the extraction helpers it uses.


PARALLELIZATION NOTES

LangGraph runs Send-spawned branches concurrently when you `.invoke()` the
graph. For sync node functions (which ours are), the runtime uses internal
threading to run them in parallel. max_concurrency (set on invoke in main.py)
caps how many run at once.

What is parallel:  sections (one branch each).
What is serial:    everything inside a branch (extract, then per-claim search,
                   then one conflict call).
"""

from typing import List

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes.conflict_finder import find_conflicts_for_section
from state import FindConflictState


# Conditional edge: fan out one Send per section. LangGraph runs them in parallel.
def dispatch_to_sections(state: FindConflictState) -> List[Send]:
    return [
        Send("find_conflicts_for_section", {**state, "current_section_id": str(section.id)})
        for section in state["sections_ordered"]
    ]


# Build and compile the find_conflict subgraph.
def build_find_conflict_graph():
    graph = StateGraph(FindConflictState)
    graph.add_node("find_conflicts_for_section", find_conflicts_for_section)
    graph.add_conditional_edges(START, dispatch_to_sections, ["find_conflicts_for_section"])
    graph.add_edge("find_conflicts_for_section", END)
    return graph.compile()
