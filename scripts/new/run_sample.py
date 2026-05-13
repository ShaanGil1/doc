# Run the find_conflict pipeline against SAMPLE_SECTIONS and print the flags.
"""
Usage: python run_sample.py

Registers FakeLLM responses for the sample, runs the pipeline, prints each
flag in a readable form.
"""

from llm_client import register_fake_responses, reset_fake_llm
from main import find_conflict_flags_for_draft
from models import FindConflictInput
from sample_data import (
    SAMPLE_CONFLICT_RESPONSES,
    SAMPLE_EXTRACTOR_RESPONSES,
    SAMPLE_SECTIONS,
    SAMPLE_SELECTED_DOC_IDS,
)


# Find the section that owns a given section_id so we can print the title.
def section_title_for(section_id: str) -> str:
    for section in SAMPLE_SECTIONS:
        if str(section.id) == section_id:
            return section.title
    return "(unknown section)"


# Run the pipeline and pretty-print the flags.
def main():
    reset_fake_llm()
    register_fake_responses("ExtractedClaimsLLM", SAMPLE_EXTRACTOR_RESPONSES)
    register_fake_responses("ConflictFindings", SAMPLE_CONFLICT_RESPONSES)

    payload = FindConflictInput(
        sections=SAMPLE_SECTIONS,
        selected_doc_ids=SAMPLE_SELECTED_DOC_IDS,
    )

    flags = find_conflict_flags_for_draft(payload)

    print(f"\nfind_conflict ran on {len(SAMPLE_SECTIONS)} sections, "
          f"produced {len(flags)} flag(s).\n")

    for index, flag in enumerate(flags, start=1):
        title = section_title_for(flag.section_id or "")
        print(f"--- flag {index} ---")
        print(f"section:        {title}")
        print(f"offending text: \"{flag.offending_text}\"")
        print(f"span:           chars {flag.start_char} to {flag.end_char}")
        print(f"reason:         {flag.violation_description}")
        print()


if __name__ == "__main__":
    main()
