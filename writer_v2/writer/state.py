# LangGraph state for the writer subgraph.

from typing import List
from typing_extensions import TypedDict
from shared.models import Suggestion


# State shape passed through the graph
class WriterGraphState(TypedDict):
    section_title: str
    section_content: str
    section_id: str
    dispatched_agents: List[str]
    suggestions: List[Suggestion]
    final_suggestions: List[Suggestion]
