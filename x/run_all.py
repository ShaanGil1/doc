"""python run_all.py [--no-live]
Both test suites, every input built with and without the model, and a live model run when credentials are present."""

import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent"), str(ROOT / "md_section_agent" / "tests")]
INPUTS = sorted((ROOT / "md_to_docx" / "tests").glob("*.md"))
PY = sys.executable
live = "--no-live" not in sys.argv


def banner(text):
    print("\n" + "=" * 70 + "\n" + text + "\n" + "=" * 70)


def suite(path):
    run = subprocess.run([PY, str(path)], capture_output=True, text=True)
    tail = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr.strip()[-200:]
    print("%-46s %s" % (path.relative_to(ROOT), tail))
    return run.returncode == 0


def doc_xml(data):
    return re.sub(rb'w:id="\d+"', b"", zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))


ok = True
banner("1. converter checks")
ok &= suite(ROOT / "md_to_docx" / "tests" / "check.py")
banner("2. agent checks (fake model)")
ok &= suite(ROOT / "md_section_agent" / "tests" / "check_llm.py")

import agent  # noqa: E402
import boundaries  # noqa: E402
import llm  # noqa: E402
import template_processor as converter  # noqa: E402
from fake_llm import FakeModel  # noqa: E402

banner("3. every input, deterministic provider (what main.py --provider regex does)")
regex_docs = {}
for path in INPUTS:
    text = path.read_text(encoding="utf-8")
    try:
        doc = boundaries.build_document(text, provider="regex")
        data, findings = converter.md_to_docx(doc, path.stem, "SOP")
        regex_docs[path.name] = data
        missing = sum("MISSING" in f for f in findings)
        print(
            "%-26s %6d bytes  sections %2d/11  enclosures %d  missing %d"
            % (path.name, len(data), sum(v is not None for v in doc.sections.values()), len(doc.enclosures), missing)
        )
    except Exception as error:
        print("%-26s FAILED: %s" % (path.name, error))
        ok = False

banner("4. every input, llm provider against the oracle fake (what main.py --provider llm does)")
llm.configure(backend=FakeModel())
for path in INPUTS:
    text = path.read_text(encoding="utf-8")
    if "edge_titles" in path.name:  # a fixed-field schema holds one POLICY; see docs/agent.md
        text = text.replace(
            "5. **POLICY:**\nA duplicate section title, which should be reported and not printed twice.\n", ""
        )
        ref = doc_xml(converter.md_to_docx(boundaries.build_document(text, provider="regex"), path.stem, "SOP")[0])
    else:
        ref = doc_xml(regex_docs[path.name])
    try:
        data, findings = converter.md_to_docx(agent.find_boundaries(text), path.stem, "SOP")
        same = doc_xml(data) == ref
        print("%-26s %s" % (path.name, "identical to the regex document" if same else "DIFFERS"))
        ok &= same
    except Exception as error:
        print("%-26s FAILED: %s" % (path.name, error))
        ok = False
llm.configure(backend=None)

banner("5. live model run (SOP)")
if not live:
    print("skipped (--no-live)")
elif not llm.is_configured():
    print("skipped: no key (paste it into md_section_agent/models/llm_config.py or set GOOGLE_API_KEY)")
else:
    text = (ROOT / "md_to_docx" / "tests" / "sop_template.md").read_text()
    lines = boundaries.preprocess(text)
    try:
        starts, mode, findings = agent.llm_boundaries(lines)
        served = [f for f in findings if f.startswith("LLM:") and " via " in f]
        if any("regex boundaries used" in f for f in findings):
            print("model could not be reached:", [f for f in findings if "unavailable" in f][0][:200])
        else:
            print(served[0] if served else "answered")
            for f in findings:
                if f.startswith("LLM") and " via " not in f:
                    print("  " + f)
            rs, _ = boundaries.regex_boundaries(lines)
            key = lambda s: (s.line, s.kind, s.name)
            agree = set(map(key, rs)) & set(map(key, starts))
            print("  agrees with the regex provider on %d of %d blocks" % (len(agree), len(rs)))
            for k in sorted(set(map(key, rs)) - set(map(key, starts))):
                print("  regex only: line %d %s %r" % (k[0] + 1, k[1], k[2]))
            for k in sorted(set(map(key, starts)) - set(map(key, rs))):
                print("  model only: line %d %s %r" % (k[0] + 1, k[1], k[2]))
            data, findings = converter.md_to_docx(boundaries.assemble(lines, starts, mode), "SOP 9999.92", "SOP")
            (ROOT / "output_live.docx").write_bytes(data)
            print("  wrote output_live.docx (%d bytes)" % len(data))
    except Exception as error:
        print("live run failed:", error)

banner("RESULT: %s" % ("ALL GOOD" if ok else "PROBLEMS ABOVE"))
sys.exit(0 if ok else 1)
