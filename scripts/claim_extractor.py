# Extract claims from a section and resolve their char offsets.
"""
Domain helpers for claim extraction, used by the per-section node:
  - extract_claims_for_section:     one LLM call per section, capped at 5 claims
  - resolve_claim:                  build an ExtractedClaim if original_text is found verbatim
  - spans_overlap:                  pure helper, dedups claims within a section

These run inside the per-section branch (see nodes/conflict_finder.py). There is
no longer a standalone extract node that walks every section up front.
"""

from typing import List

from pydantic import BaseModel, Field

from llm_client import llm_client
from models import ExtractedClaim, Section
from prompts import CLAIM_EXTRACTOR_PROMPT, CLAIM_EXTRACTOR_RETRY_PROMPT


# LLM-facing schema. Internal to this module.
class ExtractedClaimLLM(BaseModel):
    claim_text: str = Field(description="rewritten claim, optimized for retrieval")
    original_text: str = Field(description="exact verbatim substring of the section")


class ExtractedClaimsLLM(BaseModel):
    claims: List[ExtractedClaimLLM] = Field(default_factory=list)


# Build an ExtractedClaim from a raw LLM claim if its original_text is found verbatim.
def resolve_claim(claim_llm: ExtractedClaimLLM, section: Section):
    start = section.content.find(claim_llm.original_text)
    if start == -1:
        return None
    return ExtractedClaim(
        section_id=str(section.id),
        claim_text=claim_llm.claim_text,
        original_text=claim_llm.original_text,
        start_char=start,
        end_char=start + len(claim_llm.original_text),
    )


# Pull up to 5 claims from a section, resolve offsets, drop unresolved.
def extract_claims_for_section(section: Section) -> List[ExtractedClaim]:
    structured = llm_client.with_structured_output(ExtractedClaimsLLM)
    response = structured.invoke(CLAIM_EXTRACTOR_PROMPT.format(
        section_title=section.title,
        section_content=section.content,
    ))

    resolved: List[ExtractedClaim] = []
    needs_retry: List[ExtractedClaimLLM] = []
    for claim in response.claims[:5]:
        extracted = resolve_claim(claim, section)
        if extracted is None:
            needs_retry.append(claim)
            continue
        resolved.append(extracted)

    if not needs_retry:
        return resolved

    retry_response = structured.invoke(CLAIM_EXTRACTOR_RETRY_PROMPT.format(
        section_content=section.content,
        failed_claims="\n".join(claim.claim_text for claim in needs_retry),
    ))
    for claim in retry_response.claims:
        extracted = resolve_claim(claim, section)
        if extracted is None:
            continue
        resolved.append(extracted)

    # fuzzy fallback parked. Uncomment if verbatim + retry isn't enough.
    # from rapidfuzz import fuzz, process
    # match = process.extractOne(claim.original_text, sliding_windows(section.content), scorer=fuzz.ratio)
    # if match and match[1] > 85:
    #     resolved.append(...)

    return resolved


# Two claims overlap if their char ranges intersect within the same section.
def spans_overlap(existing_claim: ExtractedClaim, new_claim: ExtractedClaim) -> bool:
    if existing_claim.section_id != new_claim.section_id:
        return False
    return existing_claim.start_char < new_claim.end_char and new_claim.start_char < existing_claim.end_char
