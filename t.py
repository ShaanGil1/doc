# Sample draft data for trying the find_conflict route end to end.
"""
SAMPLE_SECTIONS is a List[Section] you can drop into FindConflictInput.
SAMPLE_EXTRACTOR_RESPONSES and SAMPLE_CONFLICT_RESPONSES are the FakeLLM
responses that match this sample, so the pipeline runs and produces flags.
"""

import uuid
from typing import List

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
    "doc_sop_procurement",
    "doc_general_auth",
    "doc_agency_directive",
]


# Fake extractor responses, one per section (matches SAMPLE_SECTIONS order).
SAMPLE_EXTRACTOR_RESPONSES: List[ExtractedClaimsLLM] = [
    ExtractedClaimsLLM(claims=[]),
    ExtractedClaimsLLM(claims=[
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
    ExtractedClaimsLLM(claims=[
        ExtractedClaimLLM(
            claim_text="Contracts under $25000 may be awarded without competitive bidding at the contracting officer's discretion.",
            original_text="Contracts under $25000 may be awarded without competitive bidding at the contracting officer's discretion.",
        ),
    ]),
    ExtractedClaimsLLM(claims=[
        ExtractedClaimLLM(
            claim_text="SOP documents shall be reviewed annually.",
            original_text="All SOP documents shall be reviewed annually to ensure continued relevance.",
        ),
    ]),
]


# Fake conflict responses, queued in the order claims will be processed.
SAMPLE_CONFLICT_RESPONSES: List[ConflictFindings] = [
    ConflictFindings(conflicts=[
        ConflictFinding(
            reason="The claim states a 30 day deadline. The source states 45 days for the same submission.",
            source_chunk_index=1,
            source_excerpt="All travel expense forms must be submitted within 45 days of the trip end date.",
        ),
    ]),
    ConflictFindings(conflicts=[
        ConflictFinding(
            reason="The claim requires prior supervisor approval. The source says travel under 500 dollars does not require prior approval.",
            source_chunk_index=1,
            source_excerpt="Travel under $500 does not require prior supervisor approval.",
        ),
    ]),
    ConflictFindings(conflicts=[
        ConflictFinding(
            reason="The claim allows officer discretion for awards under 25000 dollars. The source requires competition above 10000 dollars regardless of discretion.",
            source_chunk_index=1,
            source_excerpt="Contracts above $10,000 shall be awarded on the basis of competition to the maximum extent practicable.",
        ),
    ]),
    ConflictFindings(conflicts=[
        ConflictFinding(
            reason="The claim states annual review. The source mandates biennial review.",
            source_chunk_index=1,
            source_excerpt="All policy documents shall be reviewed and updated on a biennial basis, not annually.",
        ),
    ]),
]
