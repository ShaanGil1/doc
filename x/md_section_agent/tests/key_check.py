"""python md_section_agent/tests/key_check.py

Answers, in order: which provider and model the environment selected (the same
block at the top of llm.py your other agents use), whether its credentials are
present, and whether one tiny structured call through the real path comes back.
A pass here means main.py will use the model."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent")]
import llm  # noqa: E402
from models import llm_config as settings  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

provider = llm.csp or "azure (DB_CLOUD_PROVIDER not set)"
print("1. provider %s, model %r, fallbacks %s" % (provider, llm.MODEL_NAME, list(settings.FALLBACK_MODELS) or "none"))
missing = llm.missing_credentials()
if missing:
    sys.exit("2. credentials missing: %s" % missing)
print("2. credentials present for %s" % provider)


class Ping(BaseModel):
    word: str = Field(description="the single word OK")


try:
    reply = llm.structured("Reply with the single word OK in the field `word`.", "ping", Ping)
    print(
        "3. structured call OK: %r, answered by %s on attempt %d in %.1fs"
        % (reply.word, llm.last["model"], llm.last["attempts"], llm.last["seconds"])
    )
except llm.LlmUnavailable as error:
    sys.exit("3. CALL FAILED: %s" % str(error)[:600])
print("all good; main.py will use the model")
