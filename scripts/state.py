# State for the find_conflict subgraph.
"""
flags has an `add` reducer because parallel Send branches each return their
own flag list, and we want them concatenated rather than overwritten.

current_section_id carries the per-section payload when Send fans out. Only the
per-section node reads it. Each section branch extracts its own claims, so there
is no longer a shared `claims` list in state.
"""

import operator
from typing import Annotated, Dict, List, Optional, TypedDict

from models import ReviewerViolation, Section


class FindConflictState(TypedDict):
    sections: List[Section]
    selected_doc_ids: List[str]
    sections_by_id: Dict[str, Section]
    sections_ordered: List[Section]
    flags: Annotated[List[ReviewerViolation], operator.add]
    current_section_id: Optional[str]
