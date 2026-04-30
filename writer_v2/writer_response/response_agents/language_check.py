# LanguageCheck fixers (one per rule from get_consolidated_language_prompt)

from writer_response.response_base import call_response_agent_llm

PASSIVE_VOICE_FIXER = "passive_voice_fixer"
PASSIVE_VOICE_RULE = """Sentences should use active voice when an actor is named or implied.

Acceptable passive uses (don't rewrite):
1. Actor genuinely unknown ('the form was lost in transit')
2. Actor irrelevant or deliberately deemphasized ('approved on March 5')
3. Required by genre (legal/policy standardized phrasing like 'shall be deemed')
4. The patient is what the sentence is genuinely about ('the policy was published in 2023')

Otherwise, rewrite to active voice with a clear subject performing the action.

Example: 'The form must be submitted by the employee within 30 days'
becomes  'The employee must submit the form within 30 days'

Make the minimum change. Don't restructure surrounding sentences."""


def passive_voice_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        PASSIVE_VOICE_RULE, violation, state["section_content"], state["section_id"], PASSIVE_VOICE_FIXER)
    return {"response_suggestions": suggestions}


SPELLING_FIXER = "spelling_fixer"
SPELLING_RULE = """Words must be spelled correctly using standard American English.

When fixing:
1. Don't 'correct' domain-specific terms, proper nouns, or acronyms
2. Preserve the writer's word choice when only spelling is wrong (no synonyms)
3. Default to American spellings ('color', 'organize', 'analyze') unless the
   document is consistently British
4. If the word might be intentional jargon or a term of art, leave it alone
5. For compound words, follow the most common form ('email' not 'e-mail')

If you genuinely can't tell whether it's a misspelling or intentional, return empty strings."""

def spelling_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        SPELLING_RULE, violation, state["section_content"], state["section_id"], SPELLING_FIXER)
    return {"response_suggestions": suggestions}


GRAMMAR_FIXER = "grammar_fixer"
GRAMMAR_RULE = """Sentences must follow standard English grammar.

Things to fix:
1. Subject and verb agreement ('the team are' becomes 'the team is')
2. Tense consistency within a sentence ('he ran and jumps' becomes 'he ran and jumped')
3. Clear pronoun antecedents (no ambiguous 'it', 'this', 'they')
4. Modifier attachment (dangling participles, misplaced 'only')
5. Parallel structure in lists ('to write, editing, and review' becomes 'to write, edit, and review')
6. No comma splices, sentence fragments, or run-ons

Make the minimum change. Fix the grammar, don't rewrite content. Preserve
the original word choice and tone."""

def grammar_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        GRAMMAR_RULE, violation, state["section_content"], state["section_id"], GRAMMAR_FIXER)
    return {"response_suggestions": suggestions}

CLARITY_FIXER = "clarity_fixer"
CLARITY_RULE = """Text must be clear and easy to read at first pass.

Common clarity problems:
1. Buried subjects: main actor delayed by introductory clauses
2. Nominalizations ('make a determination' becomes 'determine', 'reach a decision' becomes 'decide')
3. Double or triple negatives ('not unlikely', 'no person shall not')
4. Stacked qualifications that obscure the actual rule
5. Long noun chains ('expense reimbursement form submission process')

Example: 'The making of a determination by the committee regarding the
applicability of the policy will be conducted within 30 days'
becomes  'The committee will determine whether the policy applies within 30 days'

Make the sentence easier to parse while preserving exact meaning. Policy
language can be precise. Don't strip precision; just remove what doesn't
earn its place."""

def clarity_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        CLARITY_RULE, violation, state["section_content"], state["section_id"], CLARITY_FIXER)
    return {"response_suggestions": suggestions}

