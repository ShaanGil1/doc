"""The section agent: find_boundaries(markdown) -> DlaiDocument. Registers itself as boundaries.PROVIDERS["llm"].
Ask blind, validate, retry failures, reconcile with the rules, backfill blanks, report provenance, convert to Start."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for extra_path in (HERE, HERE.parent / "md_to_docx"):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))

import boundaries  # md_to_docx
import config as cfg  # md_to_docx/config.py
import llm
from models import llm_config as settings
from models.boundary_map import COVER_KEYS, FIXED_KINDS, SECTION_FIELDS, BoundaryMap, Where, field_name
from models.prompts import EXAMPLE_ANSWER, EXAMPLE_DOC, INSTRUCTION, RECONCILE, RETRY
from rules import (
    BOLD_FIELD_LINE,
    BOLD_TITLE,
    BOLD_TITLE_INLINE,
    ENCLOSURE_TITLE,
    FENCE_LINE,
    HEADING_LINE,
    MARKUP,
    Start,
    DlaiDocument,
    normalize,
)


# ---------------------------------------------------------------------------
# the ask
# ---------------------------------------------------------------------------
def instruction() -> str:
    """INSTRUCTION with the section list and the worked example filled in"""
    return INSTRUCTION % {
        "sections": ", ".join(SECTION_FIELDS.values()),
        "example_doc": EXAMPLE_DOC,
        "example_answer": json.dumps(EXAMPLE_ANSWER, indent=1),
    }


def numbered(lines: List[str]) -> str:
    width = max(4, len(str(len(lines))))
    return "\n".join("%s| %s" % (str(i + 1).zfill(width), line) for i, line in enumerate(lines))


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def title_shaped(kind: str, line: str) -> bool:
    """Whether a line can start a block of this kind: bold-only, # heading, numbered bold title, field label, or
    fence."""
    text = line.strip()
    if not text:
        return False
    if HEADING_LINE.match(text):
        return True
    if kind == "signature" and FENCE_LINE.match(text):
        return True
    if kind == "cover":
        return bool(BOLD_FIELD_LINE.match(text))
    if BOLD_TITLE.match(text):
        return True
    if kind == "section":
        return bool(BOLD_TITLE_INLINE.match(text))
    return False


def verify(
    where: Where,
    lines: List[str],
    findings: List[str],
    label: str,
    kind: str = "section",
    reasons: Dict[str, str] = None,
) -> Optional[int]:
    """The 0-based line this Where points at, or None. The quote must begin the line (searched nearby and corrected if
    not)."""
    quote = squash(where.starts_with)
    index = where.line - 1
    found = None
    if 0 <= index < len(lines) and quote and squash(lines[index]).startswith(quote):
        found = index
    else:
        window = settings.SEARCH_WINDOW
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
    if not title_shaped(kind, lines[found]):
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


KIND_OF = {"signature": "signature", "table_of_contents": "toc"}


def kind_of(name: str) -> str:
    if name.startswith("cover_"):
        return "cover"
    if name in SECTION_FIELDS:
        return "section"
    return KIND_OF.get(name, "back")


def check_map(
    result, lines: List[str], findings: List[str]
) -> Tuple[Dict[str, int], List[int], List[str], Dict[str, str]]:
    """Validate every field: quote, title shape, document order, duplicates. Returns (placed, enclosure_lines, failed,
    reasons)."""
    placed: Dict[str, int] = {}
    failed: List[str] = []
    reasons: Dict[str, str] = {}
    for name in list(SECTION_FIELDS) + ["cover_" + k for k in COVER_KEYS] + list(FIXED_KINDS):
        where = getattr(result, name)
        if where is None:
            continue
        index = verify(where, lines, findings, name, kind_of(name), reasons)
        if index is None:
            failed.append(name)
        else:
            placed[name] = index

    enclosures: List[int] = []
    titles_seen: Dict[str, int] = {}
    titles_seen_titles: Dict[int, str] = {}
    for entry in result.enclosures:
        label = "enclosure:%s" % entry.title
        index = verify(entry, lines, findings, "enclosure %r" % entry.title, "enclosure", reasons)
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


# ---------------------------------------------------------------------------
# the provider
# ---------------------------------------------------------------------------
def llm_boundaries(lines: List[str]) -> Tuple[List[Start], str, List[str]]:
    """Provider entry point: (starts, mode, findings). Seven steps; the first call never sees the rules' answer."""
    findings: List[str] = []
    prompt = numbered(lines)

    # 1. ask the model, blind
    try:
        result = llm.structured(instruction(), prompt, BoundaryMap)
    except llm.LlmUnavailable as error:
        if not settings.FALLBACK_TO_REGEX:
            raise
        starts, mode = boundaries.regex_boundaries(lines)
        return starts, mode, ["LLM unavailable (%s); regex boundaries used" % error]
    if llm.last:
        findings.append("LLM: %(model)s, attempt %(attempts)d, %(seconds).1fs" % llm.last)

    # 2. validate every answer (quote, title shape, document order); retry the failures
    placed, enclosure_lines, failed, reasons = check_map(result, lines, findings)
    titles = enclosure_titles(result, enclosure_lines, lines)
    for _ in range(settings.RETRIES):
        if not failed:
            break
        retry = retry_call(result, placed, failed, reasons, lines, prompt, findings)
        if retry is None:
            break
        result, placed, enclosure_lines, failed, reasons, titles = retry

    # 3 + 4. compare with the rules; where both placed a block on different lines, one call to pick
    if settings.RECONCILE_WITH_RULES:
        placed, enclosure_lines, titles = reconcile(placed, enclosure_lines, titles, lines, findings)

    # 5. blanks and stubborn failures come from the rules, if the rules found a title line
    filled: List[str] = []
    if settings.BACKFILL_FROM_RULES:
        placed, enclosure_lines, titles, failed = backfill(
            placed, enclosure_lines, titles, failed, lines, findings, filled
        )
    for name in failed:
        findings.append("LLM: %s could not be placed; treated as not found" % name)

    # 6. provenance: how much came from the model, and any remaining disagreement
    findings.extend(provenance(placed, enclosure_lines, titles, filled, lines))

    # 7. hand over in the shared contract
    starts = to_starts(placed, enclosure_lines, titles, lines)
    mode = "heading" if any(HEADING_LINE.match(l) for l in lines) else "bold"
    return starts, mode, findings


