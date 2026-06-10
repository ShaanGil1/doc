# LLM client. Real Gemini or FakeLLM depending on env.
"""
FakeLLM by default (USE_FAKE_LLM=1). Set USE_FAKE_LLM=0 to use real Gemini.
When using real Gemini, GOOGLE_API_KEY must be set.

GEMINI_MODEL env var overrides the model name.

The route only calls .with_structured_output(schema).invoke(prompt), so any
LangChain chat model that supports structured output drops in here.
"""

import os
import time
from typing import Dict, List, Type

from pydantic import BaseModel


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


# Per-call delay used by FakeLLM only. Real Gemini ignores this.
FAKE_LLM_DELAY_SECONDS: float = 0.0

# Tests register scripted responses keyed by schema class name.
FAKE_RESPONSES: Dict[str, List[BaseModel]] = {}

# Tests can instead register responses keyed by a substring of the prompt. Used
# when section branches run in parallel: a FIFO queue would hand a branch the
# wrong section's response, so we match on prompt content instead. Reads are
# non-destructive (no pop), so the single per-section retry re-runs cleanly.
FAKE_RESPONSES_BY_KEY: Dict[str, Dict[str, BaseModel]] = {}


# Reset FakeLLM state between tests.
def reset_fake_llm() -> None:
    global FAKE_LLM_DELAY_SECONDS
    FAKE_RESPONSES.clear()
    FAKE_RESPONSES_BY_KEY.clear()
    FAKE_LLM_DELAY_SECONDS = 0.0


# Queue scripted responses for a given output schema (FakeLLM only).
def register_fake_responses(schema_name: str, responses: List[BaseModel]) -> None:
    FAKE_RESPONSES[schema_name] = list(responses)


# Register prompt-keyed responses for a schema: {substring: response} (FakeLLM only).
def register_fake_responses_by_key(schema_name: str, mapping: Dict[str, BaseModel]) -> None:
    FAKE_RESPONSES_BY_KEY[schema_name] = dict(mapping)


# Set per-call latency in seconds (FakeLLM only).
def set_fake_delay(seconds: float) -> None:
    global FAKE_LLM_DELAY_SECONDS
    FAKE_LLM_DELAY_SECONDS = seconds


# Fake structured runnable. Matches a keyed response by prompt if registered,
# else pops the next scripted response off the FIFO queue.
class FakeStructuredRunnable:
    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema

    def invoke(self, prompt: str) -> BaseModel:
        if FAKE_LLM_DELAY_SECONDS > 0:
            time.sleep(FAKE_LLM_DELAY_SECONDS)
        keyed = FAKE_RESPONSES_BY_KEY.get(self.schema.__name__)
        if keyed:
            for key, response in keyed.items():
                if key in prompt:
                    return response
            return self.schema()
        queue = FAKE_RESPONSES.get(self.schema.__name__, [])
        if not queue:
            return self.schema()
        return queue.pop(0)


# Fake LLM client. Only with_structured_output is used by the route.
class FakeLLM:
    def with_structured_output(self, schema: Type[BaseModel]) -> FakeStructuredRunnable:
        return FakeStructuredRunnable(schema)


# Build a real Gemini client. Raises if GOOGLE_API_KEY is missing.
def build_gemini_client():
    from langchain_core.rate_limiters import InMemoryRateLimiter
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Export it in your shell or set USE_FAKE_LLM=1 to use the FakeLLM stub."
        )
    # Hardcoded request-rate cap. Complements the graph-level max_concurrency.
    # Retune or drop if your own wrapper already handles rate limiting.
    rate_limiter = InMemoryRateLimiter(requests_per_second=5)
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=api_key,
        temperature=0.0,
        rate_limiter=rate_limiter,
    )


# Module-level client. FakeLLM by default; real Gemini when USE_FAKE_LLM=0.
if os.environ.get("USE_FAKE_LLM", "1") == "1":
    llm_client = FakeLLM()
else:
    llm_client = build_gemini_client()
