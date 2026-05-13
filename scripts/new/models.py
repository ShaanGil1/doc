# Pydantic models for the find_conflict route.
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


# A retrieved corpus document the user picked as a reference.
class Source(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str


# A citation attached to a section, pointing back at a chunk of a source.
class Citation(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str
    source_id: uuid.UUID
    page: Optional[int] = None


# A section of the working draft. Find_conflict reads title and content.
class Section(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    order: int
    title: str
    content: str
    sources: List[Source] = Field(default_factory=list)
    citation: List[Citation] = Field(default_factory=list)


# A writer or reviewer produced suggestion.
class Suggestion(BaseModel):
    source_agent: str
    sub_agent: Optional[str] = None
    suggestion_title: str
    suggestion_text: str
    original_text: Optional[str] = None
    section_id: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    buttons: str = ""


# A reviewer or cross-checker produced violation/flag. Returned to the frontend.
class ReviewerViolation(BaseModel):
    source_agent: str = "reviewer"
    rule_id: Optional[str] = None
    target_response_agent: Optional[str] = None
    violation_description: str
    offending_text: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    suggestion_fix: Optional[Suggestion] = None
    section_id: Optional[str] = None


# Input payload for the find_conflict route.
class FindConflictInput(BaseModel):
    sections: List[Section]
    selected_doc_ids: List[str]


# A claim extracted from a section. claim_text drives retrieval, original_text drives highlighting.
class ExtractedClaim(BaseModel):
    section_id: str
    claim_text: str
    original_text: str
    start_char: int
    end_char: int


# A retrieved chunk from the corpus.
class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    text: str
