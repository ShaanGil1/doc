# main caller point for the find_conflict route
from typing import List
from graph import build_find_conflict_graph
from models import FindConflictInput, ReviewerViolation

find_conflict_graph = build_find_conflict_graph()

# Find_conflict route entry point, draft in, conflict flags out
def find_conflict_flags_for_draft(payload: FindConflictInput) -> List[ReviewerViolation]:
    sections_ordered = sorted(payload.sections, key=lambda section: section.order)
    initial_state = {
        "sections": payload.sections,
        "selected_doc_ids": payload.selected_doc_ids,
        "sections_by_id": {str(section.id): section for section in payload.sections},
        "sections_ordered": sections_ordered,
        "claims": [],
        "flags": [],
        "current_claim": None,
    }
    result = find_conflict_graph.invoke(initial_state)
    return result.get("flags") or []
