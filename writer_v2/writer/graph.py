# Writer subgraph topology (sequential)

from langgraph.graph import StateGraph, START, END

from writer.state import WriterGraphState
from writer.supervisor import supervisor, validate_and_filter
from writer.writer_agents.registry import ROUTABLE_AGENTS


# Loop through dispatched agents one at a time, accumulating suggestions
def run_dispatched_agents(state: WriterGraphState) -> dict:
    suggestions = []
    for name in state.get("dispatched_agents") or []:
        node_function, _, _ = ROUTABLE_AGENTS[name]
        result = node_function(state)
        suggestions.extend(result.get("suggestions") or [])
    return {"suggestions": suggestions}


# Assemble the graph
# TODO: Parrelize the dispatched agents instead of running them sequentially
def build_writer_graph():
    graph = StateGraph(WriterGraphState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("run_dispatched_agents", run_dispatched_agents)
    graph.add_node("validate_and_filter", validate_and_filter)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "run_dispatched_agents")
    graph.add_edge("run_dispatched_agents", "validate_and_filter")
    graph.add_edge("validate_and_filter", END)
    return graph.compile()
