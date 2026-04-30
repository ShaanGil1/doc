```python
# LanguageCheck + sentence_length finders for the writer route.
"""
LanguageCheck finders. Each scans the section proactively and proposes
fixes for its rule. Same shape as the other writer agents.
"""

from writer.agent_base import make_simple_llm_call, resolve_char_positions


# --- passive_voice_finder -------------------------------------------------

PASSIVE_VOICE_FINDER = "passive_voice_finder"
PASSIVE_VOICE_PROMPT = """You are a writing assistant that detects passive voice in policy/SOP documents.

Look for sentences using passive voice when an actor is named or implied.

Acceptable passive uses (don't flag):
1. Actor genuinely unknown ('the form was lost in transit')
2. Actor irrelevant or deliberately deemphasized ('approved on March 5')
3. Required by genre (legal/policy phrasing like 'shall be deemed')

For each problem, propose an active-voice rewrite that preserves meaning.

Each suggestion must include:
1. original_text: the EXACT passive construction (verbatim)
2. suggestion_text: the active rewrite
3. suggestion_title: a short label

Return empty strings if no clear-cut passive voice issues exist.
"""


def passive_voice_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(PASSIVE_VOICE_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], PASSIVE_VOICE_FINDER)
    return {"suggestions": suggestions}


# --- spelling_finder ------------------------------------------------------

SPELLING_FINDER = "spelling_finder"
SPELLING_PROMPT = """You are a writing assistant that detects misspellings in policy/SOP documents.

Look for words spelled incorrectly using standard American English.

When checking:
1. Don't 'correct' domain-specific terms, proper nouns, or acronyms
2. Preserve the writer's word choice when only spelling is wrong (no synonyms)
3. Default to American spellings unless the document is consistently British
4. If the word might be intentional jargon, leave it alone
5. For compound words, follow the most common form ('email' not 'e-mail')

Each suggestion must include:
1. original_text: the EXACT misspelled word (verbatim)
2. suggestion_text: the corrected spelling
3. suggestion_title: a short label

Return empty strings if no clear misspellings exist.
"""


def spelling_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(SPELLING_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], SPELLING_FINDER)
    return {"suggestions": suggestions}


# --- grammar_finder -------------------------------------------------------

GRAMMAR_FINDER = "grammar_finder"
GRAMMAR_PROMPT = """You are a writing assistant that detects grammar errors in policy/SOP documents.

Things to flag:
1. Subject-verb disagreement ('the team are' should be 'the team is')
2. Tense inconsistency within a sentence
3. Ambiguous pronoun antecedents ('it', 'this', 'they' with unclear referent)
4. Modifier attachment problems (dangling participles, misplaced 'only')
5. Parallel structure violations in lists
6. Comma splices, sentence fragments, or run-ons

Make the minimum change. Fix grammar, don't rewrite content.

Each suggestion must include:
1. original_text: the EXACT problematic span (verbatim)
2. suggestion_text: the corrected version
3. suggestion_title: a short label

Return empty strings if grammar is clean.
"""


def grammar_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(GRAMMAR_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], GRAMMAR_FINDER)
    return {"suggestions": suggestions}


# --- clarity_finder -------------------------------------------------------

CLARITY_FINDER = "clarity_finder"
CLARITY_PROMPT = """You are a writing assistant that detects unclear or hard-to-read sentences in policy/SOP documents.

Common clarity problems:
1. Buried subjects: main actor delayed by introductory clauses
2. Nominalizations ('make a determination' becomes 'determine', 'reach a decision' becomes 'decide')
3. Double or triple negatives ('not unlikely', 'no person shall not')
4. Stacked qualifications that obscure the actual rule
5. Long noun chains ('expense reimbursement form submission process')

Make sentences easier to parse while preserving exact meaning. Policy language
can be precise; don't strip precision, just remove what doesn't earn its place.

Each suggestion must include:
1. original_text: the EXACT unclear span (verbatim)
2. suggestion_text: the clearer rewrite
3. suggestion_title: a short label

Return empty strings if writing is already clear.
"""


def clarity_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(CLARITY_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], CLARITY_FINDER)
    return {"suggestions": suggestions}


# --- flow_finder ----------------------------------------------------------

FLOW_FINDER = "flow_finder"
FLOW_PROMPT = """You are a writing assistant that detects flow problems in policy/SOP documents.

Common flow problems:
1. Abrupt topic shifts without a transition
2. Sentences referencing content the reader hasn't seen yet (forward references)
3. Order that doesn't follow a clear logic (chronological, causal, importance)
4. Missing connectives where they would clarify the relationship between ideas

Fix by reordering, adding a brief transition, or rephrasing. Lightest touch
that resolves the issue. Do not invent content not implied by the text.

Each suggestion must include:
1. original_text: the EXACT problematic span (verbatim)
2. suggestion_text: the smoother version
3. suggestion_title: a short label

Return empty strings if flow is already clean.
"""


def flow_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(FLOW_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], FLOW_FINDER)
    return {"suggestions": suggestions}


# --- writing_style_finder -------------------------------------------------

WRITING_STYLE_FINDER = "writing_style_finder"
WRITING_STYLE_PROMPT = """You are a writing assistant that detects writing-style issues in policy/SOP documents.

Required style:
1. Formal register: no contractions ('do not' not 'don't', 'will not' not 'won't')
2. Third-person voice: no 'we', 'I', 'you' in body content
3. Declarative sentences: avoid rhetorical questions
4. Consistent terminology: don't switch synonyms for the same concept
5. No idioms, slang, or colloquialisms ('move the needle', 'low-hanging fruit')
6. Avoid hyperbole ('absolutely critical', 'utterly essential')

Make the minimum change. Adjust register, don't rewrite meaning.

Each suggestion must include:
1. original_text: the EXACT problematic span (verbatim)
2. suggestion_text: the formal-register version
3. suggestion_title: a short label

Return empty strings if style is already consistent.
"""


def writing_style_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(WRITING_STYLE_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], WRITING_STYLE_FINDER)
    return {"suggestions": suggestions}


# --- questionable_language_finder -----------------------------------------

QUESTIONABLE_LANGUAGE_FINDER = "questionable_language_finder"
QUESTIONABLE_LANGUAGE_PROMPT = """You are a writing assistant that detects questionable language in policy/SOP documents.

Things to flag:
1. Loaded or biased phrasing ('clearly', 'obviously', 'common sense')
2. Vague intensifiers ('very important', 'extremely critical')
3. Non-inclusive or outdated terminology
4. Imprecise quantifiers in count-sensitive positions ('many', 'several', 'often'
   where a number or threshold belongs)
5. Hedging that obscures responsibility ('it is generally agreed that...')

Substitute neutral, specific language. If a vague quantifier is appropriate
(no specific number applies), leave it.

Each suggestion must include:
1. original_text: the EXACT problematic span (verbatim)
2. suggestion_text: the neutral version
3. suggestion_title: a short label

Return empty strings if language is already neutral.
"""


def questionable_language_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(QUESTIONABLE_LANGUAGE_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], QUESTIONABLE_LANGUAGE_FINDER)
    return {"suggestions": suggestions}


# --- commercial_endorsement_finder ----------------------------------------

COMMERCIAL_ENDORSEMENT_FINDER = "commercial_endorsement_finder"
COMMERCIAL_ENDORSEMENT_PROMPT = """You are a writing assistant that detects commercial product endorsements in policy/SOP documents.

Look for:
1. Specific brand/product names that should be generic categories:
     'DocuSign' becomes 'electronic signature platform'
     'Slack' becomes 'team messaging tool'
     'Adobe Acrobat' becomes 'PDF reader'
2. Endorsing language ('we recommend', 'the best option is', 'preferred vendor')

Don't flag brand mentions that are necessary for compliance:
1. A regulation that specifically requires that product
2. A contract or agreement that names a vendor by name
3. An interface or system the reader literally interacts with by that name

Each suggestion must include:
1. original_text: the EXACT brand mention or endorsing phrase (verbatim)
2. suggestion_text: the generic substitute
3. suggestion_title: a short label

Return empty strings if no inappropriate endorsements exist.
"""


def commercial_endorsement_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(COMMERCIAL_ENDORSEMENT_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], COMMERCIAL_ENDORSEMENT_FINDER)
    return {"suggestions": suggestions}


# --- sentence_length_finder -----------------------------------------------

SENTENCE_LENGTH_FINDER = "sentence_length_finder"
SENTENCE_LIMIT = 35

SENTENCE_LENGTH_PROMPT = f"""You are a writing assistant that detects over-long sentences in policy/SOP documents.

Sentences should generally be {SENTENCE_LIMIT} words or fewer.

When splitting:
1. Break at natural points: between independent clauses, before transitions
   ('however', 'because', 'while', 'although'), or before relative clauses
2. Each resulting sentence must be grammatically complete and stand alone
3. Preserve original meaning exactly. No content lost or added.
4. Combined word count should be roughly the same as the original

Some sentences over {SENTENCE_LIMIT} words are appropriate (enumerations with parallel
items, complex legal definitions). If you can't split cleanly, return empty strings.

Each suggestion must include:
1. original_text: the EXACT long sentence (verbatim)
2. suggestion_text: the split version
3. suggestion_title: a short label

Return empty strings if all sentences are reasonable length.
"""


def sentence_length_finder(state) -> dict:
    llm_suggestion = make_simple_llm_call(SENTENCE_LENGTH_PROMPT, state["section_content"])
    suggestions = resolve_char_positions(
        llm_suggestion, state["section_content"], state["section_id"], SENTENCE_LENGTH_FINDER)
    return {"suggestions": suggestions}
```
```python
# Routable writer sub-agents registry (the dispatcher picks from these).
"""
Routable writer sub-agents registry.

Future agents documented in future_agents.py (no code, just goals + blockers).
"""

from writer.writer_agents.sentence_completer import sentence_completer
from writer.writer_agents.clarity_rewriter import clarity_rewriter
from writer.writer_agents.list_completer import list_completer
from writer.writer_agents.paragraph_expander import paragraph_expander
from writer.writer_agents.redundancy_trimmer import redundancy_trimmer
from writer.writer_agents.paragraph_splitter import paragraph_splitter

from writer.writer_agents.language_check import (
    passive_voice_finder,
    spelling_finder,
    grammar_finder,
    clarity_finder,
    flow_finder,
    writing_style_finder,
    questionable_language_finder,
    commercial_endorsement_finder,
    sentence_length_finder,
)


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

    # LanguageCheck finders (one per rule)
    "passive_voice_finder": (
        passive_voice_finder,
        "Detects passive voice and proposes active rewrites.",
        [],
    ),
    "spelling_finder": (
        spelling_finder,
        "Detects misspellings and proposes corrections.",
        [],
    ),
    "grammar_finder": (
        grammar_finder,
        "Detects grammar errors and proposes minimal-change fixes.",
        [],
    ),
    "clarity_finder": (
        clarity_finder,
        "Detects unclear or hard-to-read sentences and proposes clearer rewrites.",
        [],
    ),
    "flow_finder": (
        flow_finder,
        "Detects flow problems between sentences and proposes smoother transitions.",
        [],
    ),
    "writing_style_finder": (
        writing_style_finder,
        "Detects formal-register violations (contractions, voice, slang).",
        [],
    ),
    "questionable_language_finder": (
        questionable_language_finder,
        "Detects loaded, vague, or biased language.",
        [],
    ),
    "commercial_endorsement_finder": (
        commercial_endorsement_finder,
        "Detects brand/product endorsements that should be generic categories.",
        ["long_sentence"],
    ),
    "sentence_length_finder": (
        sentence_length_finder,
        "Detects sentences over 35 words and proposes splits.",
        ["long_sentence"],
    ),
}
```
