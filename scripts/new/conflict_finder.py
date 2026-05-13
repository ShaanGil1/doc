# Find conflicts between a claim and retrieved source chunks
from typing import List
from pydantic import BaseModel, Field
from helpers.context_builder import build_context
from helpers.retriever import search
from llm_client import llm_client
from models import ExtractedClaim, RetrievedChunk, ReviewerViolation
from prompts import FIND_CONFLICT_PROMPT
from state import FindConflictState

# LLM-facing schema
class ConflictFinding(BaseModel):
    reason: str = Field(description="one or two sentences explaining the conflict in plain english")
    source_chunk_index: int = Field(description="1-based index of the chunk that triggered the conflict (matches the [N] prefix in the prompt)")
    source_excerpt: str = Field(description="verbatim sentence from the chunk that supports the conflict")

class ConflictFindings(BaseModel):
    conflicts: List[ConflictFinding] = Field(default_factory=list)

# Find conflicts between one claim and its retrieved sources
def find_conflict(
    claim: ExtractedClaim,
    context: str,
    chunks: List[RetrievedChunk],
) -> List[ReviewerViolation]:
    # index -> chunk. Enumerate from 1 so the LLM sees [1], [2], [3] (less room for error if you give chunk_ids)
    formatted_chunks = "\n---\n".join(
        f"[{index}]\n[source: {chunk.doc_title}]\n{chunk.text}"
        for index, chunk in enumerate(chunks, start=1)
    )
    print(formatted_chunks)

    structured = llm_client.with_structured_output(ConflictFindings)
    response = structured.invoke(FIND_CONFLICT_PROMPT.format(
        claim_text=claim.claim_text,
        context=context,
        formatted_chunks=formatted_chunks,
    ))

    violations: List[ReviewerViolation] = []
    for finding in response.conflicts:
        # Reverse map: index -> chunk_id Drop out-of-range indices.
        if not 1 <= finding.source_chunk_index <= len(chunks):
            continue
        source_chunk = chunks[finding.source_chunk_index - 1]
        # source_chunk.doc_id, source_chunk.chunk_id, source_chunk.doc_title all available here
        violations.append(ReviewerViolation(
            source_agent="find_conflict",
            violation_description=f"{finding.reason} Source: \"{finding.source_excerpt}\"",
            offending_text=claim.original_text,
            start_char=claim.start_char,
            end_char=claim.end_char,
            section_id=claim.section_id,
        ))
    return violations

# Node: Returns flags for one claim.
def find_conflicts_for_claim(state: FindConflictState) -> dict:
    claim = state["current_claim"]
    try:
        chunks = search(claim.claim_text, state["selected_doc_ids"])
        if not chunks:
            return {"flags": []}
        context = build_context(claim, state["sections_by_id"], state["sections_ordered"])
        violations = find_conflict(claim, context, chunks)
        return {"flags": violations}
    except Exception as error:
        print(f"find_conflicts_for_claim failed for claim in section {claim.section_id}: {error}")
        return {"flags": []}
