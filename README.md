# LangGraph Scaffolding

## Overview
This is a LangGraph-based multi-agent system for writing, reviewing, and researching
financial policy documents. The system is organized as a set of independent subgraphs
that can be composed together via interaction graphs depending on the user's entry point.

This serves as a rough framework to help accelerate developement providing documentation and points on how to make these nodes/agents in the future.
The `examples/` folder as direct examples and there are some code snippets later in the README to explain some other concepts and ways to actually implement them.
Lots of node logic is empty and would need be done at the actually time for those tickets.

> **Note:** All example nodes are mock implementations. They demonstrate structure,
> state conventions, and wiring patterns not production logic. When building a
> real node, use the relevant example as a starting point, don't directly copy/paste everything

---

## Node Development Advice

### 1. Namespace your state keys
Prefix state fields with the agent name. Use `reviewer_tone`, not `tone`.
State gets merged across subgraphs and collisions are silent bugs. If a field is
shared across subgraphs, define it in a main file like: `main_example.py` and reference it explicitly.

### 2. If it can be code, don't make it an LLM call
Trivial routing decisions, counters, field mapping, and null checks all belong in Python.
Reserve LLM calls for tasks that genuinely require language understanding, and if we have a better more deterministic logic to do something, then do it that way (like regex), this will alleviate the latency of the whole system. 

### 3. One node, one job
If you are describing a node with "and then it also…" it should be two nodes.
Nodes are cheap. Long nodes are hard to debug, hard to retry, and hard to reuse.

### 4. Every node follows the error handling pattern
See the Error Handling snippet below. No exceptions. Every node wraps its logic
in try/except, writes errors to `state["errors"]`, writes a human-readable message
to `state["feedback"]`, and routes gracefully rather than crashing the graph. We need error handling for proper logging and we need logging to speed up debugging and enchancing the system.

### 5. Design for multiple callers
Nodes will be invoked from different interaction graphs with different upstream state.
Guard against missing optional fields explicitly - never assume a field is populated
just because it is in one flow. Use `.get()` with sensible defaults. We want to be able to modularize these agents to be dedicated to a task while still being reuseable meaning some logic and clever variable checks/declarations will be needed

### 6. Set a retry ceiling and respect it
Every thing that can loop needs a `max_retries` check. The system must always return something. If the ceiling is hit, return the best available output with an error flag do not let things run forever. 

### 7. Return output, clean up asyc
Once output is ready, return to the user. Logging, metadata writes, and housekeeping
go after the return as an asyc function, the agents can be heavy in runtime and we want to make sure we are saving time when we can

---

## Key Ideas

- **Subgraphs are independent** - each pipeline (writer, reviewer, researcher, citation)
  can be run standalone or composed via an interaction graph.
- **Interaction graphs are entry points** - they represent distinct user-initiated
  scenarios and orchestrate which subgraphs get called and in what order.
- **State is scoped per subgraph** - each pipeline owns its state. The interaction
  graphs handle mapping state across subgraph boundaries.

---

## Code Snippets

Some logic on how to implement some different scenerios 

### Error Handling

Every node must follow this structure. Writing to `state["errors"]` and
`state["feedback"]` keeps failures observable and allows the graph to route
gracefully rather than crash. The examples don't really show error catching in all (see `simple_node.py` for example) however, they **SHOULD** be added to all

```python
def my_node(state: MyState) -> MyState:
    try:
        # ... node logic here
        pass

    except Exception as e:
        state["errors"]   = state.get("errors", []) + [str(e)]
        state["feedback"] = "my_node failed - see errors for detail"
        # return state as-is so the graph can route on the error flag (logic needed to be implemented also be sure to log errors)

    return state
```

---

### Human in the Loop

This is not something that explicitly needs to be done but could be something down the road we consider. A good usecase would be if the intake agent doesn't have enough information and asks the human a question back, awaits a response and resumes.

The implementation below isn't a complete solution view langchain docs for more:
https://docs.langchain.com/oss/python/langgraph/interrupts

```python
from langgraph.types import interrupt

def intake_node(state):
    if not state["intake_sufficient"]:
        user_response = interrupt("Need more information: what document type is this?")
        state["user_input"] = user_response  # graph resumes here with user's reply

    return state
```
--- 
### Nested Subgraphs

Since we will have many agents and interactions we want to keep thing as simple as "I am passing this task to agent x and I will get back output y", I don't want to have to write up everything in that agent every single time I call it so I woud just call the parent and have the whole task completed with 1 simple call.

**main.py:**
```python
from writer_agent import writer_agent_node

graph = StateGraph(State)
graph.add_node("writer", writer_agent_node)
graph.add_edge("writer", END)
# ... More edges and nodes created

flow = graph.compile()
```

**writer_agent.py:**
```python
def writer_agent_node(state: WriterState) -> WriterState:
    # ... calls writer supervisor to decompose the task
    # ... supervisor builds a queue of sub-tasks
    # ... dispatches to tone, format, consistency agents
    # ... collects results, handles any failures
    # ... aggregates outputs into a final draft
    # ... lots more logic here
    return state
```

`main.py` has no knowledge of any of that. It draws one edge and moves on. We should be able to do this for everything

---

### Data Store / Search API (Researcher Agents)

Agents should not hardcode document paths unless they are domain-specific by design
(e.g. the J8 researcher always needs specific documents and can hardcode those targets).
The agentic flows in these nodes should closely mirror how the client actually does
their work. The way we search should reflect those patterns. At the end of the day
you are informing HOW to search and should fully leverage the search API by providing
the correct parameters for the right store.

