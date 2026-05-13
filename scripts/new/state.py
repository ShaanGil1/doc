import operator
from typing import Annotated, Dict, List, Optional, TypedDict
from models import ExtractedClaim, ReviewerViolation, Section

class FindConflictState(TypedDict):
    sections: List[Section]
    selected_doc_ids: List[str]
    sections_by_id: Dict[str, Section]
    sections_ordered: List[Section]
    claims: List[ExtractedClaim]
    flags: Annotated[List[ReviewerViolation], operator.add]
    current_claim: Optional[ExtractedClaim]
