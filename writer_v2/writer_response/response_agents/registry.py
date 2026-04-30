from writer_response.response_agents.language_check import (
    passive_voice_fixer,
    spelling_fixer,
    grammar_fixer,
    clarity_fixer,
    flow_fixer,
    writing_style_fixer,
    questionable_language_fixer,
    commercial_endorsement_fixer,
)
from writer_response.response_agents.sentence_length import sentence_length_fixer


# name -> (node_function, description)
ROUTABLE_RESPONSE_AGENTS = {
    "passive_voice_fixer":          (passive_voice_fixer, "Rewrites passive voice to active."),
    "spelling_fixer":               (spelling_fixer, "Corrects spelling with awareness of domain terms."),
    "grammar_fixer":                (grammar_fixer, "Fixes grammar errors."),
    "clarity_fixer":                (clarity_fixer, "Rewrites unclear text."),
    "flow_fixer":                   (flow_fixer, "Smooths logical flow within a span."),
    "writing_style_fixer":          (writing_style_fixer, "Aligns prose with formal policy register."),
    "questionable_language_fixer":  (questionable_language_fixer, "Replaces loaded/biased/imprecise language."),
    "commercial_endorsement_fixer": (commercial_endorsement_fixer, "Removes brand/product endorsements."),
    "sentence_length_fixer":        (sentence_length_fixer, "Splits over-long sentences."),
}
