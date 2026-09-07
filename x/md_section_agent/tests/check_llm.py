"""python md_section_agent/tests/check_llm.py   (from the repo root, or anywhere)

Agent checks, no network: the llm provider against a fake model that is an
oracle by default and can be made to misbehave."""

import io, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent"), str(Path(__file__).resolve().parent)]
import boundaries, agent as B, llm, template_processor as tp  # noqa: E402
from models import llm_config as settings  # noqa: E402
from fake_llm import FakeModel  # noqa: E402

HERE = ROOT / "md_to_docx" / "tests"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))


import re


def doc_xml(b):
    return re.sub(
        rb'w:id="\d+"', b'w:id="N"', zipfile.ZipFile(io.BytesIO(b)).read("word/document.xml")
    )  # bookmark ids count up per process


def starts_of(text, provider):
    lines = boundaries.preprocess(text)
    if provider == "llm":
        s, m, f = B.llm_boundaries(lines)
        return s, m
    return boundaries.regex_boundaries(lines)


inputs = {
    n: (HERE / n).read_text(encoding="utf-8")
    for n in (
        "sop_template.md",
        "edge_titles.md",
        "edge_bodies.md",
        "demo.md",
        "list_examples.md",
        "references_torn.md",
    )
}
# A fixed-field schema holds one POLICY, so a duplicated title cannot be
# reported by the model: its lines become body text of the first POLICY.
# The oracle comparison therefore uses edge_titles without the duplicate
inputs["edge_titles.md"] = inputs["edge_titles.md"].replace(
    "5. **POLICY:**\nA duplicate section title, which should be reported and not printed twice.\n", ""
)

# 1. oracle: llm path == regex path, block for block and byte for byte
llm.configure(backend=FakeModel())
for name, text in inputs.items():
    a, ma = starts_of(text, "regex")
    b, mb = starts_of(text, "llm")
    same = ma == mb and [(s.kind, s.name, s.line, s.inline, s.number, s.end) for s in a if s.matched] == [
        (s.kind, s.name, s.line, s.inline, s.number, s.end) for s in b
    ]
    check("oracle: starts identical to regex on %s" % name, same, str([x for x in zip(a, b) if x[0] != x[1]][:2]))
    ra, fa = tp.build_dlai(text, "", "T", "SOP", provider="regex")
    rb, fb = tp.build_dlai(text, "", "T", "SOP", provider="llm")
    check("oracle: document.xml identical on %s" % name, doc_xml(ra) == doc_xml(rb))

sop = inputs["sop_template.md"]
ref = doc_xml(tp.build_dlai(sop, "", "T", "SOP", provider="regex")[0])

# 1b. provenance: with the oracle, every block is the model's and none disagree with the rules
llm.configure(backend=FakeModel())
doc = boundaries.build_document(sop, provider="llm")
prov = [x for x in doc.findings if "from the model" in x]
check(
    "provenance line present: all blocks from the model, none from the rules",
    len(prov) == 1 and "0 from the rules" in prov[0] and " 0 " not in prov[0].split("from the model")[0],
    str(prov),
)
check(
    "no disagreements with the rules on the oracle answer",
    not any("disagree" in x or "rules see no" in x for x in doc.findings),
    str([x for x in doc.findings if "disagree" in x or "rules see" in x][:2]),
)
# ...and when the model forgets the ToC, the provenance says exactly one block came from the rules
llm.configure(backend=FakeModel(toc_as_enclosures=True))
doc = boundaries.build_document(sop, provider="llm")
prov = [x for x in doc.findings if "from the model" in x][0]
check("provenance names the backfilled block", "1 from the rules (table_of_contents)" in prov, prov)

# 2. off-by-one line numbers with correct quotes: corrected, identical output
llm.configure(backend=FakeModel(shift=["section_purpose", "section_procedures", "cover_subject"]))
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "shifted numbers corrected from the quote, output identical",
    doc_xml(b) == ref and sum("corrected" in x for x in f) == 3,
    str([x for x in f if "LLM" in x]),
)

# 3. wrong quotes: retry fixes them, identical output
fake = FakeModel(badquote=["section_responsibilities", "glossary"])
llm.configure(backend=fake)
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "bad quotes: one retry, then identical output",
    doc_xml(b) == ref and fake.calls == 2 and any("retried 2 block" in x for x in f),
    str([x for x in f if "LLM" in x]),
)
check(
    "retry prompt names the failed blocks and gives anchors",
    "section_responsibilities" in fake.prompts[1] and "neighbouring blocks were verified" in fake.prompts[1],
)

