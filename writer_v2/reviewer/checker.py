# Reviewer blackbox stub (real reviewer plugs in here later).
"""
Reviewer blackbox stub.

Three contracts:
  reviewer_check                writer route filter (drop bad writer suggestions)
  reviewer_produce_violations   reviewer route source (find issues to fix)
  reviewer_revalidate_fixes     reviewer route verifier (drop fixes that didn't help)

rule_id strings match the real reviewer's output exactly (with spaces and
capitalization, e.g. "Passive Voice", "Clarity and Ease"). RULE_TO_FIXER
maps each rule_id to the snake_case fixer function name used as a routing key.

Stub only produces violations for rules with corresponding fixers in
ROUTABLE_RESPONSE_AGENTS: "Passive Voice", "Sentence Length", "Writing Style".
Other rules (Spelling, Grammar, Clarity and Ease, Flow, Questionable Language,
Commercial Product Endorsement) need LLM detection and surface only when the
real reviewer is wired in.
"""

import os
import random
import re
from typing import List

from shared.models import ReviewerViolation, Suggestion


REJECT_RATE = float(os.environ.get("REVIEWER_REJECT_RATE", "0.0"))
SENTENCE_LIMIT = 35

PASSIVE_VOICE_RES = (
    re.compile(r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b', re.IGNORECASE),
    re.compile(r'\b(?:is|are|was|were|be|been|being)\s+\w+en\b', re.IGNORECASE),
)
CONTRACTION_RE = re.compile(r"\b\w+'\w+\b")


# Maps reviewer rule_id (real reviewer's output strings) to the routing key
# (snake_case fixer function name registered in ROUTABLE_RESPONSE_AGENTS).
RULE_TO_FIXER = {
    "Passive Voice":                  "passive_voice_fixer",
    "Spelling":                       "spelling_fixer",
    "Grammar":                        "grammar_fixer",
    "Clarity and Ease":               "clarity_fixer",
    "Flow":                           "flow_fixer",
    "Writing Style":                  "writing_style_fixer",
    "Questionable Language":          "questionable_language_fixer",
    "Commercial Product Endorsement": "commercial_endorsement_fixer",
    "Sentence Length":                "sentence_length_fixer",
}


# --- Writer route filter ---------------------------------------------------

# Filter writer suggestions before the user sees them (stub approves all by default).
def reviewer_check(section_content: str, suggestions: List[Suggestion]) -> List[int]:
    """Indices of writer suggestions to reject. Stub approves all unless REJECT_RATE > 0."""
    if REJECT_RATE <= 0:
        return []
    return [i for i in range(len(suggestions)) if random.random() < REJECT_RATE]


# --- Reviewer route source -------------------------------------------------

# Find rule violations in the section and tag each with its routing key.
def reviewer_produce_violations(section_content: str) -> List[ReviewerViolation]:
    """Detect rule violations. Each violation tags target_response_agent for routing."""
    violations: List[ReviewerViolation] = []

    # Sentence Length: any sentence over SENTENCE_LIMIT words
    for sentence_match in re.finditer(r'[^.!?]+[.!?]', section_content):
        sentence = sentence_match.group(0).strip()
        if len(sentence.split()) > SENTENCE_LIMIT:
            leading_whitespace = len(sentence_match.group(0)) - len(sentence_match.group(0).lstrip())
            violations.append(ReviewerViolation(
                rule_id="Sentence Length",
                target_response_agent=RULE_TO_FIXER["Sentence Length"],
                violation_description=f"Sentence exceeds {SENTENCE_LIMIT} words ({len(sentence.split())}).",
                offending_text=sentence,
                start_char=sentence_match.start() + leading_whitespace,
                end_char=sentence_match.end(),
            ))

    # Passive Voice: 'be|is|are|...' + word ending in -ed/-en
    for pattern in PASSIVE_VOICE_RES:
        for match in pattern.finditer(section_content):
            violations.append(ReviewerViolation(
                rule_id="Passive Voice",
                target_response_agent=RULE_TO_FIXER["Passive Voice"],
                violation_description=f"Passive voice detected: '{match.group(0)}'.",
                offending_text=match.group(0),
                start_char=match.start(),
                end_char=match.end(),
            ))

    # Writing Style (contraction subcategory): formal style avoids contractions
    for match in CONTRACTION_RE.finditer(section_content):
        violations.append(ReviewerViolation(
            rule_id="Writing Style",
            target_response_agent=RULE_TO_FIXER["Writing Style"],
            violation_description=f"Contraction '{match.group(0)}'. Formal style avoids contractions.",
            offending_text=match.group(0),
            start_char=match.start(),
            end_char=match.end(),
        ))

    return violations


# --- Reviewer route verifier -----------------------------------------------

# Splice each fix into the content and rerun produce_violations to confirm the count drops.
def reviewer_revalidate_fixes(
    section_content: str,
    fixes: List[Suggestion],
    original_violations: List[ReviewerViolation],
) -> List[int]:
    """Splice each fix into the content at its recorded position and rerun
    produce_violations. If the count doesn't drop, the fix didn't help.

    Position-based splice (not str.replace) so short offending_text like a
    single 'r' doesn't accidentally match elsewhere.
    """
    baseline = len(original_violations)
    rejected = []
    for index, fix in enumerate(fixes):
        if fix.start_char == 0 and fix.end_char == 0:
            continue  # position unresolved, can't verify
        modified = section_content[:fix.start_char] + fix.suggestion_text + section_content[fix.end_char:]
        if len(reviewer_produce_violations(modified)) >= baseline:
            rejected.append(index)
    return rejected
