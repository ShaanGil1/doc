# Run both routes against a sample section.
"""
Run both routes against a sample section.

Set GOOGLE_API_KEY for real Gemini; otherwise FakeLLM canned outputs.
REVIEWER_REJECT_RATE rejects writer-route suggestions for testing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.models import Section_Input
from main import writer_suggestions_for_section, reviewer_suggestions_for_section


# Sample designed to trigger both routes:
#   writer:   wordy phrasing, redundant content, long sentence
#   reviewer: passive voice, sentence >35 words, contraction
SAMPLE_SECTION = Section_Input(
    title="Expense Reimbursement Policy",
    content=(
        "In order to submit an expense for reimbursement, employees must complete the form.\n"
        "\n"
        "required documentation includes:\n"
        "- Original receipt\n"
        "- Manager approval\n"
        "- Project code\n"
        "\n"
        "The expense form must be submitted within 30 days of 4/29/26. "
        "Late submissions won't be processed.\n"
        "\n"
        "This Policy will be reviewed annually. Reimbursement processing typically takes 2-3 weeks. "
        "The finance team reviews each submission, and validates the expense against policy, and "
        "approves or rejects, but in some cases additional documentation may be requested for further "
        "review by the finance team to validate the expense against policy requirements before approval."
    ),
)


# Format and print one route's suggestion list.
def print_suggestions(label, suggestions):
    print(f"\n{label}: {len(suggestions)} suggestion(s)")
    print("-" * 70)
    if not suggestions:
        print("  (none)")
        return
    for index, suggestion in enumerate(suggestions, 1):
        print(f"[{index}] {suggestion.sub_agent}: {suggestion.suggestion_title}")
        print(f"    Original:   {suggestion.original_text!r}")
        print(f"    Suggestion: {suggestion.suggestion_text!r}")
        print(f"    Position:   chars {suggestion.start_char} to {suggestion.end_char}")
        print()


def main():
    print(f"Running both routes on: {SAMPLE_SECTION.title!r}")
    print("=" * 70)
    #print_suggestions("WRITER route", writer_suggestions_for_section(SAMPLE_SECTION))
    print_suggestions("REVIEWER route", reviewer_suggestions_for_section(SAMPLE_SECTION))


if __name__ == "__main__":
    main()
