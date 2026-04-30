# LLM client. All graph nodes import `llm_client` from here.
"""
LLM client.

Production: Gemini via langchain-google-genai. Falls back to FakeLLM
locally if no GOOGLE_API_KEY or the lib isn't installed.

To swap providers, edit build_llm(). Keep the variable name `llm_client`
stable; everything else imports it.
"""

import os
from typing import Any, List, Type

from pydantic import BaseModel


GEMINI_MODEL = "gemini-2.5-flash-lite"
TEMPERATURE = 0.3


# --- Fake LLM (local fallback) --------------------------------------------

# Mimics .with_structured_output(schema).invoke() so the graph can run without an API key.
class FakeStructuredRunnable:
    """Mimics .with_structured_output(schema).invoke() for the schemas in this codebase."""

    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema

    def invoke(self, messages: List[Any]) -> BaseModel:
        schema_name = self.schema.__name__
        if schema_name == "DispatcherOutput":
            from writer.writer_agents.registry import ROUTABLE_AGENTS
            return self.schema(
                agents_to_run=list(ROUTABLE_AGENTS.keys()),
                reasoning="(FakeLLM: dispatching all routable agents)",
            )
        if schema_name == "LLMSuggestion":
            return self.fake_suggestion(messages)
        try:
            return self.schema()
        except Exception:
            return None  # type: ignore[return-value]

    # Match the prompt's opening keywords to a canned LLMSuggestion.
    def fake_suggestion(self, messages: List[Any]) -> BaseModel:
        """Match unique opening phrases in the system prompt to canned outputs."""
        system_message = ""
        if messages:
            content = getattr(messages[0], "content", "")
            system_message = content.lower() if isinstance(content, str) else ""

        # Writer-route prompts
        if "detects incomplete sentences" in system_message:
            return self.schema(
                suggestion_title="Complete hanging sentence",
                suggestion_text="(FakeLLM) Completed version of the hanging sentence.",
                original_text="(FakeLLM placeholder. Real Gemini would extract a real snippet.)",
            )
        if "rewrites wordy or overly complex" in system_message:
            return self.schema(
                suggestion_title="Tighten wordy phrase",
                suggestion_text="To submit an expense for reimbursement, employees must complete the form.",
                original_text="In order to submit an expense for reimbursement, employees must complete the form.",
            )

        # Response-fixer prompts share an opener; branch on rule keyword
        if "fixing a specific rule violation" in system_message:
            if "passive voice" in system_message:
                return self.schema(
                    suggestion_title="Rewrite in active voice",
                    suggestion_text="employees must submit the expense form",
                    original_text="must be submitted",
                )
            if "35 words" in system_message:
                return self.schema(
                    suggestion_title="Split long sentence",
                    suggestion_text="(FakeLLM) Split version with two shorter sentences.",
                    original_text="(FakeLLM placeholder)",
                )
            if "no contractions" in system_message:
                return self.schema(
                    suggestion_title="Expand contraction",
                    suggestion_text="will not",
                    original_text="won't",
                )

        return self.schema(suggestion_title="", suggestion_text="", original_text="")


class FakeLLM:
    def with_structured_output(self, schema: Type[BaseModel]) -> FakeStructuredRunnable:
        return FakeStructuredRunnable(schema)

    def invoke(self, messages: List[Any]) -> Any:
        class Response:
            content = "(FakeLLM unstructured response)"
        return Response()


# --- Build ----------------------------------------------------------------

# Real Gemini if the API key + lib are present, else FakeLLM.
def build_llm() -> Any:
    api_key = "redacted"
    if not api_key:
        print("[llm_client] No GOOGLE_API_KEY set. Using FakeLLM for local testing.")
        return FakeLLM()
    os.environ["GOOGLE_API_KEY"] = api_key
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        print("[llm_client] langchain_google_genai not installed. Using FakeLLM.")
        return FakeLLM()
    return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=TEMPERATURE)


llm_client = build_llm()
