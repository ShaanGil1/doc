"""
app.py

Minimal FastAPI app that mounts the working-draft router.

To run:
    pip install fastapi uvicorn mammoth markdownify python-docx \\
                langchain-google-genai pydantic
    uvicorn app:app --reload --port 8000

Then visit http://localhost:8000/docs for the auto-generated API docs.
"""

from fastapi import FastAPI

from working_draft_docx import router as working_draft_router


app = FastAPI(title="docx_to_workingdraft")
app.include_router(working_draft_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
