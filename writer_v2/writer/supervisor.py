# Supervisor + Helpers

import re
from typing import Dict, List
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from llm_client import llm_client
from reviewer.checker import reviewer_check
from writer.state import WriterGraphState
from writer.writer_agents.registry import ROUTABLE_AGENTS

# Heuristic signals: cheap-to-compute surface features that might indicate certain issues
LIST_PATTERN_RE = re.compile(r'^\s*([-*•]|\d+[.)])\s+', re.MULTILINE)
HANGING_SENTENCE_RE = re.compile(r'(?:,|\b(?:and|but|or|because)\b)\s*$', re.MULTILINE | re.IGNORECASE)
WORDY_PHRASES = (
    'in order to', 'due to the fact that', 'at this point in time',
    'in the event that', 'for the purpose of', 'a large number of',
    'with regard to', 'in spite of the fact that', 'has the ability to',
    'make a determination',
)
SENTENCE_LIMIT = 35

# Cheap repetition check: any 4-word phrase that appears more than once
def has_repeated_phrasing(content: str) -> bool:
    words = re.findall(r'\w+', content.lower())
    if len(words) < 8:
        return False
    seen = set()
    for index in range(len(words) - 3):
        phrase = tuple(words[index:index + 4])
        if phrase in seen:
            return True
        seen.add(phrase)
    return False

# Coarse "this kind of issue might exist" signals that inform the dispatcher LLM
def compute_signals(content: str) -> Dict[str, bool]:
    paragraphs = [paragraph for paragraph in content.split('\n\n') if paragraph.strip()]
    sentences = [sentence.strip() for sentence in re.split(r'[.!?]+', content) if sentence.strip()]
    lower = content.lower()
    return {
        "list_pattern": bool(LIST_PATTERN_RE.search(content)),
        "hanging_sentence": bool(HANGING_SENTENCE_RE.search(content)),
        "wordy_phrase": any(phrase in lower for phrase in WORDY_PHRASES),
        "long_sentence": any(len(sentence.split()) > SENTENCE_LIMIT for sentence in sentences),
        "sparse_paragraph": any(0 < len(paragraph.split()) < 30 for paragraph in paragraphs),
        "long_paragraph": any(len(paragraph.split()) > 150 for paragraph in paragraphs),
        "repeated_phrasing": has_repeated_phrasing(content),
    }


# Schema the dispatcher LLM returns (which agents to fire)
class DispatcherOutput(BaseModel):
    agents_to_run: List[str] = Field(description="Agent names from the available list.")
    reasoning: str = Field(description="Brief rationale (one or two sentences).")


# Node: compute signals, run the LLM, return the names of agents to fan out to
def supervisor(state: WriterGraphState) -> dict:
    content = state["section_content"]
    signals = compute_signals(content)

    descriptions = "\n".join(
        f"  {name}: {description} (heuristic triggers: {', '.join(triggers)})"
        for name, (_, description, triggers) in ROUTABLE_AGENTS.items()
    )
    triggered = sorted(name for name, is_set in signals.items() if is_set)

    system_prompt = f"""You are a dispatcher for a writing-assistant pipeline. 
    Decide which sub-agents should run on a section.
    Available agents:
    {descriptions}
    Heuristic signals from a cheap pre-scan: {', '.join(triggered) if triggered else '(none)'}
    Pick agents likely to find real, useful issues. Use signals as a starting point but apply judgment. 
    The heuristic is shallow; you can see things it can't.

    Rules:
    1. Only return names from the list above.
    2. Empty list is fine if no agents seem useful.
    3. Don't dispatch agents whose triggers are irrelevant.
    4. Reasoning: one or two sentences.
    """
    structured_llm = llm_client.with_structured_output(DispatcherOutput)
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Section title: {state['section_title']}\nSection content:\n{content}"),
    ])

    if result is None:
        return {"dispatched_agents": []}
    available = ROUTABLE_AGENTS.keys()
    dispatched = [name for name in (result.agents_to_run or []) if name in available]
    return {"dispatched_agents": dispatched}


# Reviewer rule-checks writer suggestions, drops rejected, returns final list
def validate_and_filter(state: WriterGraphState) -> dict:
    suggestions = state["suggestions"]
    rejected = set(reviewer_check(state["section_content"], suggestions))
    final_suggestions = [
        suggestion for index, suggestion in enumerate(suggestions) if index not in rejected
    ]
    return {"final_suggestions": final_suggestions}
