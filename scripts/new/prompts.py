# Prompts for the find_conflict route.
CLAIM_EXTRACTOR_PROMPT = """You are extracting checkable claims/statements from a document section.
A claim is a specific factual statement that could be verified against authoritative sources.
\n
Extract up to 5 of the most important claims from the section below.
A good claim is:
- A specific factual assertion (a rule, threshold, requirement, definition, or procedure)
- Self-contained enough to be checked against other documents
- Substantive (not boilerplate or transitional text)
\n
For each claim, return two fields:
1. claim_text: a rewritten version of the claim, optimized for retrieval against a document corpus.
   The substance of the claim must be preserved exactly. Do not add information.
   Do not soften or strengthen the assertion.
   Do not infer intent.
   You are only rephrasing for search quality.
   \n
   Acceptable transformations:
     - strip filler words
     - expand acronyms when their meaning is unambiguous from context
     - resolve pronouns to their referents
     - phrase as a complete declarative sentence
   The resulting claim_text should describe the same fact as original_text,
   just in a form that retrieval will match better.

2. original_text: an EXACT verbatim substring from the section content.
   This must be character-for-character identical to text in the section,
   including punctuation, capitalization, and whitespace.
   Do not paraphrase.
   Do not add or remove words.
   Do not change punctuation.
   **Before returning, verify each original_text appears character-for-character in the section content.**
\n
Return at most 5 claims.
If the section has fewer checkable claims, return fewer.
If the section has no checkable claims, return an empty list.
\n
SECTION TITLE:
{section_title}
\n
SECTION CONTENT:
{section_content}
"""

CLAIM_EXTRACTOR_RETRY_PROMPT = """You previously extracted claims from this section but the original_text fields
did not match the section verbatim.
Re-extract those claims, paying very close attention to copying the exact substring.

The original_text MUST be character-for-character identical to a substring of the section content.
Check your work by mentally locating each original_text in the section before returning.
\n
SECTION CONTENT:
{section_content}
\n
CLAIMS TO RE-EXTRACT (use these claim_texts as guidance for what to find):
{failed_claims}
"""

FIND_CONFLICT_PROMPT = """You are checking a claim from a document against retrieved source material
from reference documents. Your job is to find conflicts.
\n
A conflict is anything in the retrieved sources that disagrees/contradicts with the claim,
makes it incorrect, makes it outdated, or makes it incompatible with the source. 
\n
Conflicts can take many forms. Here are examples of what counts:
- The claim states a numeric threshold or limit. A source states a different number for the same thing.
- The claim cites a version, date, or edition of a referenced document. A source is a newer version that has changed what the claim states.
- The claim describes a rule or procedure one way. A source describes the same rule or procedure differently.
- The claim defines a term, role, or category. A source defines it differently.
- The claim assigns a responsibility or permission to one party. A source assigns that responsibility or permission to a different party.
- The claim states a deadline, timeframe, or duration. A source states a different one for the same action.
- The claim uses a term or acronym one way. A source uses it differently for the same context.
\n
These are examples, not a closed list. Use judgment for other disagreements.
\n
What is NOT a conflict:
- The source is on a related topic but does not directly address what the claim states.
- The source uses different phrasing for the same idea.
- The source provides additional detail the claim happens not to mention. NOT a conflict (unless it actively disagrees).
- You suspect the claim is wrong based on your own knowledge but no retrieved source supports your suspicion.
\n
CRITICAL RULES
- The retrieved sources are your only valid evidence. Do not flag conflicts based on your own knowledge.
- The CONTEXT below is provided to help you understand what the claim means. Do NOT flag conflicts you notice in the context. Context is reference material only.
- source_chunk_index must be the number prefixing the chunk in RETRIEVED SOURCES (1 for [1], 2 for [2], and so on). Do not invent indices.
- source_excerpt must be a verbatim sentence or short phrase from the chunk, copied exactly.
- Only report a conflict when the retrieved sources directly and clearly disagree with the claim:
   - Do not dig for conflicts.
   - Do not stretch interpretations.
   - Do not report something you would have to argue for.
   - If nothing in the sources clearly disagrees with the claim, return an empty list.
   - An empty list is the correct and frequent answer.
- A single claim may have zero, one, or several conflicts. Report each one separately.
- If two retrieved chunks point to the same underlying conflict, pick the stronger one and report it once.
\n
CLAIM:
{claim_text}
\n
CONTEXT (the section the claim came from, for understanding only):
{context}
\n
RETRIEVED SOURCES (the only valid source of conflicts):
{formatted_chunks}
\n
Find any conflicts between the CLAIM and the RETRIEVED SOURCES.
Return an empty list if there are no clear conflicts.
"""