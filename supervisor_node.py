"""
Purpose : A supervisor decomposes work into tasks, a dispatch node routes
          each task to the correct agent, agents loop back to dispatch.

The LLM only fires once inside the supervisor to produce the task list.
Everything after that is code popping from a queue and routing.
"""
from typing import Optional, TypedDict
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class SupervisorState(TypedDict):
    user_text               : str                 # the text the user wants improved
    additional_instructions : Optional[str]       # optional, user-provided guidance on what to focus on
    task_queue              : list[dict]          # tasks still to do
    completed               : list[dict]          # finished results
    routing                 : str                 # set by dispatch, read by router
    traversal               : list[str]


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class Task(BaseModel):
    description : str
    agent_type  : str   # "summarizer", "tone_adjuster", "formatter",


class TaskPlan(BaseModel):
    tasks : list[Task]


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

_base_llm = ChatGoogleGenerativeAI(
    model="place gemini model here",
    temperature=0.2,
    project="your-gcp-project",
)

planner_llm = _base_llm.with_structured_output(
    schema=TaskPlan.model_json_schema(),
    method="json_schema",
)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a writing supervisor. Given the user's text (and any additional
instructions they provided), decide which writing agents need to run and
in what order. Each task gets one agent_type from: summarizer, tone_adjuster,
formatter

Order by dependency. Do not invent work that was not needed.
"""

USER_PROMPT = """\
User text:
---
{user_text}
---
{instructions_block}
"""


# ---------------------------------------------------------------------------
# Supervisor Node - looks at user text, decides which agents need to run
# ---------------------------------------------------------------------------

def supervisor_node(state: SupervisorState) -> SupervisorState:

    # 1. Conditional block - only added if the user provided extra instructions
    instructions_block = f"Additional instructions: {state['additional_instructions']}\n" if state.get("additional_instructions") else ""

    # 2. LLM call - decide which agents need to run
    result = planner_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT.format(
            user_text          = state["user_text"],
            instructions_block = instructions_block,
        )),
    ])

    # 3. Write back
    state["task_queue"] = [t.model_dump() for t in result["tasks"]]
    state["traversal"]  = state.get("traversal", []) + ["supervisor_node"]

    return state


# ---------------------------------------------------------------------------
# Dispatch Node - pops next task, decides where to send it
# ---------------------------------------------------------------------------

def dispatch_node(state: SupervisorState) -> SupervisorState:

    queue = state.get("task_queue", [])

    if not queue:
        state["routing"] = "exit"
    else:
        task = queue.pop(0)
        state["task_queue"] = queue
        state["routing"]    = task["agent_type"]
        # Stash so the agent can read it
        state["current_description"] = task["description"]

    state["traversal"] = state.get("traversal", []) + ["dispatch_node"]

    return state


# ---------------------------------------------------------------------------
# Example agent - all follow the same contract: do work, loop back to dispatch
# ---------------------------------------------------------------------------
# In the real system each of these has its own prompt, schema, and LLM call/logic
# For this example they all share the same shape.

def _example_agent(agent_name: str, state: SupervisorState) -> SupervisorState:
    """Shared example logic. Real agents would have their own LLM calls here."""

    # TODO: build agent-specific prompt from state["current_description"] and state["user_text"]
    # TODO: invoke LLM, write suggestions back to state

    state["completed"] = state.get("completed", []) + [{
        "agent"       : agent_name,
        "description" : state.get("current_description", ""),
        "status"      : "done",
    }]
    state["traversal"] = state.get("traversal", []) + [agent_name]
    return state

def summarizer_node(state):           return _example_agent("summarizer", state)
def tone_adjuster_node(state):        return _example_agent("tone_adjuster", state)
def formatter_node(state):            return _example_agent("formatter", state)


# ---------------------------------------------------------------------------
# Router (trivial passthrough)
# ---------------------------------------------------------------------------

def route_after_dispatch(state) -> str:
    return state["routing"]


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
#
#  supervisor_node
#       |
#       v
#  dispatch_node  -----> exit (END)
#       |    ^
#       |    | (failure detected - re-plan)
#       |    |
#       |    +----------- supervisor_node <---+
#       |                                     |
#       +---> summarizer_node ----------------+
#       |                                     |
#       +---> tone_adjuster_node  ------------+
#       |                                     |
#       +---> formatter_node  ----------------+  (all agents loop back to dispatch)

AGENT_NODES = {
    "summarizer"          : summarizer_node,
    "tone_adjuster"       : tone_adjuster_node,
    "formatter"           : formatter_node,
}

def build_supervisor_graph() -> StateGraph:
    graph = StateGraph(SupervisorState)

    graph.add_node("supervisor_node", supervisor_node)
    graph.add_node("dispatch_node",   dispatch_node)
    for name, fn in AGENT_NODES.items():
        graph.add_node(name, fn)

    graph.set_entry_point("supervisor_node")
    graph.add_edge("supervisor_node", "dispatch_node")

    # Dispatch fans out to the correct agent (or exits)
    graph.add_conditional_edges(
        "dispatch_node",
        route_after_dispatch,
        {
            **{name: name for name in AGENT_NODES},   # one edge per agent type
            "supervisor_node" : "supervisor_node",    # failure re-plan
            "exit"            : END,
        },
    )

    # Every agent loops back to dispatch for the next task
    for name in AGENT_NODES:
        graph.add_edge(name, "dispatch_node")

    return graph.compile()

supervisor_graph = build_supervisor_graph()