An example would be using an LLM call to determine which store is appropriate given the context, then route to the right search call in code.
```python
class DBDecision(BaseModel):
    store  : Literal["documents", "fact_table", "graph_db"]
    reason : str   # brief explanation useful for debugging and observability

store_llm = base_llm.with_structured_output(DBDecision)

DB_PROMPT = """\
Given the research topic below, decide which data store to query.
- documents   : full policy text, source documents, reference material
- fact_table  : specific facts, figures, or citations that need grounding
- graph_db    : relationships between documents, entities, or policy links

Topic: {topic}
"""

def my_researcher_node(state: MyState) -> MyState:
    decision = store_llm.invoke(DB_PROMPT.format(topic=state["topic"]))

    if decision.store == "documents":
        results = search_api.query_documents(state["topic"])
    elif decision.store == "fact_table":
        results = search_api.query_facts(state["topic"])
    else:
        results = search_api.query_graph(state["topic"])

    if not results:
        state["errors"] = state.get("errors", []) + [f"no results from {decision.store}"]
        return state

    state["researcher_documents"] = results
    return state
```


---

## Full File Structure Example
Below is an example of what the file structure of project might look like based off the agentic graph that is presented below. This file structure would show the hierarchy of places and where each agent would rest in a file structure. 
```
finance_policy_agent/
│
├── README.md
│
├── interaction_graphs/                <- USER ENTRY POINTS
│   ├── document_write_flow.py
│   ├── document_review_flow.py
│   ├── search_flow.py
│   └── write_review_loop_flow.py
│
├── intake/
│   └── intake_agent.py                <- Runs once per flow. Processes intake form,
│                                         derives metadata
│
├── writer/
│   ├── main_graph.py                  <- Compiled writer subgraph
│   ├── writer_state.py                <- WriterState definition
│   ├── writer_supervisor.py           <- Decomposes task, dispatches to agents,
│   │                                     handles failures and retries
│   ├── writer_agents/
│   │   ├── formatter.py               <- Applies formatting rules
│   │   ├── summerizer.py              <- Summerizes content
│   │   ├── active_voice.py            <- Writes in active voice
│   │   └── tone adjuster.py           <- Rewrites for tone
│   └── specialist_writer/
│       └── specialist_writer_agent.py <- Writes in the style of an assigned specialist
│
├── researcher/
│   ├── main_graph.py                  <- Compiled researcher subgraph
│   ├── researcher_state.py            <- ResearcherState definition
│   ├── researcher_supervisor.py       <- Decomposes query into topics, assigns to
│   │                                     domain researchers, aggregates results
│   └── domain_researchers/
│       ├── ai_search_agent.py         <- General document search - semantic similarity,
│       │                                 document hierarchy, gap detection loop
│       ├── j8_researcher.py           <- J8-specific research across FMRs, parent
│       │                                 policies, FAR, and SFFAS
│       └── leases_researcher/
│           ├── leases_researcher.py   <- Entry point for leases-specific research
│           └── leases_workflow.py     <- Nested subgraph for leases research steps
│
├── reviewer/
│   ├── main_graph.py                  <- Compiled reviewer subgraph
│   ├── reviewer_state.py              <- ReviewerState definition
│   ├── reviewer_supervisor.py         <- Runs all review checks, collects failures,
│   │                                     routes to scoring, flags issues for writer
│   └── review_agents/
│       ├── reviewer_scoring.py        <- Compiles failed cases, evaluates severity,
│       │                                 produces readable output for Review Tab
|       ├── content_critique.py        <- Evaluates substance and completeness
|       ├── consistancy.py             <- Makes sure facts and information are aligned
│       └── styleguide_reviewer.py     <- Enforces style guide compliance
│
└── citation/
    ├── main_graph.py                  <- Compiled citation subgraph
    ├── citation_state.py              <- CitationState definition
    └── citation_agents/
        ├── citation_required.py       <- Determines if a citation is needed
        ├── fact_check.py              <- Verifies claim against source material
        └── citation_formatter.py      <- Formats the final citation for output
```
---

## Examples Reference

### main_example.py
Shows how a LangGraph main file might look and how nodes created and draw. This is a minimal example to understand LangGraph and how this might look. Purpose is to show flow, show what calls what, how conditional edges work, state variables and overall structure.

---

### simple_node.py
The atomic unit - one node, one LLM call, clean state in/out.
Shows node function signature, reading from state, conditional prompt injection,
structured LLM call, writing results back to state. The baseline every node follows.

---

### writer_node.py and reviewer_node.py
Two nodes that are independent by design and composable by wiring.

Each node is fully self-contained and can be called from any interaction graph on
its own without the other present:

- The **writer node** takes a section and context, produces a draft, and writes it
  to state.
- The **reviewer node** takes a draft, evaluates it, sets a `needs_revision` flag
  and structured feedback, and writes to state.

The loop between them is formed entirely at the graph level. The conditional edge
is is created (example in `writer_node.py`) and routes back to the writer if needed.
`max_retries` is enforced to prevent infinate looping


---

### supervisor_node.py
A supervisor that decomposes work, assigns tasks via a queue, and handles failures.
Shows task decomposition, routing to worker nodes, and the how a queue and "dispatcher" node would manage the tasks

---
