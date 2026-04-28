import base64
import os
import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from docx_to_workingdraft.llm import build_llm
from docx_to_workingdraft.models import (
    AcaiWorkingDraftv2,
    IntakeFormMetadata,
    Section,
    TemplateType,
)
from docx_to_workingdraft.util import run_sectioning


router = APIRouter(prefix="/working-draft", tags=["working-draft"])

# TODO: replace with real auth once implemented. When auth is wired up,
# this should pull the authenticated user's id from the request context
# =====================================================================
# Auth placeholder
# =====================================================================
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
def get_current_user_id() -> uuid.UUID:
    """Stub for current-user resolution. Replace body with real auth lookup."""
    return TEST_USER_ID


# =====================================================================
# LLM client
# =====================================================================

GOOGLE_API_KEY_FOR_LOCAL = ""  # paste your key here for local testing

if not os.environ.get('GOOGLE_API_KEY') and GOOGLE_API_KEY_FOR_LOCAL:
    os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY_FOR_LOCAL

if os.environ.get('GOOGLE_API_KEY'):
    llm = build_llm()
else:
    llm = None  # /docx route will return a clear error until key is set


class CreateWorkingDraftIntakeRequest(BaseModel):
    intake_form_metadata: Optional[IntakeFormMetadata] = None  
    template_id: Optional[uuid.UUID] = None 

@router.post("/intake", response_model=AcaiWorkingDraftv2, status_code=201)
async def create_working_draft_intake(intake_request: CreateWorkingDraftIntakeRequest):
    today = date.today()
    user_id = get_current_user_id()

    # Temp (FIX THIS): inline default so local testing works with empty payloads.
    metadata = intake_request.intake_form_metadata or IntakeFormMetadata(
        template_type=TemplateType.SOP,
        issuance_proposed_name="Untitled Test Draft",
    )

    working_draft = AcaiWorkingDraftv2(
        template_id=intake_request.template_id,
        document_name=metadata.issuance_proposed_name or "Untitled Draft",
        intake_form_metadata=metadata,
        draft_author=user_id,
        draft_creation_date=today,
        draft_modified_date=today,
    )
    # TODO: Save to some DB
    return working_draft

class CreateWorkingDraftDocxRequest(BaseModel):
    template_id: Optional[uuid.UUID] = None
    docx_b64: str = Field(description="Base64-encoded .docx file contents")
    file_name: Optional[str] = None

@router.post("/docx", response_model=AcaiWorkingDraftv2, status_code=201)
async def create_working_draft_docx(docx_request: CreateWorkingDraftDocxRequest):
    if llm is None:
        raise HTTPException(status_code=500, detail="LLM connection failed",)
    try:
        docx_bytes = base64.b64decode(docx_request.docx_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64-encoded docx payload.")

    today = date.today()
    user_id = get_current_user_id()

    # Run the pipeline/make it a temp doc we del after the work is done
    docx_path = f"upload_{uuid.uuid4()}.docx"
    with open(docx_path, "wb") as f:
        f.write(docx_bytes)
    try:
        section_dicts = run_sectioning(llm, docx_path)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Document too large: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sectioning failed: {e}")
    finally:
        if os.path.exists(docx_path):
            os.remove(docx_path)

    # Fit into correct object
    sections: List[Section] = [
        Section(
            title=section_dict['title'],
            content=section_dict['content'],
            order_index=index,
        )
    for index, section_dict in enumerate(section_dicts)
]

    working_draft = AcaiWorkingDraftv2(
        template_id=docx_request.template_id,
        document_name=docx_request.file_name if docx_request.file_name else "Untitled Draft",
        sections=sections,
        draft_author=user_id,
        draft_creation_date=today,
        draft_modified_date=today,
    )
    # TODO: Save to some DB
    return working_draft
