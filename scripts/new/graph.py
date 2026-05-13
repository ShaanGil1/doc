# Find_conflict graph

from typing import List
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from nodes.claim_extractor import extract_claims
from nodes.conflict_finder import find_conflicts_for_claim
from state import FindConflictState

# fan out one send per claim, LangGraph runs them in parallel
def dispatch_to_claims(state: FindConflictState) -> List[Send]:
    return [
        Send("find_conflicts_for_claim", {**state, "current_claim": claim})
        for claim in state["claims"]
    ]

# Build and compile graph
def build_find_conflict_graph():
    graph = StateGraph(FindConflictState)
    graph.add_node("extract_claims", extract_claims)
    graph.add_node("find_conflicts_for_claim", find_conflicts_for_claim)
    graph.add_edge(START, "extract_claims")
    graph.add_conditional_edges("extract_claims", dispatch_to_claims, ["find_conflicts_for_claim"])
    graph.add_edge("find_conflicts_for_claim", END)
    return graph.compile()
