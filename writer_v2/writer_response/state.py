# LangGraph state for the reviewer-route subgraph
from typing import List, Optional
from typing_extensions import TypedDict

from shared.models import ReviewerViolation, Suggestion


# State shape passed through the reviewer subgraph (current_violation set per fixer call).
class ReviewerRouteState(TypedDict):
    section_title: str
    section_content: str
    section_id: str

    violations: List[ReviewerViolation]
    current_violation: Optional[ReviewerViolation]

    response_suggestions: List[Suggestion]
    final_response_suggestions: List[Suggestion]
