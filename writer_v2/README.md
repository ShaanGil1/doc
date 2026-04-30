# writer_v2

LangGraph writer + reviewer agent system for policy/SOP document editing.
Two routes exposed as pure functions in `main.py`:

  writer_suggestions_for_section(section)     autocomplete-style proactive suggestions
  reviewer_suggestions_for_section(section)   fixes for reviewer-flagged violations

Reviewer is a stub this pass; real reviewer is built by another team.


## Setup

```bash
cd writer_v2
python -m venv .venv && source .venv/bin/activate
pip install langgraph langchain-core langchain-google-genai pydantic
```


## Run

With real Gemini:

```bash
export GOOGLE_API_KEY=your_key_here
python run_example.py
```

Without a key — falls back to FakeLLM canned outputs so the graph still
runs end-to-end:

```bash
python run_example.py
```


## Stub knobs

```bash
REVIEWER_REJECT_RATE=1.0 python run_example.py     # writer route filter
```

The reviewer route's revalidate step is real (not random) — it splices each
fix into the content and reruns produce_violations. Fixes that don't reduce
the violation count get dropped.


## Plug into a real route

```python
from shared.models import Section
from main import writer_suggestions_for_section, reviewer_suggestions_for_section

section = Section(title="...", content="...")
writer_results = writer_suggestions_for_section(section)
reviewer_results = reviewer_suggestions_for_section(section)
```

Both return List[Suggestion]. Section pydantic validates input.


## Swap the LLM

Edit build_llm() in llm_client.py. The variable name `llm_client` is what
everything imports — keep that stable.


## Layout

```
writer_v2/
├── main.py                       both route entry points
├── run_example.py                end-to-end demo (both routes)
├── llm_client.py                 Gemini + FakeLLM fallback
├── shared/models.py              Section, Suggestion, ReviewerViolation, LLMSuggestion
├── reviewer/checker.py           three blackbox stubs:
│                                   reviewer_check (writer route filter)
│                                   reviewer_produce_violations (reviewer route source)
│                                   reviewer_revalidate_fixes (reviewer route verifier)
│
├── writer/                       WRITER ROUTE (autocomplete)
│   ├── graph.py
│   ├── state.py
│   ├── supervisor.py             heuristic + LLM dispatcher in one node
│   ├── agent_base.py
│   └── writer_agents/            6 routable + 4 non-routable scaffolds
│
└── writer_response/              REVIEWER ROUTE (reactive fixers)
    ├── graph.py
    ├── state.py
    ├── supervisor.py
    ├── response_base.py
    └── response_agents/          12 routable (9 LLM + 3 regex) + 4 non-routable
```


## Topologies

Writer:
```
START → supervisor → [Send to dispatched agents] → finalize → validate → filter → END
                  ↘ "finalize" if dispatched is empty
```

Reviewer:
```
START → run_reviewer → [Send per violation by target_response_agent] → finalize → revalidate → filter → END
                    ↘ "finalize" if no violations
```

Reviewer-route dispatch is deterministic — each violation carries
target_response_agent. No LLM call at the dispatch stage.
