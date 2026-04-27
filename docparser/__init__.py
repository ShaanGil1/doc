"""
docparser - Convert .docx documents to markdown and split into editable sections.

Public API:

    from docparser import convert
    markdown_text = convert("path/to/file.docx")

    from docparser import run_sectioning, build_llm
    llm = build_llm()
    result = run_sectioning(llm, "path/to/file.docx")
    sections = result["sections"]   # list of {"title", "content"}
    reliable = result["reliable"]   # False if matching was poor

Internal modules:
    converter.py    - .docx -> markdown (no AI, pure metadata + shape detection)
    utils.py        - support functions for the converter
    sectioning.py   - markdown -> {title, content} sections via LLM
    llm_client.py   - LLM connection setup, change models/providers here
"""

from .converter import convert
from .llm_client import build_llm, GEMINI_MODEL
from .sectioning import (
    run_sectioning,
    build_payload,
    match_sections,
    split_markdown,
    Sections,
    SectionItem,
    MAX_DOCUMENT_WORDS,
    MIN_SECTION_WORDS,
    MAX_SECTION_WORDS,
    MAX_RETRIES,
)

__all__ = [
    'convert',
    'build_llm',
    'GEMINI_MODEL',
    'run_sectioning',
    'build_payload',
    'match_sections',
    'split_markdown',
    'Sections',
    'SectionItem',
    'MAX_DOCUMENT_WORDS',
    'MIN_SECTION_WORDS',
    'MAX_SECTION_WORDS',
    'MAX_RETRIES',
]
