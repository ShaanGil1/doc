# Edits: the malformed-markdown fallback (the 40% rule)

The whole change as replacement blocks sliced from the committed files, in apply order: two files, no new file.
Tests, docs and the fake model are in the repository commit, not here. `md_to_docx/` is untouched.
After applying, `python run_all.py --no-live` must end ALL GOOD (46 converter checks, 49 agent checks).

## What changed, and why

| where | what | why |
|---|---|---|
| prompts.py `INSTRUCTION` | a `%(note)s` placeholder after "a heading line is the start." | empty on the normal path, so that prompt is byte-identical to before; carries the note on the re-ask |
| prompts.py `MALFORMED_NOTE` | five lines: the markers are missing or unreliable and are not the decider; report each enclosure once where its content begins | the only prompt change the fallback needs |
| agent.py knobs | `FALLBACK_UNPLACED_SHARE = 0.40`, `FALLBACK_UNPLACED_LINES = 10`, `FALLBACK_SHORT_BODY = 15` | the 40% rule, adjustable in one place |
| agent.py `unplaced_share` (new) | non-blank lines held by no section, enclosure or back-matter block, over the total | the trigger; cover, signature and ToC bodies count only up to 15 lines because on a stripped document the signature marker swallows everything after it |
| agent.py `instruction(note="")` | passes the note into the prompt | one function serves the normal question and the re-ask |
| agent.py `llm_boundaries`, step 5b | after the retries and backfill: measure; if the rule trips, ask once more with the note and take the answer through `check_map` with the shape rule off; provenance skipped for that answer | the model already points at the plain title lines; only the title-shape rule refused them |
| agent.py `verify`, `check_map`, `enclosure_titles` | a `shaped` switch, default on | the same validator serves the re-ask; quote, order and duplicate checks still apply, only the shape rule is lifted |
| agent.py `title_inline` | a last branch for a plain "NAME: rest" line whose name is a section alias or cover label | an accepted plain title line is consumed as the title, so "OPR: DLA J6" would print an empty OPR; guarded so any title-shaped line behaves exactly as before |

## 1. `md_section_agent/models/prompts.py`

### Replace the line `Documents may instead use # headings for the same titles; a heading line is the start.` with

```python
Documents may instead use # headings for the same titles; a heading line is the start.%(note)s
```

### Replace the line `Answer only with the JSON object described by the schema."""` with

```python
Answer only with the JSON object described by the schema."""

# Injected into INSTRUCTION as %(note)s when the first answers left most of the text held by no block (a docx -> md
# round trip: the markers are gone), lifting the shape rule for that one question. Empty otherwise
MALFORMED_NOTE = """

THIS DOCUMENT'S MARKDOWN IS MALFORMED: its bold and # markers are missing or unreliable, so do not
use them to decide what a title is. Ignore the rule above: a title is a line holding a block's
name (or "Enclosure N: name"), plain text or not, with the block's content beneath it. A written
table of contents still lists the enclosures by name; report each enclosure once, at the line
where its own content begins."""
```

## 2. `md_section_agent/agent.py`

### Replace the line `from models.prompts import EXAMPLE_ANSWER, EXAMPLE_DOC, INSTRUCTION, RECONCILE, RETRY  # noqa: E402` with

```python
from models.prompts import EXAMPLE_ANSWER, EXAMPLE_DOC, INSTRUCTION, MALFORMED_NOTE, RECONCILE, RETRY  # noqa: E402
```

### Add after the line `    BOLD_TITLE_INLINE,`

```python
    COVER_FIELDS,
```

### Add after the `FATAL = (...)` line (the last of the existing knobs)

```python
FALLBACK_UNPLACED_SHARE = 0.40  # this share of the non-blank lines held by no block -> ask again as malformed markdown
FALLBACK_UNPLACED_LINES = 10  # and at least this many such lines, so a short fragment never triggers it
FALLBACK_SHORT_BODY = 15  # cover, signature and ToC bodies count as held only up to this many non-blank lines
```

### In class `SectionAgent`, replace method `llm_boundaries` with

