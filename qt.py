# Raw triple-quoted string. Paste any markdown between the r""" fences.
from md_to_docx import markdown_to_docx


md = r"""+++
title = this front matter uses +++ fences and must be stripped
+++

# Edge Cases

## Nested fences and escaped pipes

````markdown
```python
# this inner fence and its backticks must survive as text
**not bold** and | not | a | table |
```
````

| Command | Note |
| --- | --- |
| `a \| b` | a pipe escaped inside code |
| `grep -e "x"` | quotes in code |

## Ragged and single-column tables

| A | B | C |
|---|---|---|
| only one cell |
| 1 | 2 | 3 | 4 | 5 |

| Solo |
| --- |
| x |

## Reference-style link and bracketed text

A [reference link][ref] and text with [literal brackets] that is not a link.

[ref]: https://example.com/reference

## Emphasis torture

a**b**c, snug*italic*snug, and ***all*** three, plus **bold *with italic* back to bold**.

## Loose list with paragraphs, and mixed nesting

1. first item, paragraph one

   first item, paragraph two

2. second item
   - bullet under an ordered item
     1. ordered under that bullet
   - back to bullet

## Blockquote holding a list holding code

> quote intro
>
> - quoted bullet
> - another, then code:
>
> ```
> quoted code line
> ```

## Breaks, escapes, entities

line with two trailing spaces  
next line after a hard break, then a soft
break folds to a space.

Escapes: \*literal\* \_underscore\_ \# hash \\ backslash.

Entities and specials: &amp; &lt; &gt; and raw 5 < 6 & 7 > 3 "q" 'a'.

## HTML and links that should stay plain

<div class="note">raw html block kept as text</div>

Inline <b>html</b> and a<br>break.

Autolink <https://example.org/a?x=1&y=2>, bare URL https://example.com/plain, filename build.sh in prose.

## Three rules, three styles

---
***
___

Trailing text after everything.
"""

data = markdown_to_docx(md)                 # the real route call: str -> bytes
with open("out.docx", "wb") as f:           # "wb" = write bytes, no text encoding
    f.write(data)
print(f"wrote out.docx ({len(data)} bytes)")