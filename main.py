"""python main.py input.md output.docx [--title T] [--template SOP] [--provider llm|regex] [--quiet]
Findings are logged on the "md_to_docx" logger, never printed; main() returns (docx_bytes, findings)."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent"), str(ROOT)]

from agent import llm_boundaries  # noqa: E402  md_section_agent
from boundaries import assemble, preprocess, regex_boundaries  # noqa: E402  md_to_docx
from template_processor import md_to_docx  # noqa: E402  md_to_docx

log = logging.getLogger("md_to_docx")


def main(markdown_path, out_path, title="PLACEHOLDER TITLE", template=None, provider="llm"):
    markdown = Path(markdown_path).read_text(encoding="utf-8")  # 1. read
    lines = preprocess(markdown)  # 2. line endings, tabs; nothing removed

    if provider == "llm":
        starts, mode, findings = llm_boundaries(lines)  # 3a. the model (falls back to the rules)
    else:
        starts, mode = regex_boundaries(lines)  # 3b. the rules only
        findings = []

    sections = assemble(lines, starts, mode)  # 4. starts -> DlaiDocument
    docx_bytes, more = md_to_docx(sections, title, template)  # 5. render
    findings += more

    Path(out_path).write_bytes(docx_bytes)  # 6. write
    findings.insert(0, "wrote %s (%d bytes) using the %s provider" % (out_path, len(docx_bytes), provider))
    for finding in findings:  # 7. report
        log.info(finding)
    return docx_bytes, findings


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("markdown")
    ap.add_argument("output")
    ap.add_argument("--title", default="PLACEHOLDER TITLE")
    ap.add_argument("--template", default=None, help="cover document type, e.g. SOP")
    ap.add_argument("--provider", default="llm", choices=("llm", "regex"))
    ap.add_argument("--quiet", action="store_true", help="do not echo the findings to the console")
    args = ap.parse_args()
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
        for noisy in ("openai", "httpx", "httpcore"):  # the client's own retry chatter; our findings say what happened
            logging.getLogger(noisy).setLevel(logging.WARNING)
    main(args.markdown, args.output, args.title, args.template, args.provider)