```python
    def llm_boundaries(self, lines: List[str]) -> Tuple[List[Start], str, List[str]]:
        """(starts, mode, findings). Seven steps; the first question never sees the rules' answer."""
        findings: List[str] = []
        prompt = numbered(lines)

        # 1. ask the model, blind
        try:
            result = self.structured(instruction(), prompt, BoundaryMap)
        except LlmUnavailable as error:
            if not FALLBACK_TO_REGEX:
                raise
            starts, mode = boundaries.regex_boundaries(lines)
            return starts, mode, ["LLM unavailable (%s); regex boundaries used" % error]
        findings.append(
            "LLM: %s, attempt %d, %.1fs" % (self.provider, self.last.get("attempts", 1), self.last.get("seconds", 0))
        )

        # 2. validate every answer (quote, title shape, document order); retry the failures
        placed, enclosure_lines, failed, reasons = check_map(result, lines, findings)
        titles = enclosure_titles(result, enclosure_lines, lines)
        for _ in range(RETRIES):
            if not failed:
                break
            retry = self.retry_call(result, placed, failed, reasons, lines, prompt, findings)
            if retry is None:
                break
            result, placed, enclosure_lines, failed, reasons, titles = retry

        # 3 + 4. compare with the rules; where both placed a block on different lines, one question to pick
        if RECONCILE_WITH_RULES:
            placed, enclosure_lines, titles = self.reconcile(placed, enclosure_lines, titles, lines, findings)

        # 5. blanks and stubborn failures come from the rules, if the rules found a title line
        filled: List[str] = []
        if BACKFILL_FROM_RULES:
            placed, enclosure_lines, titles, failed = backfill(
                placed, enclosure_lines, titles, failed, lines, findings, filled
            )
        for name in failed:
            findings.append("LLM: %s could not be placed; treated as not found" % name)

        # 5b. most of the text held by no block: the markdown is malformed. Ask once more, saying so, and take that
        # answer through the same checks with the title-shape rule off
        unplaced, total = unplaced_share(to_starts(placed, enclosure_lines, titles, lines), lines)
        malformed = total > 0 and unplaced / total >= FALLBACK_UNPLACED_SHARE and unplaced >= FALLBACK_UNPLACED_LINES
        if malformed:
            try:
                result = self.structured(instruction(MALFORMED_NOTE), prompt, BoundaryMap)
            except LlmUnavailable as error:
                findings.append("LLM: malformed-markdown question unavailable (%s); first answer kept" % error)
                malformed = False
            else:
                placed, enclosure_lines, failed, reasons = check_map(result, lines, findings, shaped=False)
                titles = enclosure_titles(result, enclosure_lines, lines, shaped=False)
                findings.append(
                    "LLM: %d of %d non-blank lines (%d%%) held by no block; asked again as malformed markdown: "
                    "%d block(s) placed, %d not"
                    % (unplaced, total, round(100 * unplaced / total), len(placed) + len(enclosure_lines), len(failed))
                )
                for name in failed:
                    findings.append("LLM: %s could not be placed; treated as not found" % name)

        # 6. provenance: how much came from the model, and any remaining disagreement (not for the malformed answer)
        if not malformed:
            findings.extend(provenance(placed, enclosure_lines, titles, filled, lines))

        # 7. hand over in the shared contract
        starts = to_starts(placed, enclosure_lines, titles, lines)
        mode = "heading" if any(HEADING_LINE.match(l) for l in lines) else "bold"
        return starts, mode, findings
```

### Replace function `instruction` with

```python
def instruction(note: str = "") -> str:
    """INSTRUCTION with the section list and the worked example filled in; `note` is MALFORMED_NOTE or nothing"""
    return INSTRUCTION % {
        "sections": ", ".join(SECTION_FIELDS.values()),
        "example_doc": EXAMPLE_DOC,
        "example_answer": json.dumps(EXAMPLE_ANSWER, indent=1),
        "note": note,
    }
```

### Add after function `numbered`

```python
HELD = ("section", "enclosure", "appendices", "glossary", "glossary_part", "tables", "figures")  # hold every line
SHORT = ("cover", "signature", "toc")  # held up to FALLBACK_SHORT_BODY lines: on a broken document they swallow all


def unplaced_share(starts: List[Start], lines: List[str]) -> Tuple[int, int]:
    """(non-blank lines held by no section, enclosure or back-matter block, non-blank lines in all): the 40% rule."""
    starts = sorted(starts, key=lambda s: s.line)
    total = sum(1 for line in lines if line.strip())
    held = 0
    for position, start in enumerate(starts):
        following = starts[position + 1].line if position + 1 < len(starts) else len(lines)
        stop = min(start.end + 1, following) if start.end is not None else following
        count = sum(1 for line in lines[start.line : stop] if line.strip())
        kind = "signature" if start.kind == "section" and start.name == cfg.SIGNATURE_SECTION else start.kind
        if kind in HELD:
            held += count
        elif kind in SHORT:
            held += min(count, FALLBACK_SHORT_BODY)
    return total - held, total
```

