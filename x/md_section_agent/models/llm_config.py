"""How the section agent behaves. Which model and its credentials come from the environment at the top of llm.py."""

import os

# tried in order when LLM_MODEL is unavailable (503, 429, 404). Deployment
# names on azure, model names on gcp. Empty means LLM_MODEL only
FALLBACK_MODELS = tuple(m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip())
TEMPERATURE = 0.0

ATTEMPTS = 3  # per model, for transient errors (503, 429, timeouts)
BACKOFF_SECONDS = 2.0  # wait before the second attempt; doubles each time

RETRIES = 1  # extra calls for blocks that failed validation
SEARCH_WINDOW = 5  # lines either side of a reported number to look for the quote
FALLBACK_TO_REGEX = True  # no model reachable at all -> regex provider, with a finding
RECONCILE_WITH_RULES = True  # model and rules disagree on a line -> one call to pick
BACKFILL_FROM_RULES = True  # blanks and stubborn failures -> the rules, with a finding
VERBOSE = False  # True shows the ADK / genai / litellm client logs
