"""The one place a model is called. The provider block at the top is the one the other agents use.
llm.structured(instruction, prompt, PydanticModel) returns a validated instance, with retries and fallback models."""

import os
from dotenv import load_dotenv

load_dotenv()
csp = os.getenv("DB_CLOUD_PROVIDER", "").lower()
model = os.getenv("LLM_MODEL", "gemini-2.5-flash")

if csp == "gcp":
    from google.adk.agents.llm_agent import Agent
else:  # if csp == "azure":
    from google.adk.agents import LlmAgent as Agent
    from google.adk.models.lite_llm import LiteLlm

    model = LiteLlm(
        model=f"azure/{model}",
        api_key=os.environ.get("AZURE_OPEN_AI_API_KEY", ""),
        api_base=os.environ.get("AZURE_OPEN_AI_API_BASE", ""),
        api_version=os.environ.get("AZURE_OPEN_AI_API_VERSION", ""),
    )

import asyncio  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Callable, Optional, Type, TypeVar  # noqa: E402

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

try:
    import litellm  # noqa: E402
except ImportError:  # gcp installs need not have it
    litellm = None

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from models import llm_config as settings  # noqa: E402

Schema = TypeVar("Schema", bound=BaseModel)
Backend = Callable[[str, str, Type[BaseModel]], dict]

MODEL_NAME = os.getenv("LLM_MODEL", "gemini-2.5-flash")  # the name behind `model`
AZURE_ENV = ("AZURE_OPEN_AI_API_KEY", "AZURE_OPEN_AI_API_BASE", "AZURE_OPEN_AI_API_VERSION")


class LlmUnavailable(Exception):
    """No credentials, no network, no model answering, or nothing usable back"""


backend_override: Optional[Backend] = None
last: dict = {}  # {"model", "attempts", "seconds"} of the last success


def missing_credentials() -> str:
    """Empty when the configured provider has what it needs, else what is missing"""
    if csp == "gcp":
        return "" if os.environ.get("GOOGLE_API_KEY") else "gcp: set GOOGLE_API_KEY"
    missing = [name for name in AZURE_ENV if not os.environ.get(name)]
    return "azure: set %s" % ", ".join(missing) if missing else ""


def is_configured() -> bool:
    return backend_override is not None or not missing_credentials()


def configure(backend: Backend = None):
    """Swap in a fake backend for tests (None restores the real model)"""
    global backend_override
    backend_override = backend


def structured(instruction: str, prompt: str, schema: Type[Schema]) -> Schema:
    """Ask for an instance of `schema`. Raises LlmUnavailable."""
    if backend_override is not None:
        return schema.model_validate(backend_override(instruction, prompt, schema))
    missing = missing_credentials()
    if missing:
        raise LlmUnavailable("no credentials (%s)" % missing)
    return schema.model_validate(with_retries(instruction, prompt, schema))


# ---------------------------------------------------------------------------
# retries and fallback models
# ---------------------------------------------------------------------------
TRANSIENT = (
    "503",
    "UNAVAILABLE",
    "429",
    "RESOURCE_EXHAUSTED",
    "overloaded",
    "high demand",
    "timeout",
    "Timeout",
    "DEADLINE",
    "temporarily",
    "RateLimit",
    "ServiceUnavailable",
    "APIConnectionError",
    "InternalServerError",
)
NOT_OFFERED = ("404", "NOT_FOUND", "not found", "not supported", "DeploymentNotFound")


def with_retries(instruction, prompt, schema) -> dict:
    names = [MODEL_NAME] + [m for m in settings.FALLBACK_MODELS if m != MODEL_NAME]
    failures = []
    for name in names:
        wait = settings.BACKOFF_SECONDS
        for attempt in range(1, settings.ATTEMPTS + 1):
            started = time.time()
            try:
                result = transport_call(name, instruction, prompt, schema)
                last.clear()
                last.update(model=name, attempts=attempt, seconds=round(time.time() - started, 1))
                return result
            except LlmUnavailable as error:
                text = str(error)
                failures.append("%s: %s" % (name, text[:140]))
                if any(word in text for word in NOT_OFFERED):
                    break  # this model, not this attempt
                if not any(word in text for word in TRANSIENT):
                    raise  # bad key, bad request: stop now
                if attempt < settings.ATTEMPTS:
                    time.sleep(wait)
                    wait *= 2
    raise LlmUnavailable("every model failed: " + " | ".join(failures))


def transport_call(name, instruction, prompt, schema) -> dict:
    try:
        return adk_call(name, instruction, prompt, schema)
    except LlmUnavailable:
        raise
    except Exception as error:  # network, auth, quota: one exception type out
        raise LlmUnavailable("%s: %s" % (type(error).__name__, error)) from error


def quiet_client_logs():
    """ADK, the genai client and litellm log tracebacks and banners at WARNING
    and ERROR; the caller gets one LlmUnavailable instead. VERBOSE shows them"""
    if not settings.VERBOSE:
        for name in ("google.adk", "google_adk", "google_genai", "google.genai", "LiteLLM", "litellm", "httpx"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        if litellm is not None:
            litellm.suppress_debug_info = True


# ---------------------------------------------------------------------------
# Google ADK
# ---------------------------------------------------------------------------
def model_for(name: str = None):
    """The model object for a model name: the module-level `model` for the
    configured name, or the same kind of object for a fallback name"""
    if name is None or name == MODEL_NAME:
        return model
    if csp == "gcp":
        return name
    return LiteLlm(
        model=f"azure/{name}",
        api_key=os.environ.get("AZURE_OPEN_AI_API_KEY", ""),
        api_base=os.environ.get("AZURE_OPEN_AI_API_BASE", ""),
        api_version=os.environ.get("AZURE_OPEN_AI_API_VERSION", ""),
    )


def build_agent(instruction: str, schema: Type[BaseModel], name: str = None):
    """An Agent that answers in `schema`: no tools, pinned temperature, sees only the current message."""
    return Agent(
        name="md_to_docx_boundaries",
        model=model_for(name),
        description="Finds where each block of a DLA issuance starts.",
        instruction=instruction,
        output_schema=schema,
        output_key="result",
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=settings.TEMPERATURE),
    )


def adk_call(name, instruction, prompt, schema) -> dict:
    quiet_client_logs()
    agent = build_agent(instruction, schema, name)
    sessions = InMemorySessionService()
    runner = Runner(app_name="md_to_docx", agent=agent, session_service=sessions)
    user_id, session_id = "md_to_docx", uuid.uuid4().hex

    async def run() -> dict:
        created = sessions.create_session(app_name="md_to_docx", user_id=user_id, session_id=session_id)
        if inspect.isawaitable(created):
            await created
        message = types.Content(role="user", parts=[types.Part(text=prompt)])
        text = None
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(part.text or "" for part in event.content.parts)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        session = sessions.get_session(app_name="md_to_docx", user_id=user_id, session_id=session_id)
        if inspect.isawaitable(session):
            session = await session
        result = (session.state or {}).get("result") if session else None
        if isinstance(result, dict):
            return result
        raise LlmUnavailable("model returned no JSON: %r" % (text or "")[:200])

    return asyncio.run(run())
