```
MARKUP = re.compile(r"[*_`~#]+")
# "## 1. Purpose" and "## 1.2) Purpose" both mean the section, not a new name
LEADING_NUMBER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
TRAILING_PUNCTUATION = re.compile(r"[\s:.\-–—;,]+$")
WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """'Summary of  Changes :' and '**SUMMARY OF CHANGES**' both become
    'SUMMARY OF CHANGES'"""
    text = MARKUP.sub("", unicodedata.normalize("NFKC", text or ""))
    text = LEADING_NUMBER.sub("", WHITESPACE.sub(" ", text).strip())
    return TRAILING_PUNCTUATION.sub("", text).upper()
```

```
# A line that is nothing but bold text, e.g. "**PURPOSE**"
BOLD_ONLY_LINE = re.compile(r"^\s*\*\*\s*(.+?)\s*\*\*\s*$")
# A labelled field, e.g. "**OPR:** J6 Logistics". Colon inside or outside
BOLD_FIELD_LINE = re.compile(r"^\s*\*\*\s*(.+?)\s*:?\s*\*\*\s*:?\s*(.*)$")

# label -> the key write_cover looks for
COVER_FIELDS = {"OPR": "opr", "SUBJECT": "subject",
                "EFFECTIVE DATE": "effective", "EFFECTIVE": "effective",
                "REFERENCES": "references"}


def split_cover(markdown_text: str) -> Tuple[str, Dict[str, str]]:
    """Pull "**OPR:** value" style lines off the top. Returns (rest, fields).

    Scanning stops at the first heading or bold-only line, so only the block
    above the body is considered. A value runs until the next line carrying
    ** or #, which lets it wrap across lines.
    """
    lines = (markdown_text or "").splitlines()
    fields: Dict[str, list] = {}
    current, cut = None, len(lines)

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or BOLD_ONLY_LINE.match(stripped):
            cut = index
            break
        match = BOLD_FIELD_LINE.match(stripped)
        if match:
            current = COVER_FIELDS.get(normalize(match.group(1)))
            if current:
                fields[current] = [match.group(2).strip()] if match.group(2).strip() else []
            continue
        if current:
            fields[current].append(stripped)

    return ("\n".join(lines[cut:]),
            {key: "\n".join(value).strip() for key, value in fields.items()})
```


```
    effective = " ".join((fields.get("effective") or "").split())
    write(document, "cover_line",
          cover["effective_pattern"] % effective if effective
          else cover["effective_text"])
```

```
    for index, (text, key) in enumerate(cover["labels"]):
        paragraph = write(document, "cover_label", text)
        value = " ".join((fields.get(key) or "").split()) if key else ""
        if value:
            # a plain run, so the label stays underlined and the value does not
            paragraph.add_run(value)
```

```
    # one reference per line or per semicolon, falling back to placeholders
    supplied = [r.strip() for r in
                fields.get("references", "").replace(";", "\n").splitlines()
                if r.strip()]
    entries = supplied or [cover["ref_pattern"] % i
                           for i in range(1, cover["ref_count"] + 1)]
```


```
    # strip the "**OPR:** value" block off the top of either input
    sections_input, cover = dlai.split_cover(sections_input)
    markdown_input, more = dlai.split_cover(markdown_input)
    cover = {**more, **cover}
```

```
    # (printed label, cover field it accepts). Trailing double space is
    # deliberate and part of the label
    "labels": (("OPR:  ", "opr"), ("Subject:  ", "subject"),
               ("References:  ", None)),
    "effective_pattern": "Effective: %s",   # used when the input supplies one
```


