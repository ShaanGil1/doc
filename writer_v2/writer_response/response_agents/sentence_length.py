# Splits over-long sentences (>35 words) at natural break points

from writer_response.response_base import call_response_agent_llm


AGENT_NAME = "sentence_length_fixer"
SENTENCE_LIMIT = 35

RULE = f"""Sentences should generally be {SENTENCE_LIMIT} words or fewer.

When splitting:
1. Break at natural points: between independent clauses, before transitions
   ('however', 'because', 'while', 'although'), or before relative clauses
2. Each resulting sentence must be grammatically complete and stand alone
3. Preserve original meaning exactly. No content lost or added.
4. Combined word count should be roughly the same as the original
5. If you need to add a transitional word for the second sentence to flow,
   pick the lightest one that works ('It', 'However', 'In addition')

Some sentences over {SENTENCE_LIMIT} words are appropriate:
1. Enumerations with parallel items ('the policy applies to A, B, C, and D')
2. Complex legal definitions where breaking would change scope
3. Single-thought sentences that genuinely can't be split without distortion

If you can't split cleanly without sacrificing meaning, return all empty strings."""

def sentence_length_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        RULE, violation, state["section_content"], state["section_id"], AGENT_NAME)
    return {"response_suggestions": suggestions}
