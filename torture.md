# Converter Test

## Inline formatting

Normal text with **bold**, *italic*, ***bold italic***, `inline code`, and ~~strikethrough~~.

A [simple link](https://example.com) and a [link with **bold** and `code` inside](https://example.com/x).

A bare URL that must stay plain text: https://example.com/not-a-link

Filenames in prose must stay plain: edit setup.py and README.md.

An image with no file should show its alt text: ![a sample logo](missing.png)

Escapes: \*not italic\* and \# not a heading.

Special chars: 5 < 6 & 7 > 3, "quotes" and 'apostrophes', unicode 日本語 and 🎲.

## Lists

- bullet one
- bullet two with **bold**
  - nested bullet
    - deeper still

1. first
2. second

Custom start:

7. seven
8. eight

Restarts at one:

1. alpha
2. beta

Tasks:

- [ ] not done
- [x] done

## Blockquote

> A quote with **bold**.
>
> > A nested quote.

## Code

```python
def greet(name):
    return f"hello {name}"
```

## Table

| Left | Center | Right |
|:-----|:------:|------:|
| a    | b      | 1     |
| longer cell text | c | 22 |

## Rule

---

Text after the rule.