### Replace function `verify` with

```python
def verify(
    where: Where,
    lines: List[str],
    findings: List[str],
    label: str,
    kind: str = "section",
    reasons: Dict[str, str] = None,
    shaped: bool = True,
) -> Optional[int]:
    """The 0-based line this Where points at, or None. The quote must begin the line (searched nearby and corrected if
    not); with `shaped` the line must also look like a title (off for the malformed-markdown answer)."""
    quote = squash(where.starts_with)
    index = where.line - 1
    found = None
    if 0 <= index < len(lines) and quote and squash(lines[index]).startswith(quote):
        found = index
    else:
        window = SEARCH_WINDOW
        candidates = [
            i
            for i in range(max(0, index - window), min(len(lines), index + window + 1))
            if quote and squash(lines[i]).startswith(quote)
        ]
        if len(candidates) == 1:
            findings.append(
                "LLM: %s reported at line %d, quote found at line %d; corrected"
                % (label, where.line, candidates[0] + 1)
            )
            found = candidates[0]
    if found is None:
        if reasons is not None:
            reasons[label] = "the quoted text does not begin line %d" % where.line
        return None
    if shaped and not title_shaped(kind, lines[found]):
        findings.append(
            "LLM: %s reported at line %d, but that line is plain text, not " "a title; rejected" % (label, found + 1)
        )
        if reasons is not None:
            reasons[label] = (
                "line %d is plain text, not a bold or # title line; a written "
                "table of contents entry is not a title" % (found + 1)
            )
        return None
    return found
```

### Replace function `check_map` with

```python
def check_map(
    result, lines: List[str], findings: List[str], shaped: bool = True
) -> Tuple[Dict[str, int], List[int], List[str], Dict[str, str]]:
    """Validate every field: quote, title shape (unless `shaped` is off), document order, duplicates. Returns (placed,
    enclosure_lines, failed, reasons)."""
    placed: Dict[str, int] = {}
    failed: List[str] = []
    reasons: Dict[str, str] = {}
    for name in list(SECTION_FIELDS) + ["cover_" + k for k in COVER_KEYS] + list(FIXED_KINDS):
        where = getattr(result, name)
        if where is None:
            continue
        index = verify(where, lines, findings, name, kind_of(name), reasons, shaped)
        if index is None:
            failed.append(name)
        else:
            placed[name] = index

    enclosures: List[int] = []
    titles_seen: Dict[str, int] = {}
    titles_seen_titles: Dict[int, str] = {}
    for entry in result.enclosures:
        label = "enclosure:%s" % entry.title
        index = verify(entry, lines, findings, "enclosure %r" % entry.title, "enclosure", reasons, shaped)
        if index is None:
            failed.append(label)
            continue
        key = normalize(entry.title)
        if key in titles_seen:
            findings.append(
                "LLM: enclosure %r reported twice (lines %d and %d); the "
                "second dropped" % (entry.title, titles_seen[key] + 1, index + 1)
            )
            continue
        titles_seen[key] = index
        titles_seen_titles[index] = entry.title
        enclosures.append(index)

    # one shape: cover -> sections (each once) -> SIGNATURE BLOCK -> [ToC] -> enclosures -> back matter
    # after the signature nothing is a section; "See Enclosure 2" points at an enclosure, never a second section
    signature = placed.get("signature")
    toc = placed.get("table_of_contents")
    back_lines = [placed[n] for n in placed if n in FIXED_KINDS and n not in ("signature", "table_of_contents")]
    boundary = "the signature block (line %d)" % (signature + 1) if signature is not None else "the enclosures"

    def reject_section(name, reason):
        findings.append("LLM: %s reported at line %d, after %s; rejected" % (name, placed[name] + 1, boundary))
        reasons[name] = reason
        failed.append(name)
        del placed[name]

    def late_section_reason(index):
        title = ENCLOSURE_TITLE.match(plain_title(lines[index]))
        if title:
            return (
                "line %d is the title of Enclosure %s (%s), after %s. The section is the one "
                "before the signature; if it says 'See Enclosure %s' this is the enclosure it "
                "refers to, not the section"
                % (index + 1, title.group(1) or "?", title.group(2).strip(), boundary, title.group(1) or "?")
            )
        return "sections end at %s; line %d is after it and belongs to an enclosure" % (boundary, index + 1)

    # 1. sections cannot follow the hard marks: signature, written ToC, back matter
    marks_end = min(
        [x for x in (signature, toc, min(back_lines) if back_lines else None) if x is not None] or [len(lines)]
    )
    for name in [n for n in list(placed) if n in SECTION_FIELDS and placed[n] >= marks_end]:
        reject_section(name, late_section_reason(placed[name]))

    # 2. enclosures cannot sit inside the sections (before the last one, or before the signature)
    section_lines = [i for n, i in placed.items() if n in SECTION_FIELDS]
    last_section = max(section_lines) if section_lines else -1
    kept: List[int] = []
    for index in enclosures:
        if index <= last_section or (signature is not None and index < signature):
            owner = next((SECTION_FIELDS[n] for n, i in placed.items() if i == index and n in SECTION_FIELDS), None)
            label = "enclosure:%s" % titles_seen_titles.get(index, "?")
            reasons[label] = "line %d is %s, before %s; enclosures come after the signature block" % (
                index + 1,
                "the %s section" % owner if owner else "inside the sections",
                boundary,
            )
            findings.append("LLM: enclosure at line %d sits inside the sections; rejected" % (index + 1))
            failed.append(label)
        else:
            kept.append(index)
    enclosures = kept

    # 3. sections cannot follow the first remaining enclosure
    if enclosures:
        first_enclosure = min(enclosures)
        for name in [n for n in list(placed) if n in SECTION_FIELDS and placed[n] > first_enclosure]:
            reject_section(name, late_section_reason(placed[name]))

    last_enclosure = max(enclosures) if enclosures else max(last_section, signature if signature is not None else -1)
    for name in [n for n in list(placed) if n in FIXED_KINDS and n not in ("signature", "table_of_contents")]:
        if placed[name] < last_enclosure:
            findings.append(
                "LLM: %s reported at line %d, before the enclosures end; rejected" % (name, placed[name] + 1)
            )
            reasons[name] = "back matter comes after the enclosures; line %d is before them" % (placed[name] + 1)
            failed.append(name)
            del placed[name]

    # two blocks on one line: keep the first in field order, fail the other
    seen: Dict[int, str] = {}
    for name in list(placed):
        if placed[name] in seen:
            findings.append(
                "LLM: %s and %s both reported at line %d; %s dropped"
                % (seen[placed[name]], name, placed[name] + 1, name)
            )
            reasons[name] = "line %d already holds %s" % (placed[name] + 1, seen[placed[name]])
            failed.append(name)
            del placed[name]
        else:
            seen[placed[name]] = name
    return placed, enclosures, failed, reasons
```