FLOW_FIXER = "flow_fixer"
FLOW_RULE = """Text should flow logically from one sentence to the next.

Common flow problems:
1. Abrupt topic shifts without a transition
2. Sentences referencing content the reader hasn't seen yet (forward references)
3. Order that doesn't follow a clear logic (chronological, causal, importance)
4. Missing connectives where they would clarify the relationship between ideas
   ('however', 'because', 'as a result', 'in addition')

Fix by reordering, adding a brief transition, or rephrasing. Lightest touch
that resolves the issue. Do not invent content not implied by the surrounding
text. If the flow is bad because the underlying logic is muddled, that's a
content problem the writer needs to fix; return empty strings."""

def flow_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        FLOW_RULE, violation, state["section_content"], state["section_id"], FLOW_FIXER)
    return {"response_suggestions": suggestions}


WRITING_STYLE_FIXER = "writing_style_fixer"
WRITING_STYLE_RULE = """Policy and SOP documents use a consistent formal style.

Required:
1. Formal register: no contractions ('do not' not 'don't', 'will not' not 'won't')
2. Third-person voice: no 'we', 'I', 'you' in body content (titles and instructions
   to the reader can be exceptions)
3. Declarative sentences: avoid rhetorical questions
4. Consistent terminology: don't switch synonyms for the same concept within a section
5. No idioms, slang, or colloquialisms ('move the needle', 'low-hanging fruit', 'a no-brainer')
6. Avoid hyperbole ('absolutely critical', 'utterly essential')

Make the minimum change to bring the offending text in line. Adjust the
register, don't rewrite the meaning."""

def writing_style_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        WRITING_STYLE_RULE, violation, state["section_content"], state["section_id"], WRITING_STYLE_FIXER)
    return {"response_suggestions": suggestions}

QUESTIONABLE_LANGUAGE_FIXER = "questionable_language_fixer"
QUESTIONABLE_LANGUAGE_RULE = """Policy/SOP documents must use neutral, precise language.

Things to fix:
1. Loaded or biased phrasing ('clearly', 'obviously', 'common sense'). These
   signal the writer's frustration, not a fact.
2. Vague intensifiers that add no information ('very important', 'extremely
   critical', 'highly significant')
3. Non-inclusive or outdated terminology
4. Imprecise quantifiers in count-sensitive positions ('many', 'several',
   'often' where a number or threshold belongs)
5. Hedging that obscures responsibility ('it is generally agreed that...',
   'it has been determined that...'). Name the actor.

Substitute neutral, specific language. If a vague quantifier is appropriate
because no specific number applies, leave it; only fix when specificity is
missing where it belongs."""


def questionable_language_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        QUESTIONABLE_LANGUAGE_RULE, violation, state["section_content"], state["section_id"], QUESTIONABLE_LANGUAGE_FIXER)
    return {"response_suggestions": suggestions}


COMMERCIAL_ENDORSEMENT_FIXER = "commercial_endorsement_fixer"
COMMERCIAL_ENDORSEMENT_RULE = """Policy documents must not appear to endorse specific products, services, or brands.
When fixing:
1. Replace specific brand/product names with the generic category:
    'DocuSign' becomes 'electronic signature platform'
    'Slack' becomes 'team messaging tool'
    'Adobe Acrobat' becomes 'PDF reader'
2. Remove endorsing language ('we recommend', 'the best option is', 'preferred vendor')
3. Keep the functional requirement intact. The document still needs to specify
WHAT the reader must do, just not which brand to use.

Don't strip brand mentions that are necessary for compliance:
1. A regulation that specifically requires that product
2. A contract or agreement that names a vendor by name
3. An interface or system the reader will literally interact with by that name

Trust the reviewer's flag. Only the spans they flag are inappropriate."""


# Node: dispatched when the reviewer flags commercial_product_endorsement
def commercial_endorsement_fixer(state) -> dict:
    violation = state["current_violation"]
    if violation is None:
        return {"response_suggestions": []}
    suggestions = call_response_agent_llm(
        COMMERCIAL_ENDORSEMENT_RULE, violation, state["section_content"], state["section_id"], COMMERCIAL_ENDORSEMENT_FIXER)
    return {"response_suggestions": suggestions}
