# Extract claims from a section and resolve their char offsets
from typing import List
from pydantic import BaseModel, Field
from llm_client import llm_client
from models import ExtractedClaim, Section
from prompts import CLAIM_EXTRACTOR_PROMPT, CLAIM_EXTRACTOR_RETRY_PROMPT
from state import FindConflictState

# LLM-facing schema
class ExtractedClaimLLM(BaseModel):
    claim_text: str = Field(description="rewritten claim, optimized for retrieval")
    original_text: str = Field(description="exact verbatim substring of the section")

class ExtractedClaimsLLM(BaseModel):
    claims: List[ExtractedClaimLLM] = Field(default_factory=list)

# Build an ExtractedClaim if its original_text is found verbatim
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

# Pull up to 5 claims from a section, resolve offsets, drop unresolved
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
    # fuzzy fallback Uncomment if verbatim + retry isn't enough
    # from rapidfuzz import fuzz, process
    # match = process.extractOne(claim.original_text, sliding_windows(section.content), scorer=fuzz.ratio)
    # if match and match[1] > 85:
    #     resolved.append(...)
    return resolved

# True if two char ranges intersect
def spans_intersect(first: ExtractedClaim, second: ExtractedClaim) -> bool:
    return first.start_char < second.end_char and second.start_char < first.end_char

# Node: extract claims from every section, drop overlapping spans within each section
def extract_claims(state: FindConflictState) -> dict:
    all_claims: List[ExtractedClaim] = []
    for section in state["sections"]:
        kept: List[ExtractedClaim] = []
        for claim in extract_claims_for_section(section):
            if any(spans_intersect(accepted, claim) for accepted in kept):
                continue
            kept.append(claim)
        all_claims.extend(kept)
    return {"claims": all_claims}