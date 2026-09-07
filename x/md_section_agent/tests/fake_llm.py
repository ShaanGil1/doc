"""A fake backend for llm.configure(backend=...).

It answers the boundary question truthfully by running the regex provider on
the numbered prompt, then applies the corruptions it was built with. That
makes it an oracle for "the llm path must equal the regex path", and a way to
exercise validation and retry without a network."""

import re
from typing import Dict, List
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent")]
INPUTS = ROOT / "md_to_docx" / "tests"

import boundaries  # noqa: E402
from models.boundary_map import field_name  # noqa: E402


def first_words(line: str, count: int = 6) -> str:
    words = line.strip().split()
    return " ".join(words[:count])


def truthful_map(lines: List[str]) -> dict:
    starts, mode = boundaries.regex_boundaries(lines)
    out: Dict[str, object] = {"enclosures": []}
    for s in starts:
        where = {"line": s.line + 1, "starts_with": first_words(lines[s.line])}
        if s.kind == "cover":
            out.setdefault("cover_" + s.name, where)
        elif s.kind == "section" and s.name == "SIGNATURE BLOCK":
            out.setdefault("signature", where)
        elif s.kind == "section" and s.matched:
            out.setdefault(field_name(s.name), where)  # a model reports one; first wins, as regex does
        elif s.kind == "signature":
            out["signature"] = where
        elif s.kind == "toc":
            out["table_of_contents"] = where
        elif s.kind == "enclosure":
            out["enclosures"].append(dict(where, title=s.name))
        elif s.kind == "glossary_part":
            key = (
                "glossary_part_abbreviations"
                if re.search(r"ABBREV|ACRONYM", s.name.upper())
                else "glossary_part_definitions"
            )
            out[key] = where
        else:
            out[s.kind] = where
    return out


RECONCILE_BLOCK = re.compile(
    r"BLOCK (\S+)\n  candidate A \(your answer\), around line (\d+):\n(.*?)\n  candidate B \(the rules\), around line (\d+):\n(.*?)(?=\n\nBLOCK |\n\nAnswer with)",
    re.S,
)


class FakeModel:
    """corruptions: shift=[fields], badquote=[fields], stubborn=[fields],
    outofrange=[fields], drop=[fields], duplicate=(field_a, field_b),
    toc_as_enclosures=True (report the written table of contents' plain
    lines as extra enclosures and forget the ToC itself, as a small model
    did), section_on_body_line=field (point a section at an "a." body line)"""

    def __init__(self, **corruptions):
        self.c = corruptions
        self.calls = 0
        self.prompts = []

    def reconcile_answer(self, instruction: str) -> dict:
        """pick the rules' candidate, the model's, or neither, per reconcile_pick"""
        choice = self.c.get("reconcile_pick", "rules")
        picks = []
        for label, a_line, a_text, b_line, b_text in RECONCILE_BLOCK.findall(instruction):
            line, block = (b_line, b_text) if choice == "rules" else (a_line, a_text)
            marked = next(l for l in block.splitlines() if l.startswith(">"))
            words = marked.split("| ", 1)[1]
            if choice == "neither":
                picks.append({"field": label, "line": 0, "starts_with": ""})
            else:
                picks.append({"field": label, "line": int(line), "starts_with": first_words(words)})
        return {"picks": picks}

    def __call__(self, instruction: str, prompt: str, schema) -> dict:
        self.calls += 1
        self.prompts.append(instruction)
        if "You answered blind" in instruction:  # the reconcile call
            return self.reconcile_answer(instruction)
        lines = [l.split("| ", 1)[1] if "| " in l else "" for l in prompt.splitlines()]
        answer = truthful_map(lines)
        retry = "previous answer was checked" in instruction
        for name in self.c.get("drop", []):
            answer[name] = None
        if not retry:
            for name in self.c.get("shift", []):
                if answer.get(name):
                    answer[name]["line"] += 1
            for name in self.c.get("badquote", []):
                if answer.get(name):
                    answer[name]["starts_with"] = "zzz not on this line"
            for name in self.c.get("outofrange", []):
                if answer.get(name):
                    answer[name]["line"] = len(lines) + 40
            if "duplicate" in self.c:
                a, b = self.c["duplicate"]
                if answer.get(a) and answer.get(b):
                    answer[b] = dict(answer[a])
        for name in self.c.get("stubborn", []):
            if answer.get(name):
                answer[name]["starts_with"] = "still wrong"
        if self.c.get("toc_as_enclosures") and not retry:
            answer["table_of_contents"] = None
            for i, line in enumerate(lines):
                m = re.match(r"^ENCLOSURE (\d+): (.+?)\s*$", line.strip())
                if m and "**" not in line:
                    answer["enclosures"].append({"line": i + 1, "starts_with": first_words(line), "title": m.group(2)})
            answer["enclosures"].sort(key=lambda e: e["line"])
        if self.c.get("glossary_on_part_line") and not retry:
            answer["glossary"] = dict(answer["glossary_part_abbreviations"])
            answer["glossary_part_abbreviations"] = None
        name = self.c.get("section_on_body_line")
        if name and not retry and answer.get(name):
            i = answer[name]["line"]  # the line after the title: an "a." item
            answer[name] = {"line": i + 1, "starts_with": first_words(lines[i])}
        # the schema has every field; anything missing is None
        for field in schema.model_fields:
            answer.setdefault(field, [] if field == "enclosures" else None)
        return answer