# 4. stubborn: still wrong after retry -> recovered from the rules; with backfill off, not found and nothing else moves
llm.configure(backend=FakeModel(badquote=["section_applicability"], stubborn=["section_applicability"]))
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "stubborn block: rules backfill it, output identical",
    doc_xml(b) == ref and any("could not place section_applicability; found by the rules" in x for x in f),
    str([x for x in f if "applicability" in x]),
)
settings.BACKFILL_FROM_RULES = False
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
doc = boundaries.build_document(sop, provider="llm")
others = {k: v is not None for k, v in doc.sections.items() if k != "APPLICABILITY"}
check(
    "stubborn block, backfill off: MISSING APPLICABILITY, every other section intact",
    doc.sections["APPLICABILITY"] is None
    and all(others[k] for k in others if k not in ("POLICY", "SIGNATURE BLOCK"))
    and any("MISSING required section: APPLICABILITY" in x for x in f)
    and any("could not be placed" in x for x in f),
    str([x for x in f if "APPLIC" in x]),
)
settings.BACKFILL_FROM_RULES = True

# 5. out-of-range line: retry fixes
llm.configure(backend=FakeModel(outofrange=["section_purpose"]))
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "out-of-range line: retried and recovered, identical output", doc_xml(b) == ref, str([x for x in f if "LLM" in x])
)

# 6. omitted field: backfilled from the rules with no retry; with backfill off, plain MISSING
fake = FakeModel(drop=["section_internal_controls"])
llm.configure(backend=fake)
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "model omits a section: no retry, rules backfill it, output identical",
    fake.calls == 1
    and doc_xml(b) == ref
    and any("omitted section_internal_controls; found by the rules" in x for x in f),
)
settings.BACKFILL_FROM_RULES = False
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "omitted section, backfill off: MISSING finding", any("MISSING required section: INTERNAL CONTROLS" in x for x in f)
)
settings.BACKFILL_FROM_RULES = True

# 7. two blocks on one line: second dropped with a finding
llm.configure(backend=FakeModel(duplicate=("section_purpose", "section_applicability")))
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check("two blocks on one line: reported, later one treated as not found", any("both reported at line" in x for x in f))

# 7b. the lite model's mistake: ToC lines reported as enclosures, ToC itself forgotten
fake = FakeModel(toc_as_enclosures=True)
llm.configure(backend=fake)
doc = boundaries.build_document(sop, provider="llm")
b, f = tp.md_to_docx(doc, "T", "SOP")
check(
    "ToC lines reported as enclosures: rejected as plain text, 5 real enclosures remain",
    len(doc.enclosures) == 5 and sum("plain text, not a title" in x for x in f) >= 5,
    str([b_.title for b_ in doc.enclosures]),
)
check(
    "forgotten ToC backfilled from the rules, output identical to regex",
    doc_xml(b) == ref and any("omitted table_of_contents; found by the rules" in x for x in f),
    str([x for x in f if "rules" in x]),
)
check(
    "retry prompt tells the model why those lines were rejected",
    fake.calls == 2 and "written table of contents entry is not a title" in fake.prompts[1],
)
settings.BACKFILL_FROM_RULES = False
doc = boundaries.build_document(sop, provider="llm")
check(
    "with backfill off the forgotten ToC stays in the text (5 enclosures, ToC lines in EXPIRATION DATE)",
    len(doc.enclosures) == 5 and any("PART II" in l for l in doc.sections["EXPIRATION DATE"].lines),
)
settings.BACKFILL_FROM_RULES = True

# 7c. a section pointed at a body line ("a. **Director...**") is rejected, then recovered on retry
llm.configure(backend=FakeModel(section_on_body_line="section_responsibilities"))
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "section reported on an 'a.' body line: rejected, retry recovers, output identical",
    doc_xml(b) == ref,
    str([x for x in f if "LLM" in x][:2]),
)


# 7d. structural order: an enclosure placed before the sections end is rejected
class Reorder(FakeModel):
    def __call__(self, instruction, prompt, schema):
        a = super().__call__(instruction, prompt, schema)
        if "previous answer" not in instruction and a["enclosures"]:
            purpose = a["section_purpose"]
            a["enclosures"].insert(
                0, {"line": purpose["line"], "starts_with": purpose["starts_with"], "title": "Bogus"}
            )
        return a


llm.configure(backend=Reorder())
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "enclosure reported inside the sections: rejected, output identical",
    doc_xml(b) == ref and any("sits inside the sections" in x for x in f),
)


# 7e. the "See Enclosure 2" case: RESPONSIBILITIES reported a second time on the enclosure's title line
class SeeEnclosure(FakeModel):
    def __call__(self, instruction, prompt, schema):
        a = super().__call__(instruction, prompt, schema)
        if "previous answer" not in instruction:
            encl = next(e for e in a["enclosures"] if e["title"].upper() == "RESPONSIBILITIES")
            a["section_responsibilities"] = {"line": encl["line"], "starts_with": encl["starts_with"]}
        return a