### Replace function `enclosure_titles` with

```python
def enclosure_titles(result, enclosure_lines, lines, shaped: bool = True) -> Dict[int, str]:
    """line index -> title as the model gave it, for the entries that were kept"""
    titles = {}
    for entry in result.enclosures:
        index = verify(entry, lines, [], "", "enclosure", None, shaped)
        if index is not None and index in enclosure_lines and index not in titles:
            titles[index] = entry.title
    return titles
```

### Replace function `title_inline` with (the regex above it comes along)

```python
# a plain title with its body on the same line, accepted on a malformed document: "OPR: DLA J6", "4. DEFINITIONS: See"
PLAIN_TITLE = re.compile(r"^\s*(?:\d+[.)]\s+)?(?P<name>[^:.]{1,60}?)\s*[:.]\s+(?P<rest>\S.*)$")


def title_inline(line: str) -> str:
    """Body text sitting on the title line, after the title"""
    inline = BOLD_TITLE_INLINE.match(line.lstrip())
    if inline:
        return inline.group("rest").strip()
    heading = HEADING_LINE.match(line)
    if heading and ":" in heading.group(2):  # "# DEFINITIONS: See Glossary."
        head, _, rest = heading.group(2).partition(":")
        return rest.strip() if normalize(head) in SECTION_ALIASES else ""
    field = BOLD_FIELD_LINE.match(line.strip())
    if field or title_shaped("section", line):
        return field.group(2).strip() if field else ""
    plain = PLAIN_TITLE.match(line.strip())  # only an accepted plain title of a malformed document gets here
    name = normalize(plain.group("name")) if plain else ""
    known = plain and (name in SECTION_ALIASES or name in COVER_FIELDS)
    return plain.group("rest").strip() if known else ""
```

## Verify

    python run_all.py --no-live                       # ALL GOOD: 46 + 49, every formatted input byte-identical
    python main.py stripped.md out.docx --title "SOP 9999.92" --template SOP   # a docx -> md document, with a key

