from __future__ import annotations
from typing import List, Tuple
import dlai


def dlai_to_docx(
    markdown_input: str,
    sections_input: str = "",
    doc_title: str = "PLACEHOLDER TITLE",
) -> Tuple[bytes, List[str]]:
    """
    Convert two markdown strings into a DLAI .docx and return its raw bytes.

    markdown_input   the enclosures. Its shallowest heading level becomes the
                     enclosure title level and everything nests below it
    sections_input   the required sections before the ToC, matched loosely by
                     heading. Anything missing gets a placeholder
    doc_title        printed in the header and on the cover

    Returns (bytes, findings). Nothing touches the filesystem, so this is what
    a route hands straight back to the caller.
    """
    return dlai.build_dlai(markdown_input, sections_input, doc_title)


def main(argv=None) -> int:
    """python3 dlai_to_docx.py enclosures.md sections.md out.docx "TITLE" """
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    enclosures = Path(args[0]).read_text(encoding="utf-8") if args else ""
    sections = Path(args[1]).read_text(encoding="utf-8") if len(args) > 1 else ""
    target = args[2] if len(args) > 2 else "out.docx"
    title = args[3] if len(args) > 3 else "PLACEHOLDER TITLE"

    # 1. markdown -> bytes. This is the whole job; everything below is for
    #    looking at the result locally
    data, findings = dlai_to_docx(enclosures, sections, title)
    print("findings %d, bytes %d" % (len(findings), len(data)))
    # 2. bytes -> file
    Path(target).write_bytes(data)
    print("wrote %s (%d bytes)" % (target, len(data)))

    # 3. what was wrong with the input, if anything
    for line in findings:
        print("  %s" % line)

    # 4. confirm the .docx is valid for Word, not just for a PDF renderer
    problems, summary = __import__("validate").validate(target)
    print("bookmarks %d, PAGEREF targets %d, update on open %s"
          % (summary["bookmarks"], summary["pagerefs"], summary["update_on_open"]))
    for line in problems[:10]:
        print("  %s" % line)
    if not problems:
        print("OK, no schema or reference problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
