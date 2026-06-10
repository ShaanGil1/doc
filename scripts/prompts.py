# Prompts for the find_conflict route.


CLAIM_EXTRACTOR_PROMPT = """You are extracting checkable claims from a document section. A claim is a specific factual statement that could be verified against authoritative sources.

Extract up to 5 of the most important claims from the section below.

A good claim is:
- A specific factual assertion (a rule, threshold, requirement, definition, or procedure)
- Self-contained enough to be checked against other documents
- Substantive (not boilerplate or transitional text)

For each claim, return two fields:

1. claim_text: a rewritten version of the claim, optimized for retrieval against a document corpus. The substance of the claim must be preserved exactly. Do not add information, do not soften or strengthen the assertion, do not infer intent. You are only rephrasing for search quality. Acceptable transformations: strip filler words, expand acronyms when their meaning is unambiguous from context, resolve pronouns to their referents, phrase as a complete declarative sentence. The resulting claim_text should describe the same fact as original_text, just in a form that retrieval will match better.

2. original_text: an EXACT verbatim substring from the section content. This must be character-for-character identical to text in the section, including punctuation, capitalization, and whitespace. Do not paraphrase. Do not add or remove words. Do not change punctuation. If you would need to alter the text in any way to make a clean sentence, pick a different substring that you can quote exactly.

What is NOT a claim (do not extract these):
- Boilerplate, transitions, or framing ("This section covers...", "As noted above...", "The following applies.").
- Opinions, intentions, goals, or aspirations.
- Vague or general statements with nothing specific to verify.
- Background or narrative that asserts no concrete, checkable fact.
If a sentence is fluff, filler, or contains nothing factual to check against sources, it is not a claim. Skip it.

Returning an empty list is a correct and expected outcome. If the section has no checkable claims, return an empty list. Do not invent or stretch claims to fill space. Return at most 5 claims; if the section has fewer, return fewer.

SECTION TITLE: {section_title}

SECTION CONTENT:
{section_content}
"""


CLAIM_EXTRACTOR_RETRY_PROMPT = """You previously extracted claims from this section but the original_text fields did not match the section verbatim. Re-extract those claims, paying very close attention to copying the exact substring.

The original_text MUST be character-for-character identical to a substring of the section content. Check your work by mentally locating each original_text in the section before returning.

SECTION CONTENT:
{section_content}

CLAIMS TO RE-EXTRACT (use these claim_texts as guidance for what to find):
{failed_claims}
"""


FIND_CONFLICT_PROMPT = """You are checking claims from one section of a document against retrieved source material from reference documents. Your job is to find conflicts.

You are given a numbered list of SOURCES (retrieved reference material) and a numbered list of CLAIMS (statements pulled from the section). Check every claim against the sources and report any conflicts.

A conflict is anything in the sources that disagrees with a claim, makes it incorrect, makes it outdated, or makes it incompatible with the source. Conflicts can take many forms. Here are examples of what counts:

- A claim states a numeric threshold or limit. A source states a different number for the same thing. CONFLICT.

- A claim cites a version, date, or edition of a referenced document. A source is a newer version that has changed what the claim states. CONFLICT.

- A claim describes a rule or procedure one way. A source describes the same rule or procedure differently. CONFLICT.

- A claim defines a term, role, or category. A source defines it differently. CONFLICT.

- A claim assigns a responsibility or permission to one party. A source assigns that responsibility or permission to a different party. CONFLICT.

- A claim states a deadline, timeframe, or duration. A source states a different one for the same action. CONFLICT.

- A claim uses a term or acronym one way. A source uses it differently for the same context. CONFLICT.

These are examples, not a closed list. Use judgment for other disagreements.

What is NOT a conflict:
- A source is on a related topic but does not directly address what a claim states. NOT a conflict.
- A source uses different phrasing for the same idea. NOT a conflict.
- A source provides additional detail a claim happens not to mention. NOT a conflict (unless it actively disagrees).
- You suspect a claim is wrong based on your own knowledge but no retrieved source supports your suspicion. NOT a conflict.

CRITICAL RULES

- The SOURCES are your only valid evidence. Do not flag conflicts based on your own knowledge.
- The CONTEXT below is the full section the claims came from, provided only so you understand what each claim means. Do NOT flag conflicts you notice inside the CONTEXT. It is reference material only.
- For each conflict, claim_index is the number of the claim in the CLAIMS list and source_index is the number of the source in the SOURCES list. Do not invent indices.
- source_excerpt must be a verbatim sentence or short phrase from the source, copied exactly.
- Only report a conflict when a source directly and clearly disagrees with a claim. Do not dig for conflicts. Do not stretch interpretations. Do not report anything you would have to argue for.
- Returning an empty list is correct and expected. If nothing in the sources clearly disagrees with any claim, return an empty list. Most checks find no conflicts; that is a normal, correct result, not a failure.
- A single claim may have zero, one, or several conflicts. Report each one separately. A claim with no conflict simply does not appear in your output.
- If two sources point to the same underlying conflict for the same claim, pick the stronger one and report it once.

SOURCES (the only valid source of conflicts)
{formatted_sources}

CLAIMS (statements from the section to check)
{formatted_claims}

CONTEXT (the full section the claims came from, for understanding only)
{context}

Find any conflicts between the CLAIMS and the SOURCES. Return an empty list if there are no clear conflicts.
"""
