"""
llm_client.py

Constructs the LLM client used by the sectioning pipeline. Kept in a
separate file so the LLM provider, model, and connection details are
visible and easy to swap.

To switch providers, change the function body to return a different
langchain-compatible LLM. The rest of the pipeline doesn't care which
backend you use as long as it supports .with_structured_output().
"""

from langchain_google_genai import ChatGoogleGenerativeAI


# =====================================================================
# Configuration
# =====================================================================
# Model choice notes (as of 2026):
#
#   "gemini-2.5-flash"      ~$0.005 per ~10-page doc, more reliable
#                            structured output. Recommended default.
#   "gemini-2.5-flash-lite" ~$0.001 per ~10-page doc, cheapest tier,
#                            occasionally returns slightly off match_text.
#                            Use for high-volume / dev work.
#   "gemini-2.5-pro"        more expensive, only worth it if flash is
#                            unreliable on a particular doc style.

GEMINI_MODEL = 'gemini-2.5-flash'
TEMPERATURE = 0   # deterministic structured output


# =====================================================================
# Client constructor
# =====================================================================

def build_llm():
    """Construct and return the LLM client used by run_sectioning().

    Reads GOOGLE_API_KEY from the environment automatically. Set it via:
        export GOOGLE_API_KEY=your-key
    or by populating os.environ before calling this function.
    """
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=TEMPERATURE,
    )


# =====================================================================
# Hot-swap notes (for future reference)
# =====================================================================
#
# To switch to Anthropic:
#     from langchain_anthropic import ChatAnthropic
#     return ChatAnthropic(model='claude-haiku-4-5', temperature=0)
#
# To switch to OpenAI:
#     from langchain_openai import ChatOpenAI
#     return ChatOpenAI(model='gpt-5-nano', temperature=0)
#
# Both support .with_structured_output() so the rest of the pipeline
# keeps working unchanged.
