"""
local_test.py - Stupid simple runner for the docparser pipeline.

To run:
    1. Edit the two variables below.
    2. python local_test.py

That's it. The script will:
    - parse the .docx into markdown
    - send to Gemini for section detection
    - print a summary to the terminal
    - save full sections to a .md file next to your input doc

Requirements:
    pip install langchain-google-genai pydantic python-docx

Get a free Google API key at: https://aistudio.google.com/apikey
"""

# =====================================================================
# EDIT THESE TWO LINES
# =====================================================================

DOCX_PATH = "your_document.docx"

GOOGLE_API_KEY = "paste-your-api-key-here"

# =====================================================================
# Below this line is just plumbing. You shouldn't need to edit anything.
# =====================================================================

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    # 1. Validate the input file exists
    docx_path = Path(DOCX_PATH)
    if not docx_path.exists():
        print(f'ERROR: file not found: {docx_path}')
        print(f'(working from {Path.cwd()})')
        sys.exit(1)

    # 2. Make sure the API key is set in the environment
    if not os.environ.get('GOOGLE_API_KEY'):
        if GOOGLE_API_KEY == 'paste-your-api-key-here' or not GOOGLE_API_KEY:
            print('ERROR: GOOGLE_API_KEY is not set.')
            print('Either edit the variable at the top of this file, or run:')
            print('    export GOOGLE_API_KEY=your-key-here')
            print('Get a free key at https://aistudio.google.com/apikey')
            sys.exit(1)
        os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY

    # 3. Import the package (after env var is set)
    try:
        from docparser import build_llm, run_sectioning, GEMINI_MODEL
    except ImportError as import_error:
        print(f'ERROR: missing package: {import_error}')
        print('    pip install langchain-google-genai pydantic python-docx')
        sys.exit(1)

    # 4. Run the pipeline
    print(f'Converting and sectioning: {docx_path.name}')
    print(f'(model: {GEMINI_MODEL}, takes a few seconds)')
    print()

    llm = build_llm()
    try:
        result = run_sectioning(llm, str(docx_path))
    except ValueError as size_error:
        print(f'ERROR: {size_error}')
        sys.exit(1)
    except Exception as unexpected_error:
        print(f'ERROR: unexpected failure: {unexpected_error}')
        print('(maybe a bad API key? or rate limit?)')
        sys.exit(1)

    # 5. Show terminal summary
    print_summary(result)

    # 6. Save outputs next to the input doc
    save_outputs(docx_path, result)


def print_summary(result):
    sections = result['sections']
    status_marker = 'reliable' if result['reliable'] else 'unreliable'
    print(f'[{status_marker}] found {len(sections)} sections:')
    print()
    for index, section in enumerate(sections, 1):
        word_count = len(section['content'].split())
        first_line = (section['content'].split('\n')[0] if section['content'] else '').strip()
        print(f'  {index:2d}. [{section["title"][:60]:<60}] ({word_count:>4}w)')
        if first_line:
            print(f'      {first_line[:80]}')


def save_outputs(docx_path, result):
    sections = result['sections']

    # Human-readable markdown
    output_md_path = docx_path.with_name(f'{docx_path.stem}_sections.md')
    output_lines = [
        f'# Sections: {docx_path.name}',
        '',
        f'Reliable: {result["reliable"]}  ',
        f'Section count: {len(sections)}',
        '',
        '---',
        '',
    ]
    for index, section in enumerate(sections, 1):
        output_lines.append(f'## {index}. {section["title"]}')
        output_lines.append('')
        output_lines.append(section['content'])
        output_lines.append('')
        output_lines.append('---')
        output_lines.append('')
    output_md_path.write_text('\n'.join(output_lines))

    # Raw JSON for pipeline ingest
    output_json_path = docx_path.with_name(f'{docx_path.stem}_sections.json')
    output_json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print()
    print(f'Saved:')
    print(f'  {output_md_path}    (human-readable)')
    print(f'  {output_json_path}  (for pipeline ingest)')


if __name__ == '__main__':
    main()
