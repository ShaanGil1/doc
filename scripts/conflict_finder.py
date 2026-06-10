# Per-section conflict finding.
"""
Contains the find_conflicts_for_section node plus its domain helper:
  - find_conflict:                  one LLM call. Given all of a section's claims +
                                    the section text + the deduped source pool,
                                    return zero or more ReviewerViolations.
  - find_conflicts_for_section:     the LangGraph node. One branch per section,
                                    run in parallel via Send. Extracts the
                                    section's claims, searches per claim, dedups
                                    the sources, then runs one conflict call.

The whole section job is wrapped in a single retry: if it raises, wait one
second and run it once more. If it fails again, return no flags so one bad
section does not sink the rest of the draft.

Claims and sources are handed to the LLM as numbered lists (1, 2, 3...). The LLM
cites a finding by claim_index and source_index; we remap each index back to the
real objects in code (claims[i-1] for the span, chunks[i-1] for the source, which
still carries its real chunk_id/doc_id). Numbers are easier for the model to emit
than echoing UUIDs back.
"""

import time
from typing import Dict, List

from pydantic import BaseModel, Field

from helpers.retriever import search
from llm_client import llm_client
from models import ExtractedClaim, RetrievedChunk, ReviewerViolation
from nodes.claim_extractor import extract_claims_for_section, spans_overlap
from prompts import FIND_CONFLICT_PROMPT
from state import FindConflictState


# Seconds to wait before the single retry. Module-level so tests can zero it.
RETRY_WAIT_SECONDS = 1.0


# LLM-facing schema. Internal to this module.
class ConflictFinding(BaseModel):
    claim_index: int = Field(description="1-based index of the claim this conflict is about (matches the numbered CLAIMS list)")
    source_index: int = Field(description="1-based index of the source that triggered the conflict (matches the numbered SOURCES list)")
    reason: str = Field(description="one or two sentences explaining the conflict in plain english")
    source_excerpt: str = Field(description="verbatim sentence from the source that supports the conflict")


class ConflictFindings(BaseModel):
    conflicts: List[ConflictFinding] = Field(default_factory=list)


# Find conflicts across all of a section's claims against the deduped source pool.
def find_conflict(
    claims: List[ExtractedClaim],
    context: str,
    chunks: List[RetrievedChunk],
) -> List[ReviewerViolation]:
    # Number both lists from 1 so the model sees 1., 2., 3.
    formatted_sources = "\n".join(
        f"{index}. [source: {chunk.doc_title}] {chunk.text}"
        for index, chunk in enumerate(chunks, start=1)
    )
    formatted_claims = "\n".join(
        f"{index}. {claim.claim_text}"
        for index, claim in enumerate(claims, start=1)
    )

    structured = llm_client.with_structured_output(ConflictFindings)
    response = structured.invoke(FIND_CONFLICT_PROMPT.format(
        formatted_sources=formatted_sources,
        formatted_claims=formatted_claims,
        context=context,
    ))

    violations: List[ReviewerViolation] = []
    for finding in response.conflicts:
        # Remap both indices to the real objects. Drop anything out of range.
        if not 1 <= finding.claim_index <= len(claims):
            continue
        if not 1 <= finding.source_index <= len(chunks):
            continue
        claim = claims[finding.claim_index - 1]
        source_chunk = chunks[finding.source_index - 1]
        # source_chunk.chunk_id, source_chunk.doc_id, source_chunk.doc_title all
        # available here for citation/source build-out.
        violations.append(ReviewerViolation(
            source_agent="find_conflict",
            violation_description=f"{finding.reason} Source: \"{finding.source_excerpt}\"",
            offending_text=claim.original_text,
            start_char=claim.start_char,
            end_char=claim.end_char,
            section_id=claim.section_id,
        ))
    return violations


# Do the whole section job: extract -> dedup claims -> search per claim ->
# consolidate sources -> one conflict call. Returns flags for the section.
def _process_section(section, selected_doc_ids: List[str]) -> List[ReviewerViolation]:
    # Extract the section's claims and drop span overlaps within the section.
    claims = extract_claims_for_section(section)
    deduped_claims: List[ExtractedClaim] = []
    for claim in claims:
        if any(spans_overlap(accepted, claim) for accepted in deduped_claims):
            continue
        deduped_claims.append(claim)
    if not deduped_claims:
        return []

    # Serial DB lookup per claim, then consolidate the source pool by chunk_id
    # (first-seen order, so source numbering is stable).
    deduped_chunks: Dict[str, RetrievedChunk] = {}
    for claim in deduped_claims:
        for chunk in search(claim.claim_text, selected_doc_ids):
            deduped_chunks.setdefault(chunk.chunk_id, chunk)
    chunks = list(deduped_chunks.values())
    if not chunks:
        return []

    # One conflict call over all claims, with the whole section as context.
    return find_conflict(deduped_claims, section.content, chunks)


# Node: per-section work. Runs in parallel via Send. Retries once on failure.
def find_conflicts_for_section(state: FindConflictState) -> dict:
    section_id = state["current_section_id"]
    section = state["sections_by_id"][section_id]
    selected_doc_ids = state["selected_doc_ids"]

    try:
        return {"flags": _process_section(section, selected_doc_ids)}
    except Exception as error:
        print(f"find_conflicts_for_section failed for section {section_id}, retrying in {RETRY_WAIT_SECONDS}s: {error}")
        time.sleep(RETRY_WAIT_SECONDS)
        try:
            return {"flags": _process_section(section, selected_doc_ids)}
        except Exception as retry_error:
            print(f"find_conflicts_for_section retry failed for section {section_id}: {retry_error}")
            return {"flags": []}
