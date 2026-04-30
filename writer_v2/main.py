# Pure-function entry points for both routes.

from typing import List

from shared.models import Section_Input, Suggestion
from writer.graph import build_writer_graph
from writer_response.graph import build_writer_response_graph


writer_graph = build_writer_graph()
writer_response_graph = build_writer_response_graph()


# Writer route entry point: section in, suggestions out.
def writer_suggestions_for_section(section: Section_Input) -> List[Suggestion]:
    initial_state = {
        "section_title": section.title,
        "section_content": section.content,
        "section_id": str(section.id),
        "dispatched_agents": [],
        "suggestions": [],
        "final_suggestions": [],
    }
    result = writer_graph.invoke(initial_state)
    return result.get("final_suggestions") or []


# Reviewer route entry point: section in, fixes out.
def reviewer_suggestions_for_section(section: Section_Input) -> List[Suggestion]:
    initial_state = {
        "section_title": section.title,
        "section_content": section.content,
        "section_id": str(section.id),
        "violations": [],
        "current_violation": None,
        "response_suggestions": [],
        "final_response_suggestions": [],
    }
    result = writer_response_graph.invoke(initial_state)
    return result.get("final_response_suggestions") or []
