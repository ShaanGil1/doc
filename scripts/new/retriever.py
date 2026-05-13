# Search the corpus for top_k chunks matching a query.
"""
Stub. Real implementation will be pgsql vector + tsvector + RRF.
Signature is the only thing callers see, so the swap is local to this file.

The fake corpus is keyed by simple substring triggers on the query, so tests
can predict what comes back. Multiple chunks share triggers so a single query
returns several chunks (useful for testing the find_conflict positional
indexing).
"""

from typing import List

from models import RetrievedChunk


# Fake corpus. Each entry is (substring_trigger, RetrievedChunk).
# Triggers are deliberately repeated across entries so a single query
# returns multiple chunks. search() preserves the order below.
FAKE_CORPUS: List[tuple] = [
    # "30 days" -> two chunks (travel deadline + procurement deadline)
    (
        "30 days",
        RetrievedChunk(
            chunk_id="chunk_sop_travel",
            doc_id="doc_sop_travel",
            doc_title="Travel SOP v2",
            text="All travel expense forms must be submitted within 45 days of the trip end date.",
        ),
    ),
    (
        "30 days",
        RetrievedChunk(
            chunk_id="chunk_sop_procurement",
            doc_id="doc_sop_procurement",
            doc_title="Procurement SOP",
            text="Procurement requests must be filed within 14 days of identifying the need.",
        ),
    ),

    # "supervisor approval" -> two chunks (general policy + travel-specific)
    (
        "supervisor approval",
        RetrievedChunk(
            chunk_id="chunk_sop_travel_b",
            doc_id="doc_sop_travel",
            doc_title="Travel SOP v2",
            text="Travel under $500 does not require prior supervisor approval.",
        ),
    ),
    (
        "supervisor approval",
        RetrievedChunk(
            chunk_id="chunk_general_auth",
            doc_id="doc_general_auth",
            doc_title="General Authority Policy",
            text="All discretionary spending requires prior supervisor sign-off documented in writing.",
        ),
    ),

    # "25000" -> two chunks (FAR + agency directive)
    (
        "25000",
        RetrievedChunk(
            chunk_id="chunk_far_13_104",
            doc_id="doc_far",
            doc_title="FAR 13.104",
            text="Contracts above $10,000 shall be awarded on the basis of competition to the maximum extent practicable.",
        ),
    ),
    (
        "25000",
        RetrievedChunk(
            chunk_id="chunk_agency_directive",
            doc_id="doc_agency_directive",
            doc_title="Agency Directive 5400",
            text="No-bid contracts above $5,000 require written justification from the contracting officer.",
        ),
    ),

    # "annually" -> single chunk (kept simple)
    (
        "annually",
        RetrievedChunk(
            chunk_id="chunk_policy_review",
            doc_id="doc_policy_meta",
            doc_title="Policy Review Schedule",
            text="All policy documents shall be reviewed and updated on a biennial basis, not annually.",
        ),
    ),

    # "international travel" -> single chunk
    (
        "international travel",
        RetrievedChunk(
            chunk_id="chunk_intl_travel",
            doc_id="doc_sop_travel",
            doc_title="Travel SOP v2",
            text="International travel must be approved by both the supervisor and the program director.",
        ),
    ),
]


# Return top chunks for a query, filtered to selected_doc_ids.
def search(query: str, selected_doc_ids: List[str], top_k: int = 5) -> List[RetrievedChunk]:
    query_lower = query.lower()
    matched: List[RetrievedChunk] = []
    for trigger, chunk in FAKE_CORPUS:
        if trigger.lower() in query_lower and chunk.doc_id in selected_doc_ids:
            matched.append(chunk)
    return matched[:top_k]