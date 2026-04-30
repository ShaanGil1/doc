# Reviewer subgraph topology (sequential).

from langgraph.graph import StateGraph, START, END

from writer_response.state import ReviewerRouteState
from writer_response.supervisor import run_reviewer, revalidate_and_filter
from writer_response.response_agents.registry import ROUTABLE_RESPONSE_AGENTS


# Loop through violations one at a time and call the fixer for each
def run_fixers(state: ReviewerRouteState) -> dict:
    suggestions = []
    for violation in state.get("violations") or []:
        target = violation.target_response_agent
        if not target or target not in ROUTABLE_RESPONSE_AGENTS:
            continue
        state["current_violation"] = violation
        fixer_function = ROUTABLE_RESPONSE_AGENTS[target][0]
        result = fixer_function(state)
        suggestions.extend(result.get("response_suggestions") or [])
    return {"response_suggestions": suggestions}


# Assemble the graph: three nodes wired in a straight line
# TODO: Parrelize the dispatched agents instead of running them sequentially
def build_writer_response_graph():
    graph = StateGraph(ReviewerRouteState)
    graph.add_node("run_reviewer", run_reviewer)
    graph.add_node("run_fixers", run_fixers)
    graph.add_node("revalidate_and_filter", revalidate_and_filter)

    graph.add_edge(START, "run_reviewer")
    graph.add_edge("run_reviewer", "run_fixers")
    graph.add_edge("run_fixers", "revalidate_and_filter")
    graph.add_edge("revalidate_and_filter", END)
    return graph.compile()
