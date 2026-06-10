# Sample draft data for trying the find_conflict route end to end.
"""
SAMPLE_SECTIONS is a List[Section] you can drop into FindConflictInput.

Because sections now run in parallel, the FakeLLM responses are registered keyed
by a substring of each section (via register_fake_responses_by_key) rather than
as an ordered queue. register_sample_fakes() wires them up; run_sample.py calls it.

The conflict findings' source_index values assume the deduped source order each
section produces (search each claim in order, dedup by chunk_id, first seen wins).
"""

import uuid
from typing import Dict, List

from llm_client import register_fake_responses_by_key
from models import Section
from nodes.claim_extractor import ExtractedClaimLLM, ExtractedClaimsLLM
from nodes.conflict_finder import ConflictFinding, ConflictFindings


# Fixed UUIDs so test output is stable across runs.
SECTION_TRAVEL_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SECTION_AWARD_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SECTION_REVIEW_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
SECTION_INTRO_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


# Sample draft. Four sections, ordered.
SAMPLE_SECTIONS: List[Section] = [
    Section(
        id=SECTION_INTRO_ID,
        order=0,
        title="Introduction",
        content=(
            "This document outlines the standard operating procedures for the office. "
            "It describes how employees should handle administrative tasks, including travel, "
            "procurement, and document review. The procedures apply to all full-time staff."
        ),
    ),
    Section(
        id=SECTION_TRAVEL_ID,
        order=1,
        title="Travel Expense Submission",
        content=(
            "Employees must submit travel expense reports within 30 days of trip completion. "
            "Reports submitted after this window may be denied. "
            "Travel under $500 requires supervisor approval before booking. "
            "International travel always requires director-level approval regardless of cost. "
            "Receipts must be attached for any single expense over $25."
        ),
    ),
    Section(
        id=SECTION_AWARD_ID,
        order=2,
        title="Contract Award Procedures",
        content=(
            "Contracts under $25000 may be awarded without competitive bidding at the contracting "
            "officer's discretion. Larger contracts require a formal solicitation process. "
            "All awards must be documented in the contract file within 10 business days of decision."
        ),
    ),
    Section(
        id=SECTION_REVIEW_ID,
        order=3,
        title="Policy Review Schedule",
        content=(
            "All SOP documents shall be reviewed annually to ensure continued relevance. "
            "The review committee meets each January to assign documents to reviewers."
        ),
    ),
]


# Selected reference doc IDs the user picked. Must match doc_ids in the fake corpus.
SAMPLE_SELECTED_DOC_IDS: List[str] = [
    "doc_sop_travel",
    "doc_far",
    "doc_policy_meta",
]


# Each key is a substring unique to one section (appears in both that section's
# extractor prompt and its conflict prompt, since the section text is the context).
INTRO_KEY = "standard operating procedures"
TRAVEL_KEY = "travel expense reports within 30 days"
AWARD_KEY = "Contracts under $25000"
REVIEW_KEY = "reviewed annually"


# Fake extractor responses, keyed by section.
SAMPLE_EXTRACTOR_BY_KEY: Dict[str, ExtractedClaimsLLM] = {
    INTRO_KEY: ExtractedClaimsLLM(claims=[]),
    TRAVEL_KEY: ExtractedClaimsLLM(claims=[
        ExtractedClaimLLM(
            claim_text="Travel expense reports must be submitted within 30 days of trip completion.",
            original_text="Employees must submit travel expense reports within 30 days of trip completion.",
        ),
        ExtractedClaimLLM(
            claim_text="Travel under 500 dollars requires supervisor approval before booking.",
            original_text="Travel under $500 requires supervisor approval before booking.",
        ),
        ExtractedClaimLLM(
            claim_text="International travel requires director-level approval regardless of cost.",
            original_text="International travel always requires director-level approval regardless of cost.",
        ),
    ]),
    AWARD_KEY: ExtractedClaimsLLM(claims=[
        ExtractedClaimLLM(
            claim_text="Contracts under $25000 may be awarded without competitive bidding at the contracting officer's discretion.",
            original_text="Contracts under $25000 may be awarded without competitive bidding at the contracting officer's discretion.",
        ),
    ]),
    REVIEW_KEY: ExtractedClaimsLLM(claims=[
        ExtractedClaimLLM(
            claim_text="SOP documents shall be reviewed annually.",
            original_text="All SOP documents shall be reviewed annually to ensure continued relevance.",
        ),
    ]),
}


# Fake conflict responses, keyed by section. One ConflictFindings per section.
# Travel: claim 1 (30 days) vs source 1 (45 days); claim 2 (approval) vs source 2 (no approval).
# Award:  claim 1 vs source 1 (competition above 10000). Review: claim 1 vs source 1 (biennial).
SAMPLE_CONFLICT_BY_KEY: Dict[str, ConflictFindings] = {
    TRAVEL_KEY: ConflictFindings(conflicts=[
        ConflictFinding(
            claim_index=1,
            source_index=1,
            reason="The claim states a 30 day deadline. The source states 45 days for the same submission.",
            source_excerpt="All travel expense forms must be submitted within 45 days of the trip end date.",
        ),
        ConflictFinding(
            claim_index=2,
            source_index=2,
            reason="The claim requires prior supervisor approval. The source says travel under 500 dollars does not require prior approval.",
            source_excerpt="Travel under $500 does not require prior supervisor approval.",
        ),
    ]),
    AWARD_KEY: ConflictFindings(conflicts=[
        ConflictFinding(
            claim_index=1,
            source_index=1,
            reason="The claim allows officer discretion for awards under 25000 dollars. The source requires competition above 10000 dollars regardless of discretion.",
            source_excerpt="Contracts above $10,000 shall be awarded on the basis of competition to the maximum extent practicable.",
        ),
    ]),
    REVIEW_KEY: ConflictFindings(conflicts=[
        ConflictFinding(
            claim_index=1,
            source_index=1,
            reason="The claim states annual review. The source mandates biennial review.",
            source_excerpt="All policy documents shall be reviewed and updated on a biennial basis, not annually.",
        ),
    ]),
}


# Register the sample fakes (keyed by section) on the FakeLLM.
def register_sample_fakes() -> None:
    register_fake_responses_by_key("ExtractedClaimsLLM", SAMPLE_EXTRACTOR_BY_KEY)
    register_fake_responses_by_key("ConflictFindings", SAMPLE_CONFLICT_BY_KEY)