def rule_field(start: Start) -> Optional[str]:
    """The schema field a regex Start corresponds to, or None"""
    if start.kind == "cover":
        return "cover_" + start.name
    if start.kind == "section":
        if start.name == cfg.SIGNATURE_SECTION:
            return "signature"
        return field_name(start.name) if start.matched else None
    if start.kind == "signature":
        return "signature"
    if start.kind == "toc":
        return "table_of_contents"
    if start.kind == "glossary_part":
        key = normalize(start.name)
        if any(w in key for w in cfg.GLOSSARY_COLUMNS["keywords"]):
            return "glossary_part_abbreviations"
        if any(w in key for w in cfg.GLOSSARY_DEFINITIONS["keywords"]):
            return "glossary_part_definitions"
        return None
    return start.kind if start.kind in FIXED_KINDS else None


def backfill(placed, enclosure_lines, titles, failed, lines, findings, filled=None):
    """Blanks and stubborn failures are taken from the rules when they find a title line; never overrides a placed
    block."""
    starts, _ = boundaries.regex_boundaries(lines)
    taken = set(placed.values()) | set(enclosure_lines)
    for start in starts:
        if start.line in taken:
            continue
        if start.kind == "enclosure":
            if normalize(start.name) in {normalize(t) for t in titles.values()}:
                continue
            enclosure_lines.append(start.line)
            titles[start.line] = start.name
            if filled is not None:
                filled.append("enclosure:%s" % start.name)
            findings.append("LLM missed enclosure %r; found by the rules at line %d" % (start.name, start.line + 1))
            failed = [f for f in failed if f != "enclosure:%s" % start.name]
            taken.add(start.line)
            continue
        field = rule_field(start)
        if field is None or field in placed:
            continue
        placed[field] = start.line
        taken.add(start.line)
        if filled is not None:
            filled.append(field)
        findings.append(
            "LLM %s %s; found by the rules at line %d"
            % ("could not place" if field in failed else "omitted", field, start.line + 1)
        )
        failed = [f for f in failed if f != field]
    enclosure_lines.sort()
    return placed, enclosure_lines, titles, failed


class Pick(BaseModel):
    field: str = Field(description="the block name exactly as listed")
    line: int = Field(description="the chosen line's number as printed, or 0 if neither candidate is the title")
    starts_with: str = Field(description="the first words of the chosen line, copied exactly")


class Reconciliation(BaseModel):
    picks: List[Pick] = Field(default_factory=list)


