# Routable writer sub-agents registry (the dispatcher picks from these)
from writer.writer_agents.sentence_completer import sentence_completer
from writer.writer_agents.clarity_rewriter import clarity_rewriter
from writer.writer_agents.list_completer import list_completer
from writer.writer_agents.paragraph_expander import paragraph_expander
from writer.writer_agents.redundancy_trimmer import redundancy_trimmer
from writer.writer_agents.paragraph_splitter import paragraph_splitter


# name -> (node_function, description, heuristic_triggers)
ROUTABLE_AGENTS = {
    "sentence_completer": (
        sentence_completer,
        "Detects incomplete sentences and proposes completions.",
        ["hanging_sentence"],
    ),
    "clarity_rewriter": (
        clarity_rewriter,
        "Rewrites wordy or overly complex sentences.",
        ["wordy_phrase", "long_sentence"],
    ),
    "list_completer": (
        list_completer,
        "Detects partial lists and proposes next items.",
        ["list_pattern"],
    ),
    "paragraph_expander": (
        paragraph_expander,
        "Expands sparse one-sentence paragraphs with grounded elaboration.",
        ["sparse_paragraph"],
    ),
    "redundancy_trimmer": (
        redundancy_trimmer,
        "Detects repeated content and proposes trims.",
        ["repeated_phrasing"],
    ),
    "paragraph_splitter": (
        paragraph_splitter,
        "Splits overly long paragraphs at natural topic shifts.",
        ["long_paragraph"],
    ),
}
