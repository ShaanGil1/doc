"""python md_section_agent/tests/live_llm.py md_to_docx/tests/sop_template.md

Needs a key: pasted into md_section_agent/models/llm_config.py or GOOGLE_API_KEY.

Runs the real model once on one input and shows its work: the numbered prompt
size, every block it reported with the quote check result, the validation
findings, a side-by-side against the regex provider, then a full build with
provider="llm". Nothing is cached; each run is one or two model calls."""

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent")]
import boundaries, agent as B, llm, template_processor as tp  # noqa: E402

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)
if not llm.is_configured():
    print("no key: paste it into md_section_agent/models/llm_config.py or set GOOGLE_API_KEY")
    sys.exit(1)

text = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = boundaries.preprocess(text)
prompt = B.numbered(lines)
print(
    "provider %s, model %s | %d lines, %d chars in the prompt"
    % (llm.csp or "azure", llm.MODEL_NAME, len(lines), len(prompt))
)

t = time.time()
raw = llm.structured(B.instruction(), prompt, B.BoundaryMap)
print(
    "first call: %.1fs, answered by %s (attempt %d)\n"
    % (time.time() - t, llm.last.get("model"), llm.last.get("attempts", 1))
)

findings = []
placed, encl, failed, reasons = B.check_map(raw, lines, findings)
print("%-34s %-6s %-6s %s" % ("block", "said", "is", "quote"))
for name in [f for f in raw.model_fields if f != "enclosures"]:
    w = getattr(raw, name)
    if w is None:
        continue
    ok = placed.get(name)
    print("%-34s %-6d %-6s %s" % (name, w.line, (ok + 1) if ok is not None else "FAIL", w.starts_with[:40]))
for e in raw.enclosures:
    print("%-34s %-6d %-6s %s" % ("enclosure: " + e.title, e.line, "", e.starts_with[:40]))
print("\nvalidation:", *(["  " + f for f in findings] or ["  clean"]), sep="\n")
if failed:
    print("failed (would be retried):", failed)

print("\n== regex provider for comparison ==")
rs, mode = boundaries.regex_boundaries(lines)
ls, lmode, lf = B.llm_boundaries(lines)
key = lambda s: (s.line, s.kind, s.name)
only_regex = sorted(set(map(key, rs)) - set(map(key, ls)))
only_llm = sorted(set(map(key, ls)) - set(map(key, rs)))
print("agree on %d starts" % len(set(map(key, rs)) & set(map(key, ls))))
for k in only_regex:
    print("  regex only: line %d %s %r" % (k[0] + 1, k[1], k[2]))
for k in only_llm:
    print("  llm only:   line %d %s %r" % (k[0] + 1, k[1], k[2]))

print("\n== full build with provider='llm' ==")
data, f = tp.build_dlai(text, "", Path(sys.argv[1]).stem, None, provider="llm")
out = Path(tempfile.gettempdir()) / "live_llm.docx"
out.write_bytes(data)
print("wrote %s (%d bytes)" % (out, len(data)))
for x in f:
    print("  " + x)