def rule_placements(lines) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Where the regex rules put each field and each enclosure title"""
    rules, _ = boundaries.regex_boundaries(lines)
    fields: Dict[str, int] = {}
    enclosures: Dict[str, int] = {}
    for start in rules:
        if start.kind == "enclosure":
            enclosures.setdefault(normalize(start.name), start.line)
        else:
            field = rule_field(start)
            if field:
                fields.setdefault(field, start.line)
    return fields, enclosures


def excerpt(lines, index, around=2) -> str:
    width = max(4, len(str(len(lines))))
    return "\n".join(
        "%s%s| %s" % (">" if i == index else " ", str(i + 1).zfill(width), lines[i])
        for i in range(max(0, index - around), min(len(lines), index + around + 1))
    )


def reconcile(placed, enclosure_lines, titles, lines, findings):
    """Where the model and the rules placed a block on different lines, one call shows both and the model picks."""
    rule_fields, rule_enclosures = rule_placements(lines)
    conflicts = []  # (label, field_or_title, model_line, rules_line)
    for name, line in placed.items():
        other = rule_fields.get(name)
        if other is not None and other != line:
            conflicts.append((name, name, line, other))
    for line in enclosure_lines:
        title = titles.get(line, "")
        other = rule_enclosures.get(normalize(title))
        if other is not None and other != line:
            conflicts.append(("enclosure:%s" % title, title, line, other))
    if not conflicts:
        return placed, enclosure_lines, titles

    text = []
    for label, _, mine, theirs in conflicts:
        text.append(
            "BLOCK %s\n  candidate A (your answer), around line %d:\n%s\n  candidate B (the rules), around line %d:\n%s"
            % (label, mine + 1, excerpt(lines, mine), theirs + 1, excerpt(lines, theirs))
        )
    try:
        answer = llm.structured(
            instruction() + "\n\n" + RECONCILE % {"conflicts": "\n\n".join(text)},
            "Pick the title line for each block listed in the instructions.",
            Reconciliation,
        )
    except llm.LlmUnavailable as error:
        findings.append("LLM: reconciliation unavailable (%s); model placements kept" % error)
        return placed, enclosure_lines, titles

    picks = {pick.field: pick for pick in answer.picks}
    for label, key, mine, theirs in conflicts:
        pick = picks.get(label)
        chosen = None
        if pick is not None and pick.line > 0:
            index = verify(
                Where(line=pick.line, starts_with=pick.starts_with),
                lines,
                [],
                label,
                "enclosure" if label.startswith("enclosure:") else kind_of(key),
            )
            if index in (mine, theirs):
                chosen = index
        if chosen is None:
            findings.append(
                "LLM reconciliation for %s: no valid pick; model line %d kept over rules line %d"
                % (label, mine + 1, theirs + 1)
            )
            continue
        if chosen == mine:
            findings.append(
                "LLM reconciliation for %s: model line %d confirmed over rules line %d" % (label, mine + 1, theirs + 1)
            )
            continue
        findings.append(
            "LLM reconciliation for %s: rules line %d chosen over model line %d" % (label, theirs + 1, mine + 1)
        )
        if label.startswith("enclosure:"):
            enclosure_lines[enclosure_lines.index(mine)] = theirs
            titles[theirs] = titles.pop(mine)
        else:
            placed[key] = theirs
    enclosure_lines.sort()
    return placed, enclosure_lines, titles


def provenance(placed, enclosure_lines, titles, filled, lines) -> List[str]:
    """ "N blocks from the model, M from the rules", then every remaining disagreement with the rules (model kept)."""
    total = len(placed) + len(enclosure_lines)
    out = [
        "LLM: %d block(s) from the model, %d from the rules%s"
        % (total - len(filled), len(filled), (" (%s)" % ", ".join(filled)) if filled else "")
    ]
    rule_lines, rule_enclosures = rule_placements(lines)
    for name, line in sorted(placed.items(), key=lambda item: item[1]):
        if name in filled:
            continue
        other = rule_lines.get(name)
        if other is None:
            out.append("LLM: %s at line %d; the rules see no title there (model kept)" % (name, line + 1))
        elif other != line:
            out.append(
                "LLM and rules disagree on %s: model line %d, rules line %d (model kept)" % (name, line + 1, other + 1)
            )
    for line in enclosure_lines:
        title = titles.get(line, "")
        if "enclosure:%s" % title in filled:
            continue
        other = rule_enclosures.get(normalize(title))
        if other is None:
            out.append(
                "LLM: enclosure %r at line %d; the rules see no enclosure there (model kept)" % (title, line + 1)
            )
        elif other != line:
            out.append(
                "LLM and rules disagree on enclosure %r: model line %d, rules line %d (model kept)"
                % (title, line + 1, other + 1)
            )
    return out


def enclosure_titles(result, enclosure_lines, lines) -> Dict[int, str]:
    """line index -> title as the model gave it, for the entries that were kept"""
    titles = {}
    for entry in result.enclosures:
        index = verify(entry, lines, [], "", "enclosure")
        if index is not None and index in enclosure_lines and index not in titles:
            titles[index] = entry.title
    return titles


def retry_call(result, placed, failed, reasons, lines, prompt, findings):
    """Ask again about the failed blocks, with their validated neighbours as
    re-placeable anchors. Everything else is frozen from the first answer."""
    order = sorted(placed.items(), key=lambda item: item[1])
    anchors = set()
    for name in failed:
        # neighbours: the nearest placed block before and after this one's
        # reported line (or, when we have no line, the two nearest overall)
        reported = None
        if name.startswith("enclosure:"):
            for entry in result.enclosures:
                if "enclosure:%s" % entry.title == name:
                    reported = entry.line - 1
        elif getattr(result, name) is not None:
            reported = getattr(result, name).line - 1
        before = [n for n, i in order if reported is None or i < reported]
        after = [n for n, i in order if reported is not None and i > reported]
        anchors.update(before[-1:] + after[:1])
    problems = "\n".join(
        "- %s: %s"
        % (
            name,
            reasons.get(name)
            or reasons.get(
                "enclosure %r" % name.split(":", 1)[1] if name.startswith("enclosure:") else name,
                "could not be verified",
            ),
        )
        for name in failed
    )
    anchor_text = (
        "\n".join(
            "- %s: line %d, %r" % (name, placed[name] + 1, lines[placed[name]][:60])
            for name in sorted(anchors, key=lambda n: placed[n])
        )
        or "- (none)"
    )
    try:
        again = llm.structured(
            instruction() + "\n\n" + RETRY % {"problems": problems, "anchors": anchor_text}, prompt, BoundaryMap
        )
    except llm.LlmUnavailable as error:
        findings.append("LLM: retry unavailable (%s)" % error)
        return None
    findings.append("LLM: retried %d block(s)" % len(failed))

    # merge: failed blocks and anchors come from the retry, the rest is frozen
    merged = result.model_copy(deep=True)
    replaceable = set(failed) | anchors
    for name in replaceable:
        if name.startswith("enclosure:"):
            continue
        setattr(merged, name, getattr(again, name))
    if any(n.startswith("enclosure:") for n in replaceable) and again.enclosures:
        merged.enclosures = again.enclosures
    findings2: List[str] = []
    placed2, enclosure_lines2, failed2, reasons2 = check_map(merged, lines, findings2)
    findings.extend(findings2)
    return merged, placed2, enclosure_lines2, failed2, reasons2, enclosure_titles(merged, enclosure_lines2, lines)


# ---------------------------------------------------------------------------
# to the shared contract
# ---------------------------------------------------------------------------
def title_inline(line: str) -> str:
    """Body text sitting on the title line, after the title"""
    inline = BOLD_TITLE_INLINE.match(line.lstrip())
    if inline:
        return inline.group("rest").strip()
    field = BOLD_FIELD_LINE.match(line.strip())
    return field.group(2).strip() if field else ""


def plain_title(line: str) -> str:
    """A title line as display text: no #, no **, no list number"""
    text = HEADING_LINE.sub(lambda m: m.group(2), line.strip())
    text = re.sub(r"^\d+[.)]\s+", "", text)
    return MARKUP.sub("", text).strip().rstrip(":").strip()


