# Policy Concierge — Logging & Observability Guide

> **Audience:** Engineering team working on Policy Concierge
> **Stack:** Angular (frontend) + Python/FastAPI (backend) + Langfuse (agent layer) + Loki (everything else)
> **Last updated:** March 2026

---

## Table of Contents

- [Why We're Doing This](#why-were-doing-this)
- [Architecture Overview](#architecture-overview)
- [The Two Destinations](#the-two-destinations)
- [Core Principles](#core-principles)
- [Naming Conventions](#naming-conventions)
- [ID Hierarchy & Span Lifecycle](#id-hierarchy--span-lifecycle)
- [Error Code System](#error-code-system)
- [Frontend Instrumentation (Angular)](#frontend-instrumentation-angular)
- [Backend Instrumentation (FastAPI)](#backend-instrumentation-fastapi)
- [Agent Layer (Langfuse)](#agent-layer-langfuse)
- [What the Packets Look Like](#what-the-packets-look-like)
- [What NOT to Log](#what-not-to-log)
- [Quick Reference Cheatsheet](#quick-reference-cheatsheet)

---

## Why We're Doing This

We want to be able to answer these questions without guessing:

- **"A user says the writer agent was slow."** → We can trace from their session to the exact span that took too long.
- **"Which features are people actually using?"** → We have event logs for every button press and flow entry.
- **"The reviewer agent gave a weird result."** → Langfuse has the full prompt/completion/token trace for that generation.
- **"Something broke in production."** → We have a unique error code, a trace ID, and structured context to find it fast.

The goal is not to log *more*. It's to log *well* — one rich log line beats ten skinny ones.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    POLICY CONCIERGE                      │
│                                                         │
│  ┌──────────────┐         ┌──────────────────────────┐  │
│  │   Angular     │  HTTP   │   FastAPI Backend         │  │
│  │   Frontend    │────────▶│                          │  │
│  │              │ trace-  │  ┌─────────┐             │  │
│  │  OTel JS SDK │ parent  │  │ Routes  │  OTel SDK   │  │
│  └──────┬───────┘ header  │  └────┬────┘             │  │
│         │                 │       │                   │  │
│         │                 │       ├──── Policy DB     │  │
│         │                 │       │                   │  │
│         │                 │  ┌────▼─────────────┐    │  │
│         │                 │  │  agents/ folder   │    │  │
│         │                 │  │  ┌─────────────┐  │    │  │
│         │                 │  │  │ Writer Agent │  │    │  │
│         │                 │  │  │ Reviewer     │  │    │  │
│         │                 │  │  │ Research     │  │    │  │
│         │                 │  │  └──────┬──────┘  │    │  │
│         │                 │  └─────────┼─────────┘    │  │
│         │                 └────────────┼──────────────┘  │
│         │                              │                 │
└─────────┼──────────────────────────────┼─────────────────┘
          │                              │
          ▼                              ▼
   ┌──────────────┐              ┌──────────────┐
   │     Loki     │              │   Langfuse   │
   │              │              │              │
   │ • sessions   │              │ • prompts    │
   │ • page views │              │ • completions│
   │ • clicks     │              │ • token usage│
   │ • errors     │              │ • agent spans│
   │ • latency    │              │ • eval scores│
   │ • searches   │              │              │
   └──────┬───────┘              └──────────────┘
          │
          ▼
   ┌──────────────┐
   │   Grafana    │  (later — we're just making sure
   │   Dashboard  │   everything is Grafana-compatible)
   └──────────────┘
```

**Rule of thumb:** if the code lives in the `agents/` folder, it logs to **Langfuse**. Everything else logs to **Loki**.

---

## The Two Destinations

### Loki — General Application Observability

Everything that *isn't* an LLM call. This is the bread and butter:

| What | Example |
|------|---------|
| User session events | login, logout, session timeout |
| Page navigation | user visited `/intake`, `/editor`, `/review` |
| Button presses | clicked "Submit Form", "Accept Suggestion", "Export PDF" |
| Feature usage | which flows are used, how often, by whom |
| Search queries | what users search for in Research |
| HTTP errors | 400s, 500s, timeouts |
| Latency | time for non-agent operations (DB queries, API calls) |
| Business events | intake form submitted, document exported |

### Langfuse — Agent/LLM Observability

Anything that touches the LLM. Langfuse natively understands tokens, prompts, and costs:

| What | Example |
|------|---------|
| Writer agent generations | prompt → completion, tokens, latency |
| Reviewer agent runs | document in → errors/rules out |
| Research agent queries | search query → retrieved docs |
| Agent orchestration | which tools were called, in what order |
| Eval scores | quality scores on generations |

---

## Core Principles

### 1. Context Over Volume

**One wide, structured log > many small logs.**

```python
# ❌ BAD — three skinny logs for one action
logger.info("User clicked submit")
logger.info("Form data validated")
logger.info("Intake created successfully")

# ✅ GOOD — one rich log with all context
logger.info("intake_form_submitted", extra={
    "session_id": session_id,
    "interaction_id": interaction_id,
    "user_id": user_id,
    "form_type": "auto_liability",
    "field_count": 23,
    "duration_ms": 1450,
    "status": "success",
})
```

The single entry has everything you need to filter, group, and debug. You can query Loki with `{interaction_id="xyz"}` and get the full picture in one line.

### 2. Reduce Redundancy

If a field is already captured elsewhere in the same log context, don't duplicate it.

**Fields you should NOT include because they're already present:**

| Redundant Field | Why It's Redundant |
|---|---|
| `method` (GET/POST) | Already in the operation name — "fetch" implies GET, "write" implies POST |
| `http_status` | Redundant with `error_code` — if there's an error, the code tells you what happened; if there's no error, the status was 2xx |
| `timestamp` | Automatically added by the logging framework |
| `service_name` | Set once in OTel resource config, attached to every log |
| `trace_id` | Auto-attached by OTel SDK — don't manually add it |
| Error detail fields already sent to the client | If the client gets `{ code: "E1042", message: "..." }`, don't also log those same fields separately — just log the `error_code` |

**What you SHOULD include:** things unique to this specific event — `session_id`, `interaction_id`, `user_id`, the business context (what document, what action, what result).

### 3. One Error Code, One Location

Every distinct error gets a unique code in the `E1XXX` format. That code should appear **exactly once** in the codebase — in the place where the error originates. This means you can grep `E1042` and land on exactly one line of code.

### 4. Spans Have a Lifecycle

Every user interaction opens a span. That span closes when the interaction is done. Don't leave spans open across unrelated actions.

### 5. Minimize Cross-Boundary Payloads

When the frontend sends context to the backend, it sends **IDs only** — not the full trace state. The backend looks up what it needs. The `traceparent` header handles trace continuity automatically.

---

## Naming Conventions

Everything is **snake_case**. No exceptions.

### Log Event Names

Format: `{domain}_{action}_{result}`

```
intake_form_submitted
document_opened
suggestion_accepted
suggestion_rejected
review_started
review_completed
research_query_executed
session_started
session_expired
button_pressed
page_viewed
```

### Attribute Names

```
session_id          — top-level session identifier
interaction_id      — one user interaction (form submit, doc edit session, review run)
user_id             — the user
document_id         — which policy document
error_code          — E1XXX format
duration_ms         — always milliseconds, always an integer
page_path           — e.g. "/editor", "/intake", "/review"
action_type         — e.g. "click", "submit", "navigate", "search"
element_id          — the UI element interacted with (button ID, input name)
feature_name        — e.g. "writer_agent", "reviewer_agent", "research", "intake_form"
```

### Agent-Specific (Langfuse)

```
generation_id       — unique ID per agent generation call
agent_name          — "writer" | "reviewer" | "research"
model_name          — e.g. "gpt-4", "claude-sonnet-4"
prompt_tokens       — input token count
completion_tokens   — output token count
```

---

## ID Hierarchy & Span Lifecycle

```
session_id  (created on login / app load, expires after 30min idle)
│
│   Attached to: EVERY log line and span, always
│
├── interaction_id  (created when user starts a distinct task)
│   │
│   │   Examples of what counts as "one interaction":
│   │   • Filling out and submitting the intake form
│   │   • One editing session in the document editor
│   │   • Running the reviewer agent on a document
│   │   • A research search query → viewing results
│   │
│   │   The interaction_id span OPENS when the task starts
│   │   and CLOSES when it completes (success or failure)
│   │
│   ├── Individual events within the interaction:
│   │   • button_pressed (action_type: "click")
│   │   • suggestion_accepted
│   │   • page_viewed
│   │
│   └── generation_id  (if the interaction involves an agent)
│       │   Created per LLM call, sent to Langfuse
│       │   Multiple generations can happen per interaction
│       │   (e.g., user accepts a suggestion, then asks for another)
│       │
│       └── trace_id / span_id  (auto by OTel, per HTTP round trip)
│
├── interaction_id_2  (user starts another task)
│   └── ...
│
└── interaction_id_3
    └── ...
```

**When to create a new `interaction_id`:**

- User navigates to a new flow (intake → editor → review)
- User explicitly starts a new task (clicks "New Search", "Run Review")
- User returns after being idle (but within the same session)

**When NOT to create a new one:**

- User clicks a button within the same flow — that's an event inside the current interaction
- Agent makes a follow-up call as part of the same user request

---

## Error Code System

### Format: `E{domain}{number}`

```
E1XXX — Authentication & Session
E2XXX — Intake Form & Validation
E3XXX — Document Editor
E4XXX — Writer Agent
E5XXX — Reviewer Agent
E6XXX — Research
E7XXX — Database & Storage
E8XXX — External Services
E9XXX — Infrastructure
```

### Rules

1. **One code = one `raise` statement.** If you grep `E4012` you should find exactly one place in the code.
2. **The error code goes in the exception, not just the log.** The client receives the code so support can reference it.
3. **Register every code** in `errors/registry.py` (or wherever we decide to centralize).

### Example

```python
# errors/codes.py — the registry
# Each code is defined ONCE here with its message template

ERROR_REGISTRY = {
    "E1001": "Session expired. Please log in again.",
    "E1002": "Invalid authentication token.",
    "E2001": "Required intake field missing: {field_name}",
    "E2002": "Policy type not supported: {policy_type}",
    "E4001": "Writer agent timed out after {timeout_s}s",
    "E4002": "Writer agent returned empty completion",
    "E5001": "Reviewer agent failed to parse document",
    "E5002": "Reviewer agent rule set not found: {rule_set_id}",
    "E7001": "Document not found: {document_id}",
    "E7002": "Database connection failed",
}
```

```python
# errors/exceptions.py

class PolicyConciergeError(Exception):
    def __init__(self, code: str, **context):
        self.code = code
        self.context = context
        template = ERROR_REGISTRY.get(code, "Unknown error")
        self.message = template.format(**context) if context else template
        super().__init__(self.message)


# Usage — this is the ONE place E4001 appears in the codebase
# agents/writer.py
async def generate(self, prompt: str):
    try:
        result = await self.llm.complete(prompt, timeout=30)
    except TimeoutError:
        raise PolicyConciergeError("E4001", timeout_s=30)

    if not result.text:
        raise PolicyConciergeError("E4002")

    return result
```

```python
# middleware/error_handler.py — catches all errors, logs once

@app.exception_handler(PolicyConciergeError)
async def handle_policy_error(request: Request, exc: PolicyConciergeError):
    logger.error("policy_error", extra={
        "error_code": exc.code,
        "error_context": exc.context,
        # session_id, interaction_id, trace_id are auto-attached by OTel
    })

    return JSONResponse(
        status_code=_code_to_status(exc.code),
        content={
            "error_code": exc.code,
            "message": exc.message,
            # NOT including: stack trace, internal context, raw exception
            # The client gets the code + human message, nothing more
        }
    )
```

---

## Frontend Instrumentation (Angular)

### Setup (one time)

Install dependencies:

```bash
npm install @opentelemetry/api \
  @opentelemetry/sdk-trace-web \
  @opentelemetry/sdk-trace-base \
  @opentelemetry/exporter-trace-otlp-http \
  @opentelemetry/context-zone-peer-dep \
  @opentelemetry/instrumentation \
  @opentelemetry/instrumentation-xml-http-request \
  @opentelemetry/resources
```

Create `src/telemetry.ts`:

```typescript
import { WebTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { ZoneContextManager } from '@opentelemetry/context-zone-peer-dep';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { XMLHttpRequestInstrumentation } from '@opentelemetry/instrumentation-xml-http-request';
import { Resource } from '@opentelemetry/resources';

// Angular uses XMLHttpRequest under the hood (HttpClient),
// so we instrument XHR, not fetch.

const provider = new WebTracerProvider({
  resource: new Resource({ 'service.name': 'policy-concierge-frontend' }),
});

provider.addSpanProcessor(
  new BatchSpanProcessor(
    new OTLPTraceExporter({
      url: '/api/v1/traces',  // proxy to your collector
    })
  )
);

// ZoneContextManager reuses Angular's existing Zone.js
// so trace context propagates through async operations automatically
provider.register({ contextManager: new ZoneContextManager() });

registerInstrumentations({
  instrumentations: [
    new XMLHttpRequestInstrumentation({
      propagateTraceHeaderCorsUrls: [/your-api-domain\.com/],
    }),
  ],
});

export const tracer = provider.getTracer('policy-concierge-frontend');
```

Import in `src/main.ts` before bootstrap:

```typescript
import './telemetry';
import { bootstrapApplication } from '@angular/platform-browser';
// ... rest of bootstrap
```

### Session & Interaction Tracking Service

```typescript
// services/observability.service.ts

import { Injectable } from '@angular/core';
import { tracer } from '../telemetry';
import { Span } from '@opentelemetry/api';
import { v4 as uuid } from 'uuid';

const SESSION_TIMEOUT_MS = 30 * 60 * 1000;

@Injectable({ providedIn: 'root' })
export class ObservabilityService {
  readonly session_id = uuid();
  private interaction_id: string | null = null;
  private interaction_span: Span | null = null;
  private last_activity = Date.now();

  /** Call on every user action to keep session alive */
  touch(): void {
    this.last_activity = Date.now();
  }

  is_session_expired(): boolean {
    return Date.now() - this.last_activity > SESSION_TIMEOUT_MS;
  }

  /** Start a new interaction (e.g., user opens editor, starts review) */
  start_interaction(name: string, attrs: Record<string, string> = {}): string {
    // Close any open interaction first
    this.end_interaction();

    this.interaction_id = uuid();
    this.interaction_span = tracer.startSpan(`interaction.${name}`, {
      attributes: {
        'session.id': this.session_id,
        'interaction.id': this.interaction_id,
        ...attrs,
      },
    });

    return this.interaction_id;
  }

  /** Close the current interaction span */
  end_interaction(attrs: Record<string, string> = {}): void {
    if (this.interaction_span) {
      Object.entries(attrs).forEach(([k, v]) =>
        this.interaction_span!.setAttribute(k, v)
      );
      this.interaction_span.end();
      this.interaction_span = null;
      this.interaction_id = null;
    }
  }

  /** Log a discrete event within the current interaction */
  log_event(event_name: string, attrs: Record<string, string> = {}): void {
    this.touch();
    const span = tracer.startSpan(event_name, {
      attributes: {
        'session.id': this.session_id,
        'interaction.id': this.interaction_id ?? 'none',
        ...attrs,
      },
    });
    span.end(); // instant event — open and close immediately
  }

  /** Convenience: log a button press */
  log_button_press(element_id: string, feature_name: string): void {
    this.log_event('button_pressed', {
      'action_type': 'click',
      'element_id': element_id,
      'feature_name': feature_name,
    });
  }

  /** Convenience: log a page view */
  log_page_view(page_path: string): void {
    this.log_event('page_viewed', {
      'action_type': 'navigate',
      'page_path': page_path,
    });
  }

  /** Get headers to send with backend requests */
  get_context_headers(): Record<string, string> {
    // traceparent is auto-injected by OTel XHR instrumentation
    // we only add our custom IDs
    return {
      'X-Session-Id': this.session_id,
      'X-Interaction-Id': this.interaction_id ?? '',
    };
  }
}
```

### Usage in Components

```typescript
// intake-form.component.ts

export class IntakeFormComponent implements OnInit, OnDestroy {
  constructor(
    private obs: ObservabilityService,
    private http: HttpClient,
  ) {}

  ngOnInit() {
    // New interaction starts when user opens the intake form
    this.obs.start_interaction('intake_form', {
      'feature_name': 'intake_form',
    });
    this.obs.log_page_view('/intake');
  }

  ngOnDestroy() {
    // Interaction closes when user leaves the page
    this.obs.end_interaction();
  }

  on_field_change(field_name: string) {
    // We do NOT log every keystroke — just meaningful actions
    // This is intentionally not logged
  }

  async on_submit(form_data: IntakeForm) {
    this.obs.log_button_press('submit_intake', 'intake_form');

    const start = performance.now();
    const res = await this.http.post('/api/intake', form_data, {
      headers: this.obs.get_context_headers(),
    }).toPromise();
    const duration_ms = Math.round(performance.now() - start);

    // Interaction completes on successful submit
    this.obs.end_interaction({
      'status': 'success',
      'duration_ms': String(duration_ms),
    });
  }
}
```

---

## Backend Instrumentation (FastAPI)

### Setup

```bash
pip install opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-http \
  opentelemetry-instrumentation-fastapi \
  python-json-logger
```

```python
# telemetry.py — run once at startup

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import logging
import json_log_formatter

# Resource identifies this service in all telemetry
resource = Resource.create({"service.name": "policy-concierge-backend"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanExporter(OTLPSpanExporter(endpoint="http://collector:4318/v1/traces"))
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("policy-concierge-backend")

# JSON structured logging → OTel Collector → Loki
handler = logging.StreamHandler()
handler.setFormatter(json_log_formatter.JSONFormatter())
logger = logging.getLogger("policy_concierge")
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def instrument_app(app):
    """Call this in main.py after creating the FastAPI app."""
    # Auto-instruments all routes: reads traceparent header,
    # creates spans for each request, records HTTP attributes
    FastAPIInstrumentor.instrument_app(app)
```

### Middleware: Extract Custom Headers

```python
# middleware/context.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Extracts our custom IDs from frontend headers
    and makes them available to all route handlers.

    The traceparent header is handled automatically by OTel —
    we only deal with our own IDs here.
    """

    async def dispatch(self, request: Request, call_next):
        # Pull IDs from headers — these are the ONLY things
        # the frontend sends for context (not the whole trace)
        request.state.session_id = request.headers.get("x-session-id", "unknown")
        request.state.interaction_id = request.headers.get("x-interaction-id", "")

        response = await call_next(request)
        return response
```

### Route Handler Example

```python
# routes/intake.py

from fastapi import APIRouter, Request
from telemetry import tracer, logger
import time

router = APIRouter()

@router.post("/api/intake")
async def submit_intake(request: Request, body: IntakeFormBody):
    session_id = request.state.session_id
    interaction_id = request.state.interaction_id

    with tracer.start_as_current_span("intake.submit") as span:
        span.set_attribute("session.id", session_id)
        span.set_attribute("interaction.id", interaction_id)

        start = time.time()

        # Validate
        errors = validate_intake(body)
        if errors:
            raise PolicyConciergeError("E2001", field_name=errors[0])

        # Save to DB (OTel auto-instruments common DB libraries)
        document = await create_document_from_intake(body)

        duration_ms = int((time.time() - start) * 1000)

        # ONE log line with ALL context
        logger.info("intake_form_submitted", extra={
            "session_id": session_id,
            "interaction_id": interaction_id,
            "user_id": body.user_id,
            "document_id": document.id,
            "policy_type": body.policy_type,
            "field_count": len(body.fields),
            "duration_ms": duration_ms,
            "status": "success",
        })

        return {"document_id": document.id}
```

---

## Agent Layer (Langfuse)

Everything in the `agents/` folder uses Langfuse instead of our Loki logger. Langfuse accepts OpenTelemetry spans via `LangfuseSpanProcessor`, so the setup is similar.

```python
# agents/base.py

from langfuse import Langfuse
from langfuse.openai import openai  # drop-in wrapper
# OR if using the OTel integration:
# from langfuse import LangfuseSpanProcessor

langfuse = Langfuse()

class BaseAgent:
    """
    All agents inherit from this.
    Langfuse tracing is automatic via the decorator.
    """
    agent_name: str = "base"

    def create_trace(self, session_id: str, interaction_id: str, generation_id: str):
        """Start a Langfuse trace for this agent call."""
        return langfuse.trace(
            name=f"{self.agent_name}_agent",
            session_id=session_id,        # links to Loki logs
            metadata={
                "interaction_id": interaction_id,  # links to Loki logs
                "generation_id": generation_id,
            },
        )
```

```python
# agents/writer.py

from agents.base import BaseAgent
from uuid import uuid4

class WriterAgent(BaseAgent):
    agent_name = "writer"

    async def generate(
        self,
        prompt: str,
        session_id: str,
        interaction_id: str,
    ) -> str:
        generation_id = str(uuid4())

        trace = self.create_trace(session_id, interaction_id, generation_id)

        # Langfuse auto-captures: prompt, completion, tokens, latency, model
        generation = trace.generation(
            name="writer_generation",
            model="gpt-4",
            input=prompt,
            metadata={"generation_id": generation_id},
        )

        result = await self.llm.complete(prompt)

        generation.end(output=result.text)

        # Return the generation_id so the caller can reference it
        return result.text, generation_id
```

```python
# routes/editor.py — calling the agent from a route

@router.post("/api/editor/suggest")
async def get_suggestion(request: Request, body: SuggestionRequest):
    session_id = request.state.session_id
    interaction_id = request.state.interaction_id

    # The agent call goes to Langfuse
    text, generation_id = await writer_agent.generate(
        prompt=body.prompt,
        session_id=session_id,
        interaction_id=interaction_id,
    )

    # The HTTP/business event goes to Loki
    # Note: we log the generation_id so you can cross-reference
    # from Loki → Langfuse if needed
    logger.info("suggestion_generated", extra={
        "session_id": session_id,
        "interaction_id": interaction_id,
        "generation_id": generation_id,  # the bridge between Loki and Langfuse
        "document_id": body.document_id,
        "agent_name": "writer",
        "status": "success",
    })

    return {"text": text, "generation_id": generation_id}
```

**The `generation_id` is the bridge.** If you find a suspicious log in Loki, you grab the `generation_id` and search for it in Langfuse to see the full prompt/completion/token detail. If you find a weird generation in Langfuse, you grab the `session_id` and search Loki to see what the user was doing before and after.

---

## What the Packets Look Like

### Frontend → Backend HTTP Request

The frontend sends **IDs only** — not the full trace context, not duplicated attributes.

```
POST /api/editor/suggest HTTP/1.1
Host: api.policyconcierge.com
Content-Type: application/json

# Auto-injected by OTel (trace continuity):
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

# Our custom IDs (set by ObservabilityService.get_context_headers):
X-Session-Id: sess_a1b2c3d4
X-Interaction-Id: int_x7y8z9w0

# Body — just the business data, no logging context
{
  "document_id": "doc_123",
  "prompt": "Suggest a liability exclusion clause for..."
}
```

**What is NOT in the request:**
- No `user_id` (backend gets it from the auth token)
- No `page_path` (irrelevant to the backend)
- No `trace_id` as a custom header (already in `traceparent`)
- No duplicated session attributes in the body

### Log Line in Loki

```json
{
  "timestamp": "2026-03-15T14:32:01.123Z",
  "level": "info",
  "event": "suggestion_generated",
  "session_id": "sess_a1b2c3d4",
  "interaction_id": "int_x7y8z9w0",
  "generation_id": "gen_m3n4o5p6",
  "document_id": "doc_123",
  "agent_name": "writer",
  "status": "success"
}
```

**What is NOT in this log:**
- No `http_method` — we know it was POST because it's a generation
- No `http_status` — status is "success", that's enough; if it failed, there'd be an `error_code`
- No `user_agent` — not useful for debugging business logic
- No `request_body` — the prompt is in Langfuse, not here

### Error Log in Loki

```json
{
  "timestamp": "2026-03-15T14:32:03.456Z",
  "level": "error",
  "event": "policy_error",
  "error_code": "E4001",
  "error_context": {"timeout_s": 30},
  "session_id": "sess_a1b2c3d4",
  "interaction_id": "int_x7y8z9w0"
}
```

**That's it.** The error code `E4001` tells you exactly what happened (writer agent timeout) and exactly where in the code to look (one location). The `session_id` + `interaction_id` let you find everything else the user was doing.

---

## What NOT to Log

Seriously — this list matters as much as what we do log.

| Don't Log | Why |
|---|---|
| Every keystroke / input change | Noise. Log the submit, not the typing. |
| Full request/response bodies in Loki | Prompts and completions belong in Langfuse, not in general logs. |
| Successful health checks | They'll drown everything else. |
| Duplicate context | If `session_id` is on the span, don't also put it in the log message string. |
| PII in plain text | User emails, SSNs, etc. Use `user_id` to reference, never log raw PII. |
| Stack traces for expected errors | If it has an error code, the code is enough. Stack traces are for unexpected/unhandled errors only. |
| HTTP status codes alongside error codes | Redundant — the error code is more specific. |

---

## Quick Reference Cheatsheet

### "I'm building a new feature. What do I log?"

1. **Start of the flow:** `start_interaction()` in the Angular component's `ngOnInit`
2. **User actions:** `log_button_press()` for meaningful clicks, `log_page_view()` for navigation
3. **Backend handler:** one `logger.info("{event_name}", extra={...})` per meaningful operation
4. **Agent calls:** use Langfuse via the `agents/` base class, log the `generation_id` in Loki for cross-reference
5. **Errors:** raise `PolicyConciergeError("EXXXX")`, register the code in `errors/codes.py`, the middleware handles logging
6. **End of flow:** `end_interaction()` in `ngOnDestroy` or on completion

### "I need to add a new error code."

1. Pick the next number in the right domain range (E1XXX–E9XXX)
2. Add it to `errors/codes.py` with the message template
3. Use `raise PolicyConciergeError("EXXXX", **context)` in exactly ONE place
4. Done — the middleware logs it and the client gets it

### "I need to find what happened during a user's session."

1. Loki: `{session_id="sess_abc"}` → all events for that session
2. Narrow: `{interaction_id="int_xyz"}` → specific interaction
3. If it involves an agent: grab the `generation_id` from the log → search in Langfuse
4. If you need the HTTP trace: grab the `trace_id` from the OTel-enriched log → search in your trace backend

### Naming Quick Ref

```
IDs:         session_id, interaction_id, generation_id, document_id, user_id
Events:      {domain}_{action}_{result}  e.g. intake_form_submitted
Errors:      E{domain_number}{sequence}  e.g. E4001
Attributes:  snake_case always           e.g. duration_ms, feature_name, page_path
```