fake = SeeEnclosure()
llm.configure(backend=fake)
doc = boundaries.build_document(sop, provider="llm")
b, f = tp.md_to_docx(doc, "T", "SOP")
check(
    "section reported on its enclosure's title (after the signature): rejected with the See-Enclosure reason, retry recovers, output identical",
    doc_xml(b) == ref
    and any("after the signature block" in x and "section_responsibilities" in x for x in f)
    and "if it says 'See Enclosure 2' this is the enclosure it refers to" in fake.prompts[1],
    str([x for x in f if "responsib" in x.lower()][:2]),
)

# 7f. the converter itself refuses a section after the signature, whatever the provider said
lines = boundaries.preprocess(sop)
rs, mode = boundaries.regex_boundaries(lines)
sig = next(s_ for s_ in rs if s_.kind == "signature")
bogus = rs + [boundaries.Start("section", "PURPOSE", sig.line + 20)]
doc = boundaries.assemble(lines, bogus, mode)
check(
    "assemble ignores a section start after the signature block",
    doc.sections["PURPOSE"].source < sig.line and any("comes after the sections end" in x for x in doc.findings),
)

# 7g. reconcile: model put GLOSSARY on PART I's line (a valid title line, so validation passes);
#     the rules disagree; one reconcile call shows both; the model picks the rules' line
fake = FakeModel(glossary_on_part_line=True, reconcile_pick="rules")
llm.configure(backend=fake)
doc = boundaries.build_document(sop, provider="llm")
b, f = tp.md_to_docx(doc, "T", "SOP")
check(
    "disagreement -> one reconcile call, rules line chosen, output identical",
    fake.calls == 2 and doc_xml(b) == ref and any("reconciliation for glossary: rules line" in x for x in f),
    str([x for x in f if "reconcil" in x]),
)
check(
    "reconcile prompt shows both candidates with surroundings",
    "candidate A (your answer)" in fake.prompts[1]
    and "candidate B (the rules)" in fake.prompts[1]
    and ">0129|" in fake.prompts[1],
)
check(
    "the blank left by the move is backfilled afterwards",
    any("glossary_part_abbreviations; found by the rules" in x for x in f),
)
fake = FakeModel(glossary_on_part_line=True, reconcile_pick="model")
llm.configure(backend=fake)
doc = boundaries.build_document(sop, provider="llm")
check(
    "model confirms its own line: kept, reported",
    any("model line 131 confirmed over rules line 129" in x for x in doc.findings),
    str([x for x in doc.findings if "reconcil" in x]),
)
fake = FakeModel(glossary_on_part_line=True, reconcile_pick="neither")
llm.configure(backend=fake)
doc = boundaries.build_document(sop, provider="llm")
check(
    "model picks neither: model line kept, reported",
    any("no valid pick; model line 131 kept" in x for x in doc.findings),
)
fake = FakeModel()
llm.configure(backend=fake)
boundaries.build_document(sop, provider="llm")
check("no disagreements: no reconcile call made", fake.calls == 1)

# 8. no credentials, no backend: fallback to regex with a finding; or raise when told not to
llm.configure(backend=None)
real_missing = llm.missing_credentials
llm.missing_credentials = lambda: "azure: set AZURE_OPEN_AI_API_KEY"
b, f = tp.build_dlai(sop, "", "T", "SOP", provider="llm")
check(
    "no credentials: falls back to regex, says so, output identical",
    doc_xml(b) == ref and any("regex boundaries used" in x for x in f),
)
settings.FALLBACK_TO_REGEX = False
try:
    tp.build_dlai(sop, "", "T", "SOP", provider="llm")
    check("no credentials, no fallback: raises LlmUnavailable", False)
except llm.LlmUnavailable:
    check("no credentials, no fallback: raises LlmUnavailable", True)
settings.FALLBACK_TO_REGEX = True
llm.missing_credentials = real_missing

# 8b. the main.py path: agent.find_boundaries -> converter.md_to_docx
llm.configure(backend=FakeModel())
sections = B.find_boundaries(sop)
b, f = tp.md_to_docx(sections, "T", "SOP")
check("main.py path (find_boundaries -> md_to_docx) identical to build_dlai", doc_xml(b) == ref)

# 8c. the worked example in the prompt is an answer we would accept
from models.prompts import EXAMPLE_DOC, EXAMPLE_ANSWER

ex = dict(EXAMPLE_ANSWER)
[ex.setdefault(f, None) for f in B.BoundaryMap.model_fields]
ex_lines = [l.split("| ", 1)[1] if "| " in l else "" for l in EXAMPLE_DOC.splitlines()]
ex_findings = []
ex_placed, ex_encl, ex_failed, _ = B.check_map(B.BoundaryMap.model_validate(ex), ex_lines, ex_findings)
check(
    "prompt example: schema-valid, every quote begins its line, nothing fails",
    not ex_failed and not ex_findings and len(ex_encl) == 2,
)
check(
    "instruction names every required section and the example",
    all(n in B.instruction() for n in ("PURPOSE", "EXPIRATION DATE", "0018| **Enclosure 1: References**")),
)

