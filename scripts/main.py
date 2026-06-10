# Entry point for the find_conflict route.
"""
Pure-function entry point. Section list + selected doc ids in, flags out.

max_concurrency caps how many section branches run at once, so a large draft
does not fire every section's LLM calls simultaneously. Hardcoded; retune to
your provider headroom.
"""

from typing import List

from graph import build_find_conflict_graph
from models import FindConflictInput, ReviewerViolation


find_conflict_graph = build_find_conflict_graph()


# Max sections checked concurrently. Caps the Send fan-out burst.
MAX_CONCURRENCY = 5


# Find_conflict route entry point: draft in, conflict flags out.
def find_conflict_flags_for_draft(payload: FindConflictInput) -> List[ReviewerViolation]:
    sections_ordered = sorted(payload.sections, key=lambda section: section.order)
    initial_state = {
        "sections": payload.sections,
        "selected_doc_ids": payload.selected_doc_ids,
        "sections_by_id": {str(section.id): section for section in payload.sections},
        "sections_ordered": sections_ordered,
        "flags": [],
        "current_section_id": None,
    }
    result = find_conflict_graph.invoke(
        initial_state,
        config={"max_concurrency": MAX_CONCURRENCY},
    )
    return result.get("flags") or []
