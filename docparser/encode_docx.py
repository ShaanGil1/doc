"""
encode_docx.py - Print a JSON payload for the /working-draft/docx route.

Takes a .docx, base64-encodes it, wraps it in the JSON shape the route
expects, and prints to stdout.

Usage:
    python encode_docx.py path/to/your_document.docx > payload.json
"""

import base64
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print('Usage: python encode_docx.py path/to/document.docx', file=sys.stderr)
        sys.exit(1)

    docx_path = Path(sys.argv[1])
    if not docx_path.exists():
        print(f'File not found: {docx_path}', file=sys.stderr)
        sys.exit(1)

    docx_bytes = docx_path.read_bytes()
    docx_b64 = base64.b64encode(docx_bytes).decode('ascii')
    print(json.dumps({'docx_b64': docx_b64}, indent=2))


if __name__ == '__main__':
    main()
