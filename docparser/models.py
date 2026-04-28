from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field



# Pipeline configuration (used by both prompts and runtime)
MAX_DOCUMENT_WORDS = 5000   # hard cap; raises ValueError if exceeded
MIN_SECTION_WORDS = 60      # under this gets merged into a neighbor
MAX_SECTION_WORDS = 400     # over this gets split at sentence boundaries
MAX_RETRIES = 3             # retries when zero AI sections match

# Working-draft models 

# TEMP
class TemplateType(str, Enum):
    DLAI = "DLAI"
    DLAM = "DLAM"
    SOP = "SOP"


class IntakeFormMetadata(BaseModel):
    """Captures the raw responses from the 'Create New Policy' intake form."""
    template_type: TemplateType
    issuance_type: Optional[str] = None
    issuance_proposed_name: Optional[str] = None
    issuance_purpose: Optional[str] = None
    office_of_primary_responsibility: Optional[str] = None  # OPR
    subject_matter_experts: List[str] = Field(default_factory=list)
    jd_codes_msc_stakeholders: Optional[str] = None
    nfr_caps_related: List[str] = Field(default_factory=list)
    applicable_standards: Optional[str] = None  # FMR, FASAB, DLA/DoD policy, etc.
    template_specific: Optional[Dict[str, Any]] = Field(default_factory=dict)


class Source(BaseModel):
    """Minimal source stub. Replace with your real definition."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: Optional[str] = None
    url: Optional[str] = None


class Comment(BaseModel):
    # Placeholder
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str


class Citation(BaseModel):
    # Placeholder
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str


class Section(BaseModel):
    title: str
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str  
    required: bool = False
    is_meta_section: bool = False
    # settings: Optional[SectionSettings] = None
    comments: List["Comment"] = Field(default_factory=list)
    sources: List["Source"] = Field(default_factory=list)
    citations: List["Citation"] = Field(default_factory=list)
    order_index: int
    # laws: List["Regulation"] = Field(default_factory=list)
    # regulations: List["Regulation"] = Field(default_factory=list)
    # title_formatting_rules: Optional["TitleFormattingRules"] = None
    # content_formatting_rules: Optional["ContentFormattingRules"] = None


class AcaiWorkingDraftv2(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    template_id: Optional[uuid.UUID] = None  # template id reference
    document_name: str
    # document information (populated later, kept here for reference)
    # document_description: Optional[str] = None
    # document_type: Optional[str] = None
    # document_summary: Optional[str] = None
    # file_name: Optional[str] = None
    # document_created: Optional[datetime] = None
    # document_synonyms: List[str] = Field(default_factory=list)
    # fiscal_year: Optional[int] = None
    # entities: List[str] = Field(default_factory=list)
    version: str = "1"
    sources: List["Source"] = Field(default_factory=list)
    sections: List["Section"] = Field(default_factory=list)
    intake_form_metadata: Optional[IntakeFormMetadata] = None
    draft_author: uuid.UUID
    draft_creation_date: date
    draft_modified_date: date
    human_reviewed: bool = False

# LLM-facing models 
class SectionItem_LLM(BaseModel):
    # One section boundary. Downstream code uses section_match_text to locate 
    title: str = Field(
        min_length=1,
        max_length=100,
        description="""Short descriptive name for this section, 3-7 words ideal.
        Used for display and navigation. Prefer the original heading text when
        available, lightly cleaned up.""",
    )

    section_match_text: str = Field(
        min_length=8,
        description="""EXACT text of a line from the document where this
        section starts. Used only for locating the section.""",
    )


class Sections_LLM(BaseModel):
    sections: List[SectionItem_LLM] = Field(
        min_length=1,
        max_length=50,
        description="Section boundaries in document order.",
    )

# Internal data shape (between LLM call)
@dataclass
class MatchedSection:
    title: str
    start_line: int
    match_text: str
    matched: bool = True
