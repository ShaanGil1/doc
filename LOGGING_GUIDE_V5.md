-----

## Table of Contents

1. [Why Log](#1-why-log)
2. [Architecture Overview](#2-architecture-overview)
3. [Loki vs Langfuse](#3-loki-vs-langfuse)
4. [How We Log Things](#4-how-we-log-things)
5. [The Span Tree](#5-the-span-tree)
6. [Passing Context Across Boundaries](#6-passing-context-across-boundaries)
7. [Trace Lifecycle and Span Basics](#7-trace-lifecycle-and-span-basics)
8. [Severity Levels](#8-severity-levels)
9. [Error Codes](#9-error-codes)
10. [Backend Setup (FastAPI)](#10-backend-setup-fastapi)
11. [The @traced Decorator](#11-the-traced-decorator)
12. [Agent Layer (Langfuse)](#12-agent-layer-langfuse)
13. [What NOT to Log](#13-what-not-to-log)
14. [Links](#14-links)

-----

## 1. Why Log

The questions we should be able to answer with logging fully set up:

- "A user says the writer agent was slow." We can trace from their session to the exact span that took too long.
- "Which features are people actually using?" We have event logs for every button press and flow entry.
- "The reviewer agent gave a weird result." Langfuse has the full prompt/completion/token trace for that generation.
- "Something broke in production." We have a unique error code, a trace ID, and structured context to find it fast.
- "Our intake form is slow, is it the frontend or backend?" We have cross-boundary traces that show exactly where time is spent.

The point is not to log more. One rich log line beats ten skinny ones. We don't want to overload the server with a bunch of useless logs but we also want to know what is happening inside of our application.

-----

## 2. Architecture Overview

Here's how the pieces connect:

- **Angular frontend** runs the OTel JS SDK. Logs anything that needs to be logged specifically on the frontend (clicking a button that doesn't trigger a backend call).
- **FastAPI backend** runs the OTel Python SDK. Logs everything on the backend whenever routes are called + rich logging when using agent workflow.
- **Langfuse** will be used to collect logs which are specific to LLMs (anything in the langfuse graph will be logged here).
- **Loki** will be used to collect all other logs: latencies, buttons clicked, etc.
- **Grafana** comes later. Making sure everything is Grafana-compatible now so we don't have to re-instrument later. Grafana will allow us to aggregate the logs and get some visualization with the logs as well.

**The boundary rule:** if the code lives in the agents folder, it logs to Langfuse. Everything else logs to Loki.

-----

## 3. Loki vs Langfuse

**Loki** gets everything that isn't an LLM call: session events, page navigation, button clicks, feature usage, search queries, HTTP errors, latency, business events.

**Langfuse** gets anything that touches the LLM: agent generations (prompt/completion/tokens/latency), reviewer runs, research queries, tool calls, eval scores.

That's the split. If it involves a model call, Langfuse. Everything else, Loki.

-----

## 4. How We Log Things

These are the patterns to follow.

### One Rich Log, Not Many Skinny Ones

Pack context into a single log line so you can filter, group, and debug from one place.

```python
# Don't do this - three separate logs for one action,
# it doesn't give me much information on what is actually happening
logger.info("User clicked submit")
logger.info("Form data validated")
logger.info("Intake created successfully")

# Do this - one log with all the context
logger.info("intake_form_submitted", extra={
    "session_id": session_id,
    "interaction_id": interaction_id,
    "user_id": user_id,
    "form_id": form_id,
    "duration_ms": 1450,
    "status": "success",
})
```

### Don't Duplicate What's Already There

If a field is already captured elsewhere in the same log context, skip it. If we can easily derive the content of that field don't log it either. A good example would be `user_id` and `username`, realistically we only need to log one of them rather than both, if we need both we can find one with the other.

### One Error Code, One Location

Every distinct error gets a unique code. That code should appear **exactly once** in the codebase, in the place where the error originates. Something like `E4001` should land on one line of code. This makes errors easier to trace and track down.

### Spans Have a Lifecycle

Every user interaction opens a span. That span closes when the interaction is done. If something errors, the span still closes but with an error status. Never leave spans dangling, be sure the code closes the spans when needed, logging excessive information will not help us. More on this in [Section 7](#7-trace-lifecycle-and-span-basics).

### Send IDs, Not State

When the frontend talks to the backend (or the backend dispatches to a worker), send **IDs only**. Don't send the full trace state, don't duplicate attributes, don't send context that the receiving end can look up itself. More on this in [Section 6](#6-passing-context-across-boundaries).

-----

## 5. The Span Tree

Session, interaction, and request are actual spans in a parent-child tree.

```
session_id  (created on login/app load, expires after x min idle, this is the outer most parent)
│
│
├── interaction_id  (one per user interaction)
│   │
│   │   Examples of "one interaction":
│   │     Filling out + submitting the intake form
│   │     Running a search query on the researcher agent/search tab
│   │     Running the reviewer agent on a document
│   │     A research search -> viewing results
│   │
│   │   Span OPENS when user enters the flow
│   │   Span CLOSES when the flow completes (success or failure)
│   │
│   ├── Events within the interaction:
│   │     Latencies
│   │     Timestamp
│   │     Extra variables for the interactions (such as setting selected)
│   │
│   └── generation_id  (if the interaction involves an agent)
│       │   Created per LLM call, sent to Langfuse
│       │   Multiple generations can happen per interaction
│       │
│       └── trace_id  (auto by OTel, per HTTP round trip)
│
└── interaction_id_2  (next user interaction)
    └── ...
```

**Create a new `interaction_id` when:** user navigates to a new flow, explicitly starts a new task, or returns after idle.

**Don't create one when:** user clicks a button within the same flow, or the agent makes a follow-up call in the same request. This example would be something like multiple searches/agent interactions in the same area of the app.

### Why these are spans, not labels

If session and interaction were just string labels stamped on logs, you'd need custom headers to carry them across service boundaries. By making them actual spans in the tree, `traceparent` carries the full lineage automatically. The backend span is a child of the interaction span, which is a child of the session span. You can walk up the tree to find the session, or walk down to find every request in an interaction.

### Memory is not a concern

The `BatchSpanProcessor` exports child spans as they finish. It doesn't wait for the parent to close. The session span itself is one object in browser memory with a start time and some attributes. If a session gets long enough that the trace is unwieldy in the trace backend, just start a new session trace at some threshold. But start simple.

### Session expiry and cleanup

The `session_id` is tied to the user's authenticated session. When the session expires (x min idle) or the user logs out, the frontend should end any open interaction spans and then end the session span.

You don't need to explicitly "close" the session trace in OTel. Spans are independent units and those do need to be closed. When there are no more active spans for a session, there's nothing to close. The session just stops producing telemetry. In Loki you can still query `{session_id="sess_abc"}` to see everything that happened during that session, even after it ended.

If you need to know _when_ a session ended, that's what the `session_ended` log event is for but more likely than not it will close due to idle time. The last event with a given `session_id` is the end of that session.

-----

## 6. Passing Context Across Boundaries

Every time work crosses a boundary (frontend to backend, backend to worker, worker to downstream service), pass two things:

- `session_id` - the top-level user session
- `interaction_id` - a single interaction within that session

That's it. These two values tie every request, log, and trace back to the same flow. Don't send full trace state, don't duplicate attributes, don't send anything the receiving end can look up itself.

`generation_id` is the bridge between Loki and Langfuse. See something weird in one, search the other by `generation_id`.

### Example

Same idea whether it's an HTTP call, internal service call, or background task. Just include the IDs.

```python
# Route handler dispatching to a background worker
@router.post("/api/documents/process")
async def process_document(request: Request, body: ProcessRequest):
    session_id = get_session_id()
    interaction_id = get_interaction_id()

    # Pass IDs only, worker fetches what it needs
    task = process_document_task.delay(
        session_id=session_id,
        interaction_id=interaction_id,
        document_id=body.document_id,
    )
    return {"task_id": task.id}
```

-----

## 7. Trace Lifecycle and Span Basics

A trace is a tree of **spans**. Each span is one unit of work with a name, start time, end time, and attributes. All spans in the same trace share a `trace_id`. In our system, the session span is the root, so `session_id` is effectively the `trace_id`.

See the [OTel Tracing spec](https://opentelemetry.io/docs/concepts/signals/traces/) for the full conceptual docs.

### Spans are nested

A span created inside another span automatically becomes its child.

```text
session
├── interaction
│   ├── generation_1
│   └── generation_2
└── interaction_2
    └── generation_1
```

In code, nesting just means nesting `with` blocks:

```python
with tracer.start_as_current_span("interaction") as span:
    span.set_attribute("interaction.type", "review")

    with tracer.start_as_current_span("generation_1"):
        result = await agent.generate(prompt)
```

The child auto-parents to whatever span is currently active. You don't wire it up yourself.

### Spans close automatically

When the `with` block exits, the span ends. You don't call `span.end()` manually.

```python
with tracer.start_as_current_span("generation_1") as span:
    result = await agent.generate(prompt)
    span.set_attribute("model", "gpt-4")
# span is done here
```

If an exception escapes the block, the SDK still closes the span and records the error on it automatically.

### Closing a span explicitly

Sometimes you need a span to live outside a `with` block, like session or interaction spans on the frontend that survive across component lifecycles. In that case you create the span manually and call `end()` yourself.

```python
# Manual span management (use sparingly)
span = tracer.start_span("interaction")
try:
    # ... work happens across multiple calls ...
    span.set_attribute("interaction.type", "research")
finally:
    span.end()  # you are responsible for closing this
```

Prefer `start_as_current_span` by default. Only use `start_span` + manual `end()` when the span genuinely needs to outlive a single function scope. If you forget to call `end()`, the span stays in memory forever and never exports.

Not every error needs `StatusCode.ERROR`. A 404 is the system working correctly, the resource just doesn't exist. Reserve `ERROR` for actual failures: DB down, timeouts, unhandled exceptions. See the [OTel Status spec](https://opentelemetry.io/docs/specs/otel/trace/api/#set-status) for more.

-----

## 8. Severity Levels

We use Python's standard logging levels. The OTel bridge maps them to severity numbers automatically. See the [OTel Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/#severity-fields) for the full spec.

| Level | When |
|-------|------|
| `DEBUG` | Dev only. Never in prod. |
| `INFO` | Normal operations. Most of our logs. |
| `WARN` | Unexpected but recovered. Retries, approaching rate limits. |
| `ERROR` | Something failed. Error code raised, user-facing op broke. |
| `FATAL` | Unrecoverable. DB down, required service unreachable. Should be rare. |

This is something that is a nice to have but is not critical to be implemented.

-----

## 9. Error Codes

Every distinct error gets a unique code. That code appears **exactly once** in the codebase so you can ctrl+f it and land on the one place it's raised. That's the whole system.

### How it works

Pick a code, put it in the error where it happens, don't use that code anywhere else.

```python
# This code only exists here, nowhere else in the codebase
async def generate(self, prompt: str):
    try:
        result = await self.llm.complete(prompt, timeout=30)
    except TimeoutError:
        raise Exception("E4001: Writer agent timed out")
```

```python
# Different error, different code, different location
async def get_document(self, document_id: str):
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise Exception("E7001: Document not found")
```

When something breaks in production, you search the code for that error string and you're looking at the exact line that failed. No digging through logs trying to figure out which of five possible places threw a generic "document not found".

### That's it

You don't need a fancy registry or a custom exception class to start. The important part is the habit: one code, one location, searchable. If the project grows and we want centralized error handling or error-to-HTTP-status mapping, we can layer that on later. The codes themselves are the foundation.

-----

## 10. Backend Setup (FastAPI)

We need a single place that initializes all OTel config: the TracerProvider (for spans), the LoggerProvider (for shipping Python logs to Loki through OTel), and the exported `tracer` and `logger` that the rest of the app will import. Something like a `telemetry/setup.py` would be the right home for this.

The FastAPI app entry point (wherever that ends up living) needs to call that init function before doing anything else. The one gotcha is that `FastAPIInstrumentor.instrument_app()` has to be called before adding middleware, otherwise middleware runs outside the trace context and span parenting breaks silently.

This is all standard OTel boilerplate, nothing we need to invent. The [OTel Python Getting Started guide](https://opentelemetry.io/docs/languages/python/getting-started/) and the [FastAPI instrumentation docs](https://opentelemetry.io/docs/languages/python/instrumentation/#fastapi) walk through exactly this setup and are the best starting point for whoever implements it.

-----

## 11. The @traced Decorator

The built-in OTel decorator doesn't work with `async def` ([known issue](https://github.com/open-telemetry/opentelemetry-python/issues/2831)), so we have a custom `@traced` wrapper in `telemetry/decorators.py`.

Slap `@traced` on a function and it handles all the span boilerplate for you: opens a span named after the function, marks it OK if it returns, records the exception and marks it ERROR if it throws, and closes the span either way. Works with both sync and async functions.

If you only need to trace a specific block inside a function rather than the whole thing, use `tracer.start_as_current_span()` as a context manager instead.

The full implementation is in `telemetry/decorators.py`. For more on manual instrumentation and tracing patterns see:

- [OTel Python Tracing docs](https://opentelemetry.io/docs/languages/python/instrumentation/#tracing)
- [OTel Python decorator issue](https://github.com/open-telemetry/opentelemetry-python/issues/2831)
- [OTel Tracing spec](https://opentelemetry.io/docs/concepts/signals/traces/)

-----

## 12. Agent Layer (Langfuse)

Everything in `agents/` logs to Langfuse. Langfuse understands LLM-specific stuff natively: tokens, prompts, completions, costs. That's why agent code logs there instead of Loki.

All agents extend a `BaseAgent` class in `agents/base.py` that handles creating a Langfuse trace with the `session_id`, `interaction_id`, and `generation_id` attached. Individual agents just call `create_trace()`, log their generation, and return the result along with the `generation_id`.

The `generation_id` is what bridges the two logging systems. When a route calls an agent, it logs the `generation_id` to Loki. So if you're looking at a request in Loki and want to see the full prompt/completion/token breakdown, grab the `generation_id` and search Langfuse. Works the other way around too.

```python
# Route handler calling an agent
@router.post("/api/editor/suggest")
async def get_suggestion(request: Request, body: SuggestionRequest):
    session_id = get_session_id()
    interaction_id = get_interaction_id()

    text, generation_id = await writer_agent.generate(
        prompt=body.prompt,
        session_id=session_id,
        interaction_id=interaction_id,
    )

    # generation_id is the bridge between Loki and Langfuse
    logger.info("suggestion_generated", extra={
        "generation_id": generation_id,
        "document_id": body.document_id,
    })

    return {"text": text, "generation_id": generation_id}
```

For more on how Langfuse handles tracing and generations see the [Langfuse Python SDK docs](https://langfuse.com/docs/sdk/python).

-----

## 13. What NOT to Log

- **Every keystroke.** Log the submit, not the typing.
- **Full request/response bodies in Loki.** Prompts and completions go to Langfuse, that's the whole point of the split.
- **Successful health checks.** They drown out everything useful.
- **`trace_id`, `span_id`, `session_id`, or `interaction_id` manually.** The logging bridge and span tree already handle these. Adding them to `extra={}` just creates duplicates.
- **PII in plain text.** Use `user_id` to reference, never log names/emails/etc directly.
- **Stack traces for expected errors.** The error code is enough. Save stack traces for unexpected failures.

-----

## 14. Links

- [OTel Python SDK](https://opentelemetry.io/docs/languages/python/) - Main docs for the Python SDK, start here if you're setting up OTel for the first time.
- [OTel Python Getting Started](https://opentelemetry.io/docs/languages/python/getting-started/) - Step by step walkthrough of instrumenting a Python app with traces, metrics, and logs.
- [OTel Python Manual Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) - Covers creating spans, adding attributes, recording exceptions, and wiring up the logging bridge.
- [OTel JS SDK (browser)](https://opentelemetry.io/docs/languages/js/getting-started/browser/) - Getting started guide for the browser SDK, relevant for our Angular frontend tracing.
- [OTel Tracing Concepts](https://opentelemetry.io/docs/concepts/signals/traces/) - Explains traces, spans, context propagation, and the data model behind everything we're doing.
- [OTel Collector Config](https://opentelemetry.io/docs/collector/configuration/) - How to configure the collector that sits between our app and the trace/log backends.
- [OTel Status Spec](https://opentelemetry.io/docs/specs/otel/trace/api/#set-status) - When to use OK vs ERROR vs UNSET on spans.
- [FastAPI Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/#fastapi) - Auto-instrumentation for FastAPI, creates spans per request and reads `traceparent` headers.
- [OTel Python Testing](https://opentelemetry.io/docs/languages/python/testing/) - How to use `InMemorySpanExporter` to assert against spans in your tests.
- [Langfuse Get Started](https://langfuse.com/docs/observability/get-started) - Quickstart for ingesting your first trace into Langfuse.
- [Langfuse Core Concepts](https://langfuse.com/docs/observability/data-model) - How Langfuse organizes traces, observations, generations, and sessions.
- [Langfuse Python SDK](https://langfuse.com/docs/sdk/python) - Full SDK reference for creating traces, spans, and generations in Python.
- [Langfuse Decorator Integration](https://langfuse.com/docs/sdk/python/decorators) - Using `@observe()` to automatically trace functions and LLM calls.
- [Grafana Loki LogQL](https://grafana.com/docs/loki/latest/query/) - Query language for searching logs in Loki, this is how you'll actually find stuff.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) - The spec behind `traceparent`, which is how trace context propagates across service boundaries.