# 8d. transient errors, backoff and fallback models (transport stubbed, no sleeping)
llm.configure(backend=None)
settings.BACKOFF_SECONDS = 0.0
real_missing = llm.missing_credentials
llm.missing_credentials = lambda: ""
real_fallbacks = settings.FALLBACK_MODELS
settings.FALLBACK_MODELS = ("fallback-a", "fallback-b")
MAIN = llm.MODEL_NAME
calls = []


def flaky(model, instruction, prompt, schema):
    calls.append(model)
    if len(calls) < 3:
        raise llm.LlmUnavailable("ServerError: 503 UNAVAILABLE high demand")
    return {"x": 1}


from pydantic import BaseModel


class T(BaseModel):
    x: int


real = llm.transport_call
llm.transport_call = flaky
check(
    "503 twice then success: same model retried, answer returned, llm.last set",
    llm.structured("i", "p", T).x == 1 and calls == [MAIN] * 3 and llm.last["attempts"] == 3,
    str(calls),
)
calls.clear()


def not_offered(model, *a):
    calls.append(model)
    if model == MAIN:
        raise llm.LlmUnavailable("ClientError: 404 NOT_FOUND model not found")
    return {"x": 2}


llm.transport_call = not_offered
check(
    "404 on the first model: next fallback model used at once",
    llm.structured("i", "p", T).x == 2 and calls == [MAIN, "fallback-a"],
    str(calls),
)
calls.clear()


def bad_key(model, *a):
    calls.append(model)
    raise llm.LlmUnavailable("ClientError: 400 API key not valid")


llm.transport_call = bad_key
try:
    llm.structured("i", "p", T)
    check("400 bad key: raised immediately, no retries, no fallback", False)
except llm.LlmUnavailable:
    check("400 bad key: raised immediately, no retries, no fallback", calls == [MAIN], str(calls))
calls.clear()


def always_down(model, *a):
    calls.append(model)
    raise llm.LlmUnavailable("ServerError: 503 UNAVAILABLE")


llm.transport_call = always_down
try:
    llm.structured("i", "p", T)
    check("every model 503: LlmUnavailable names them all", False)
except llm.LlmUnavailable as e:
    check(
        "every model 503: all models tried ATTEMPTS times, then LlmUnavailable",
        len(calls) == settings.ATTEMPTS * 3 and "every model failed" in str(e),
        str(calls),
    )
llm.transport_call = real
llm.missing_credentials = real_missing
settings.FALLBACK_MODELS = real_fallbacks

# 8e. the provider block at the top of llm.py: azure unless DB_CLOUD_PROVIDER=gcp
import os as environ

if llm.csp == "gcp":
    check(
        "gcp: model is the Gemini name, credentials are GOOGLE_API_KEY",
        llm.model_for() == llm.MODEL_NAME
        and ("GOOGLE_API_KEY" in llm.missing_credentials() or environ.environ.get("GOOGLE_API_KEY")),
    )
else:
    check(
        "azure: model is LiteLlm azure/<deployment>",
        type(llm.model).__name__ == "LiteLlm" and llm.model.model == "azure/%s" % llm.MODEL_NAME,
    )
    check(
        "azure: a fallback name becomes its own LiteLlm deployment",
        llm.model_for("other").model == "azure/other" and llm.model_for(llm.MODEL_NAME) is llm.model,
    )
    saved = {k: environ.environ.pop(k, None) for k in llm.AZURE_ENV}
    check(
        "azure with nothing set names the three missing variables",
        all(k in llm.missing_credentials() for k in llm.AZURE_ENV) and not llm.is_configured(),
    )
    for k, v in saved.items():
        if v is not None:
            environ.environ[k] = v

# 9. the ADK agent builds with the real schema and the real instruction (no network)
agent = llm.build_agent(B.instruction(), B.BoundaryMap)
check(
    "ADK Agent builds with BoundaryMap schema and the environment's model, temperature pinned",
    agent.output_schema is B.BoundaryMap
    and agent.generate_content_config.temperature == 0.0
    and agent.model is llm.model,
)
lines = boundaries.preprocess(sop)
check("numbered prompt has one label per input line", B.numbered(lines).count("\n") + 1 == len(lines))

w = max(len(n) for n, _, _ in results)
for name, ok, d in results:
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name.ljust(w), "   " + d if not ok and d else ""))
print("\n%d/%d" % (sum(ok for _, ok, _ in results), len(results)))
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
