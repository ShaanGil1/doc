from __future__ import annotations
from typing import Optional
import helpers
import logic
from helpers import DocxOptions

def markdown_to_docx(
    markdown_text: str,
    options: Optional[DocxOptions] = None,
    document=None,
) -> bytes:
    """
    Convert markdown to a .docx file and return its raw bytes.
    options   page size, fonts, colours, image handling (see DocxOptions)
    document  an existing docx.Document to append into
    """
    opts = options or DocxOptions()
    # 1. clean the starting string: line endings, XML-illegal chars
    source = logic.clean_source(markdown_text, opts.strip_front_matter)
    # 2. markdown -> nested syntax tree (markdown-it-py does the parsing for us)
    tree = logic.parse_markdown(source)
    # 3. A blank document with page setup, or the starting document if it is passed in 
    document = helpers.new_document(opts) if document is None else document
    # 4. walk the tree and write every block into the document
    logic.DocxWriter(document, opts).write_document(tree)
    # 5. serialise the document to bytes and return it
    return helpers.document_to_bytes(document)


def main(argv=None) -> int:
    """python3 md_to_docx.py in.md out.docx   (reads stdin with no input file)"""
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    source = Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    target = args[1] if len(args) > 1 else "out.docx"
    Path(target).write_bytes(markdown_to_docx(source))
    print("wrote %s" % target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
