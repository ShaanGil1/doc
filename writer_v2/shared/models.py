# Models shared across writer and reviewer
import uuid
from typing import Optional

from pydantic import BaseModel, Field

# What the frontend sends in (writer/reviewer routes both take this)
class Section_Input(BaseModel):
    title: str
    content: str
    id: uuid.UUID = Field(default_factory=uuid.uuid4)


# What gets returned to the frontend (one per surfaced fix/proposal)
class Suggestion(BaseModel):
    source_agent: str  # "writer" or "reviewer"
    sub_agent: Optional[str] = None
    suggestion_title: str
    suggestion_text: str
    original_text: Optional[str] = None
    section_id: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    buttons: str = ""


# Reviewer's output type (target_response_agent is the routing key the dispatcher uses)
class ReviewerViolation(BaseModel):
    source_agent: str = "reviewer"
    rule_id: Optional[str] = None
    target_response_agent: Optional[str] = None
    violation_description: str
    offending_text: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    suggestion_fix: Optional[Suggestion] = None


# Intermediate shape returned by writer/response LLM calls (positions resolved post-LLM)
class LLMSuggestion(BaseModel):
    suggestion_title: str = Field(
        description="Short label (4-8 words). Empty if no suggestion."
    )
    suggestion_text: str = Field(
        description="Proposed replacement. Empty if no suggestion."
    )
    original_text: str = Field(
        description="EXACT verbatim substring being replaced. Empty if nothing to suggest."
    )
