```python
"""FastAPI stub routes for the writer/reviewer suggestion + feedback flow.

Returns well-formed Suggestion / ReviewerViolation objects populated with random
data so the frontend can render against a stable contract while the langgraph
side is built. Replace the random-fill blocks with real graph calls when ready.
"""

from __future__ import annotations

import random
import string
import uuid
from typing import Tuple

from fastapi import FastAPI

from models import (
    DraftSuggestionsRequest,
    FeedbackRequest,
    FeedbackResponse,
    ReviewerSuggestionsResponse,
    ReviewerViolation,
    SectionSuggestionsRequest,
    Suggestion,
    WriterSuggestionsResponse,
)


app = FastAPI(title="ACAI Writer/Reviewer Stub API")


# ---------------------------------------------------------------------------
# Tiny primitives used inside the route bodies
# ---------------------------------------------------------------------------

DEFAULT_BUTTONS = ["accept", "reject", "edit"]


def _rand(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _random_window(content: str) -> Tuple[int, int]:
    """Pick a short random [start, end] window inside content for highlight ranges."""
    if not content:
        return 0, 0
    n = len(content)
    window = random.randint(1, min(15, n))
    start = random.randint(0, n - window)
    return start, start + window


# ---------------------------------------------------------------------------
# Section-level routes
# ---------------------------------------------------------------------------

@app.post(
    "/working-draft/{working_draft_id}/section/{section_id}/writer/suggestions",
    response_model=WriterSuggestionsResponse,
)
async def writer_suggestions_for_section(
    working_draft_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: SectionSuggestionsRequest,
) -> WriterSuggestionsResponse:
    # Call Writer Agent w/ Section Content and Recent Changes
    # Format Suggestions If >0
    # Return them
    section = payload.section
    start, end = _random_window(section.content)
    tag = _rand()
    suggestion = Suggestion(
        source_agent="writer",
        suggestion_title=f"example_title_{tag}",
        suggestion_text=f"example_suggestion_text_{tag}",
        original_text=section.content,
        section_id=section.id,
        start_char=start,
        end_char=end,
        buttons=DEFAULT_BUTTONS,
    )
    return WriterSuggestionsResponse(suggestions=[suggestion])


@app.post(
    "/working-draft/{working_draft_id}/section/{section_id}/reviewer/suggestions",
    response_model=ReviewerSuggestionsResponse,
)
async def reviewer_suggestions_for_section(
    working_draft_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: SectionSuggestionsRequest,
) -> ReviewerSuggestionsResponse:
    # Call Reviewer Agent w/ Section Content and Recent Changes
    # Categorize Violations (spelling / style / compliance)
    # Attach Suggestion Fix To Each Violation
    # Return them
    section = payload.section
    start, end = _random_window(section.content)
    tag = _rand()
    fix = Suggestion(
        source_agent="reviewer",
        suggestion_title=f"example_title_{tag}",
        suggestion_text=f"example_suggestion_text_{tag}",
        original_text=section.content,
        section_id=section.id,
        start_char=start,
        end_char=end,
        buttons=DEFAULT_BUTTONS,
    )
    violation = ReviewerViolation(
        source_agent="reviewer",
        violation_description=f"example_violation_description_{_rand()}",
        suggestion_fix=fix,
    )
    return ReviewerSuggestionsResponse(violations=[violation])


# ---------------------------------------------------------------------------
# Draft-level routes (1-2 random items per call)
# Doc-level analysis skipped per spec; replace loop body with real graph call.
# ---------------------------------------------------------------------------

@app.post(
    "/working-draft/{working_draft_id}/writer/suggestions",
    response_model=WriterSuggestionsResponse,
)
async def writer_suggestions_for_draft(
    working_draft_id: uuid.UUID,
    payload: DraftSuggestionsRequest,
) -> WriterSuggestionsResponse:
    # Call Writer Agent w/ Full Draft (all sections + sources)
    # Aggregate Suggestions Across Sections
    # Return them
    sections = payload.working_draft.sections
    if not sections:
        return WriterSuggestionsResponse(suggestions=[])

    suggestions = []
    for _ in range(random.randint(1, 2)):
        section = random.choice(sections)
        start, end = _random_window(section.content)
        tag = _rand()
        suggestions.append(Suggestion(
            source_agent="writer",
            suggestion_title=f"example_title_{tag}",
            suggestion_text=f"example_suggestion_text_{tag}",
            original_text=section.content,
            section_id=section.id,
            start_char=start,
            end_char=end,
            buttons=DEFAULT_BUTTONS,
        ))
    return WriterSuggestionsResponse(suggestions=suggestions)


@app.post(
    "/working-draft/{working_draft_id}/reviewer/suggestions",
    response_model=ReviewerSuggestionsResponse,
)
async def reviewer_suggestions_for_draft(
    working_draft_id: uuid.UUID,
    payload: DraftSuggestionsRequest,
) -> ReviewerSuggestionsResponse:
    # Call Reviewer Agent w/ Full Draft (all sections + sources)
    # Aggregate Violations Across Sections
    # Return them
    sections = payload.working_draft.sections
    if not sections:
        return ReviewerSuggestionsResponse(violations=[])

    violations = []
    for _ in range(random.randint(1, 2)):
        section = random.choice(sections)
        start, end = _random_window(section.content)
        tag = _rand()
        fix = Suggestion(
            source_agent="reviewer",
            suggestion_title=f"example_title_{tag}",
            suggestion_text=f"example_suggestion_text_{tag}",
            original_text=section.content,
            section_id=section.id,
            start_char=start,
            end_char=end,
            buttons=DEFAULT_BUTTONS,
        )
        violations.append(ReviewerViolation(
            source_agent="reviewer",
            violation_description=f"example_violation_description_{_rand()}",
            suggestion_fix=fix,
        ))
    return ReviewerSuggestionsResponse(violations=violations)


# ---------------------------------------------------------------------------
# Feedback route
# Re-runs the matching agent and returns a replacement object.
# ---------------------------------------------------------------------------

@app.post(
    "/working-draft/{working_draft_id}/{suggestion_id}/feedback",
    response_model=FeedbackResponse,
)
async def submit_feedback(
    working_draft_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    payload: FeedbackRequest,
) -> FeedbackResponse:
    # Branch on the type of original_suggestion (Suggestion vs ReviewerViolation)
    # Re-Call The Matching Agent w/ Section Content + Original Suggestion + User Feedback
    # Format New Suggestion / Violation As The Replacement
    # Return It
    section = payload.section
    start, end = _random_window(section.content)
    tag = _rand()

    if isinstance(payload.original_suggestion, ReviewerViolation):
        fix = Suggestion(
            source_agent="reviewer",
            suggestion_title=f"example_title_{tag}",
            suggestion_text=f"example_suggestion_text_{tag}",
            original_text=section.content,
            section_id=section.id,
            start_char=start,
            end_char=end,
            buttons=DEFAULT_BUTTONS,
        )
        replacement: Suggestion | ReviewerViolation = ReviewerViolation(
            source_agent="reviewer",
            violation_description=f"example_violation_description_{_rand()}",
            suggestion_fix=fix,
        )
    else:
        replacement = Suggestion(
            source_agent="writer",
            suggestion_title=f"example_title_{tag}",
            suggestion_text=f"example_suggestion_text_{tag}",
            original_text=section.content,
            section_id=section.id,
            start_char=start,
            end_char=end,
            buttons=DEFAULT_BUTTONS,
        )

    return FeedbackResponse(replacement=replacement)
```
```python
"""Pydantic models for the ACAI writer/reviewer suggestion API."""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared / placeholder models (expand these later)
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    text: str = ""
    source_id: Optional[uuid.UUID] = None
    page: Optional[int] = None


class Source(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = ""
    url: Optional[str] = None


class Comment(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    author: str = ""
    text: str = ""


class IntakeFormMetadata(BaseModel):
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Draft + section
# ---------------------------------------------------------------------------

class Section(BaseModel):
    title: str
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    content: str
    required: bool = False
    is_meta_section: bool = False
    comments: List[Comment] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    order_index: int


class AcaiWorkingDraftv2(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    template_id: Optional[uuid.UUID] = None
    document_name: str
    version: str = "1"
    sources: List[Source] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)
    intake_form_metadata: Optional[IntakeFormMetadata] = None
    draft_author: uuid.UUID
    draft_creation_date: date
    draft_modified_date: date
    human_reviewed: bool = False


# ---------------------------------------------------------------------------
# Suggestions / violations
# ---------------------------------------------------------------------------

class SuggestionSource(str, Enum):
    WRITER = "writer"
    REVIEWER = "reviewer"


# Allowed values: "spelling" | "style" | "compliance"
ViolationCategory = str


class Suggestion(BaseModel):
    source_agent: str
    suggestion_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    suggestion_title: str
    suggestion_text: str
    original_text: Optional[str] = None
    section_id: uuid.UUID
    start_char: int
    end_char: int
    citation: Optional[List[Citation]] = None
    buttons: Optional[List[str]] = None


class ReviewerViolation(BaseModel):
    review_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_agent: str
    violation_category: Optional[ViolationCategory] = None  # "spelling" | "style" | "compliance"
    violation_citation: Optional[List[Citation]] = None
    violation_description: str
    suggestion_fix: Suggestion


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class Feedback(BaseModel):
    suggestion_id: uuid.UUID
    user_selected_button: str
    user_text: str
    suggestion_source: SuggestionSource  # writer | reviewer


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class SectionSuggestionsRequest(BaseModel):
    """Body for the section-level writer/reviewer routes."""
    working_draft: AcaiWorkingDraftv2
    section: Section


class DraftSuggestionsRequest(BaseModel):
    """Body for the draft-level writer/reviewer routes."""
    working_draft: AcaiWorkingDraftv2


class FeedbackRequest(BaseModel):
    """Body for the feedback route. Carries enough context for the graph to re-run."""
    working_draft: AcaiWorkingDraftv2
    section: Section
    original_suggestion: Union[Suggestion, ReviewerViolation]
    feedback: Feedback


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------

class WriterSuggestionsResponse(BaseModel):
    suggestions: List[Suggestion]


class ReviewerSuggestionsResponse(BaseModel):
    violations: List[ReviewerViolation]


class FeedbackResponse(BaseModel):
    """Replacement object emitted by the second graph run."""
    replacement: Union[Suggestion, ReviewerViolation]
```
```python
"""Mock request bodies for each of the 5 routes plus a QA runner.

Two ways to use this file:

1. REFERENCE: read the body dicts below, copy any one into Swagger UI at
   http://localhost:8000/docs and paste it into the request-body field.
   Path-param values to use are listed alongside each body.

2. QA: `python examples.py` will hit every route via TestClient and confirm
   each one returns 200 + a response that parses against its declared model.
   Run `python examples.py --examples` to just print the bodies, or
   `python examples.py --qa` to just run the test.
"""

from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from main import app
from models import (
    FeedbackResponse,
    ReviewerSuggestionsResponse,
    Suggestion,
    WriterSuggestionsResponse,
)


# ---------------------------------------------------------------------------
# Fixed IDs (reused across every example so they're predictable in Swagger)
# ---------------------------------------------------------------------------

DRAFT_ID = "11111111-1111-1111-1111-111111111111"
SECTION_INTRO_ID = "22222222-2222-2222-2222-222222222222"
SECTION_BODY_ID = "33333333-3333-3333-3333-333333333333"
SECTION_CONCLUSION_ID = "44444444-4444-4444-4444-444444444444"
AUTHOR_ID = "55555555-5555-5555-5555-555555555555"
ORIGINAL_SUGGESTION_ID = "66666666-6666-6666-6666-666666666666"


# ---------------------------------------------------------------------------
# Shared draft + sections
# ---------------------------------------------------------------------------

EXAMPLE_DRAFT = {
    "id": DRAFT_ID,
    "template_id": None,
    "document_name": "Q2 Compliance Memo",
    "version": "1",
    "sources": [],
    "sections": [
        {
            "title": "Executive Summary",
            "id": SECTION_INTRO_ID,
            "content": "This memo summarizes our compliance posture for the quarter ending June 30. Key findings indicate strong adherence to internal controls across all reviewed areas.",
            "required": True,
            "is_meta_section": False,
            "comments": [],
            "sources": [],
            "citations": [],
            "order_index": 0,
        },
        {
            "title": "Background",
            "id": SECTION_BODY_ID,
            "content": "The company recieved updated guidance from regulators in March. We have since updated our internal policies to align with the new requirements and trained staff accordingly.",
            "required": True,
            "is_meta_section": False,
            "comments": [],
            "sources": [],
            "citations": [],
            "order_index": 1,
        },
        {
            "title": "Recommendations",
            "id": SECTION_CONCLUSION_ID,
            "content": "We recommend continuing the current monitoring cadence and revisiting the framework in Q4 once the next round of regulatory updates is published.",
            "required": False,
            "is_meta_section": False,
            "comments": [],
            "sources": [],
            "citations": [],
            "order_index": 2,
        },
    ],
    "intake_form_metadata": None,
    "draft_author": AUTHOR_ID,
    "draft_creation_date": "2026-04-01",
    "draft_modified_date": "2026-04-29",
    "human_reviewed": False,
}

# Just the intro section, used as the `section` field for section-level routes
EXAMPLE_INTRO_SECTION = EXAMPLE_DRAFT["sections"][0]


# ---------------------------------------------------------------------------
# Request bodies (one per route)
# ---------------------------------------------------------------------------

# 1. POST /working-draft/{id}/section/{id}/writer/suggestions
WRITER_SECTION_BODY = {
    "working_draft": EXAMPLE_DRAFT,
    "section": EXAMPLE_INTRO_SECTION,
}

# 2. POST /working-draft/{id}/section/{id}/reviewer/suggestions
REVIEWER_SECTION_BODY = {
    "working_draft": EXAMPLE_DRAFT,
    "section": EXAMPLE_INTRO_SECTION,
}

# 3. POST /working-draft/{id}/writer/suggestions
WRITER_DRAFT_BODY = {"working_draft": EXAMPLE_DRAFT}

# 4. POST /working-draft/{id}/reviewer/suggestions
REVIEWER_DRAFT_BODY = {"working_draft": EXAMPLE_DRAFT}

# 5. POST /working-draft/{id}/{suggestion_id}/feedback
# original_suggestion mimics a Suggestion that a previous writer call returned.
EXAMPLE_ORIGINAL_SUGGESTION = {
    "source_agent": "writer",
    "suggestion_id": ORIGINAL_SUGGESTION_ID,
    "suggestion_title": "example_title_abc123",
    "suggestion_text": "Consider tightening the opening sentence to lead with the key finding.",
    "original_text": EXAMPLE_INTRO_SECTION["content"],
    "section_id": SECTION_INTRO_ID,
    "start_char": 5,
    "end_char": 18,
    "citation": None,
    "buttons": ["accept", "reject", "edit"],
}

FEEDBACK_BODY = {
    "working_draft": EXAMPLE_DRAFT,
    "section": EXAMPLE_INTRO_SECTION,
    "original_suggestion": EXAMPLE_ORIGINAL_SUGGESTION,
    "feedback": {
        "suggestion_id": ORIGINAL_SUGGESTION_ID,
        "user_selected_button": "edit",
        "user_text": "Make it more concise and use active voice.",
        "suggestion_source": "writer",
    },
}


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------

ROUTES = [
    {
        "name": "Section writer suggestions",
        "path": f"/working-draft/{DRAFT_ID}/section/{SECTION_INTRO_ID}/writer/suggestions",
        "path_params": {"working_draft_id": DRAFT_ID, "section_id": SECTION_INTRO_ID},
        "body": WRITER_SECTION_BODY,
        "response_model": WriterSuggestionsResponse,
    },
    {
        "name": "Section reviewer suggestions",
        "path": f"/working-draft/{DRAFT_ID}/section/{SECTION_INTRO_ID}/reviewer/suggestions",
        "path_params": {"working_draft_id": DRAFT_ID, "section_id": SECTION_INTRO_ID},
        "body": REVIEWER_SECTION_BODY,
        "response_model": ReviewerSuggestionsResponse,
    },
    {
        "name": "Draft writer suggestions",
        "path": f"/working-draft/{DRAFT_ID}/writer/suggestions",
        "path_params": {"working_draft_id": DRAFT_ID},
        "body": WRITER_DRAFT_BODY,
        "response_model": WriterSuggestionsResponse,
    },
    {
        "name": "Draft reviewer suggestions",
        "path": f"/working-draft/{DRAFT_ID}/reviewer/suggestions",
        "path_params": {"working_draft_id": DRAFT_ID},
        "body": REVIEWER_DRAFT_BODY,
        "response_model": ReviewerSuggestionsResponse,
    },
    {
        "name": "Submit feedback",
        "path": f"/working-draft/{DRAFT_ID}/{ORIGINAL_SUGGESTION_ID}/feedback",
        "path_params": {"working_draft_id": DRAFT_ID, "suggestion_id": ORIGINAL_SUGGESTION_ID},
        "body": FEEDBACK_BODY,
        "response_model": FeedbackResponse,
    },
]


# ---------------------------------------------------------------------------
# Printer (for copy-paste into Swagger UI)
# ---------------------------------------------------------------------------

def print_examples() -> None:
    print("Swagger UI is at http://localhost:8000/docs once `uvicorn main:app` is running.")
    for i, route in enumerate(ROUTES, 1):
        print()
        print("=" * 72)
        print(f"  {i}. {route['name']}")
        print("=" * 72)
        print(f"  POST {route['path']}")
        print()
        print("  PATH PARAMS:")
        for k, v in route["path_params"].items():
            print(f"    {k} = {v}")
        print()
        print("  BODY:")
        for line in json.dumps(route["body"], indent=2).splitlines():
            print(f"    {line}")


# ---------------------------------------------------------------------------
# QA runner
# ---------------------------------------------------------------------------

def run_qa() -> bool:
    client = TestClient(app)
    print()
    print("=" * 72)
    print("  QA RUN")
    print("=" * 72)

    all_passed = True
    for route in ROUTES:
        try:
            resp = client.post(route["path"], json=route["body"])
            assert resp.status_code == 200, f"status {resp.status_code}: {resp.text[:200]}"
            parsed = route["response_model"].model_validate(resp.json())

            # Pull a one-line summary of what came back
            if hasattr(parsed, "suggestions"):
                summary = f"{len(parsed.suggestions)} suggestion(s)"
            elif hasattr(parsed, "violations"):
                summary = f"{len(parsed.violations)} violation(s)"
            elif hasattr(parsed, "replacement"):
                summary = f"replacement is {type(parsed.replacement).__name__}"
            else:
                summary = "ok"

            print(f"  [PASS] {route['name']:<35} 200, {summary}")
        except Exception as e:
            all_passed = False
            print(f"  [FAIL] {route['name']:<35} {e}")

    print()
    print("  ALL ROUTES OK" if all_passed else "  SOME ROUTES FAILED")
    return all_passed


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--examples" in sys.argv:
        print_examples()
    elif "--qa" in sys.argv:
        ok = run_qa()
        sys.exit(0 if ok else 1)
    else:
        print_examples()
        ok = run_qa()
        sys.exit(0 if ok else 1)
```