def fence_end(lines: List[str], start: int) -> Optional[int]:
    if not FENCE_LINE.match(lines[start]):
        return None
    for index in range(start + 1, len(lines)):
        if FENCE_LINE.match(lines[index]):
            return index
    return len(lines) - 1


def to_starts(
    placed: Dict[str, int], enclosure_lines: List[int], titles: Dict[int, str], lines: List[str]
) -> List[Start]:
    starts: List[Start] = []
    for name, index in placed.items():
        line = lines[index]
        if name.startswith("cover_"):
            starts.append(Start("cover", name[len("cover_") :], index, inline=title_inline(line)))
        elif name in SECTION_FIELDS:
            starts.append(Start("section", SECTION_FIELDS[name], index, inline=title_inline(line)))
        elif name == "signature":
            end = fence_end(lines, index)
            if end is not None:
                starts.append(Start("signature", cfg.SIGNATURE_SECTION, index, end=end))
            else:
                starts.append(Start("section", cfg.SIGNATURE_SECTION, index))
        elif name == "table_of_contents":
            starts.append(Start("toc", "TABLE OF CONTENTS", index))
        elif name.startswith("glossary_part_"):
            starts.append(Start("glossary_part", plain_title(line), index))
        else:  # appendices, glossary, tables, figures
            starts.append(Start(name, plain_title(line), index))
    for index in enclosure_lines:
        raw = titles.get(index) or plain_title(lines[index])
        match = ENCLOSURE_TITLE.match(raw) or ENCLOSURE_TITLE.match(plain_title(lines[index]))
        number = int(match.group(1)) if match and match.group(1) else None
        title = match.group(2).strip() if match else raw.strip()
        starts.append(Start("enclosure", title, index, number=number))
    return sorted(starts, key=lambda s: s.line)


boundaries.PROVIDERS["llm"] = llm_boundaries


def find_boundaries(markdown_text: str) -> DlaiDocument:
    """Markdown in, DlaiDocument out, using the model (with the regex fallback
    when it cannot be reached). Hand the result to template_processor.md_to_docx"""
    return boundaries.build_document(markdown_text, provider="llm")
