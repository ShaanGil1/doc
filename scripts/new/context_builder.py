# Slice +/- 200 words around a claim, spilling into at most one neighbor section each side

from typing import Dict, List
from models import ExtractedClaim, Section

WINDOW_HALF_WORDS = 200

# Build a +/- 200 word context window, spilling into one neighbor per side if needed
def build_context(
    claim: ExtractedClaim,
    sections_by_id: Dict[str, Section],
    sections_ordered: List[Section],
) -> str:
    home_section = sections_by_id[claim.section_id]
    home_index = next(
        index for index, section in enumerate(sections_ordered)
        if str(section.id) == claim.section_id
    )

    before_words = home_section.content[:claim.start_char].split()
    after_words = home_section.content[claim.end_char:].split()

    if len(before_words) < WINDOW_HALF_WORDS and home_index > 0:
        deficit = WINDOW_HALF_WORDS - len(before_words)
        previous_words = sections_ordered[home_index - 1].content.split()
        before_words = previous_words[-deficit:] + before_words

    if len(after_words) < WINDOW_HALF_WORDS and home_index < len(sections_ordered) - 1:
        deficit = WINDOW_HALF_WORDS - len(after_words)
        next_words = sections_ordered[home_index + 1].content.split()
        after_words = after_words + next_words[:deficit]

    before_window = before_words[-WINDOW_HALF_WORDS:]
    after_window = after_words[:WINDOW_HALF_WORDS]

    return " ".join(before_window) + " " + claim.original_text + " " + " ".join(after_window)
