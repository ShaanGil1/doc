"""python main.py input.md output.docx [--title T] [--template SOP] [--provider llm|regex] [--quiet]
Model from the environment (DB_CLOUD_PROVIDER, LLM_MODEL, AZURE_OPEN_AI_* / GOOGLE_API_KEY).
Findings are logged, never printed.
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "md_to_docx"), str(ROOT / "md_section_agent")]

import boundaries  # noqa: E402  md_to_docx
import template_processor as converter  # noqa: E402  md_to_docx

try:
    import agent  # noqa: E402  md_section_agent; absent until the model is wired in
except ImportError:
    agent = None

log = logging.getLogger("md_to_docx")


def main(markdown_path, out_path, title="PLACEHOLDER TITLE", template=None, provider="llm"):
    markdown = Path(markdown_path).read_text(encoding="utf-8")  # 1. read

    if provider == "llm" and agent is None:
        provider = "regex"  # the agent package is not installed; the rules do the work
    if provider == "llm":
        sections = agent.find_boundaries(markdown)  # 2a. model (falls back to the rules)
    else:
        sections = boundaries.build_document(markdown, provider=provider)  # 2b. rules only

    docx_bytes, findings = converter.md_to_docx(sections, title, template)  # 3. render

    Path(out_path).write_bytes(docx_bytes)  # 4. write
    findings.insert(0, "wrote %s (%d bytes) using the %s provider" % (out_path, len(docx_bytes), provider))
    for finding in findings:  # 5. report
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
    main(args.markdown, args.output, args.title, args.template, args.provider)
