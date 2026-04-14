# Search API — Local Test Cases

Every case below uses this shape:

```python
from starlette.requests import Request
from search_api import run_search_get

request = Request({
    "type": "http",
    "query_string": b"...",
})
run_search_get("<table>", request, db)
```

Remember: `query_string` is **bytes**, `%` in URLs is `%25`, spaces are `+`.

---

## doc_metadata

### Scalar equality and comparison

```python
# document_type = 'report'
Request({"type": "http", "query_string": b"document_type=report"})

# fiscal_year >= 2020
Request({"type": "http", "query_string": b"fiscal_year_gte=2020"})

# fiscal_year > 2019 AND fiscal_year <= 2024
Request({"type": "http", "query_string": b"fiscal_year_gt=2019&fiscal_year_lte=2024"})

# document_type != 'draft'
Request({"type": "http", "query_string": b"document_type_neq=draft"})
```

### Text pattern matching

```python
# document_name ILIKE '%climate%'
Request({"type": "http", "query_string": b"document_name_ilike=%25climate%25"})

# document_name LIKE 'Annual%'  (case-sensitive)
Request({"type": "http", "query_string": b"document_name_like=Annual%25"})
```

### IN / NOT IN

```python
# document_type IN ('report', 'brief', 'memo')
Request({"type": "http", "query_string": b"document_type_in=report,brief,memo"})

# document_type NOT IN ('draft', 'archived')
Request({"type": "http", "query_string": b"document_type_not_in=draft,archived"})
```

### Booleans (case-insensitive)

```python
# is_latest = true
Request({"type": "http", "query_string": b"is_latest=true"})

# is_latest = true  (capital T)
Request({"type": "http", "query_string": b"is_latest=True"})

# enabled = false  (allcaps)
Request({"type": "http", "query_string": b"enabled=FALSE"})
```

### Dates

```python
# document_created between 2023-01-01 and 2024-01-01
Request({"type": "http", "query_string": b"document_created_gte=2023-01-01&document_created_lt=2024-01-01"})
```

### UUID

```python
# document_id = '12345678-...'
Request({"type": "http", "query_string": b"document_id=12345678-1234-5678-1234-567812345678"})
```

### Numeric

```python
# document_number between 100 and 200
Request({"type": "http", "query_string": b"document_number_gte=100&document_number_lt=200"})
```

### Array operations

```python
# dates_referenced && ['2023-Q1', '2023-Q2']   (overlap / any)
Request({"type": "http", "query_string": b"dates_referenced_contains_any=2023-Q1,2023-Q2"})

# dates_referenced @> ['2023', '2024']          (superset / all)
Request({"type": "http", "query_string": b"dates_referenced_contains_all=2023,2024"})

# dates_referenced is empty or NULL
Request({"type": "http", "query_string": b"dates_referenced_is_empty=true"})

# dates_referenced has at least one element
Request({"type": "http", "query_string": b"dates_referenced_not_empty=true"})

# document_synonyms has none of these values
Request({"type": "http", "query_string": b"document_synonyms_contains_none=deprecated,legacy"})
```

### Full-text search

```python
# search_tsv @@ plainto_tsquery('climate policy')
Request({"type": "http", "query_string": b"search_matches=climate+policy"})

# multi-word search
Request({"type": "http", "query_string": b"search_matches=greenhouse+gas+emissions"})
```

### Pagination and return_cols

```python
# limit 5
Request({"type": "http", "query_string": b"limit=5"})

# limit 10 offset 20
Request({"type": "http", "query_string": b"limit=10&offset=20"})

# custom return columns
Request({"type": "http", "query_string": b"return_cols=document_id,document_name,fiscal_year"})
```

### Combined / realistic

```python
# Reports from 2020+, latest only, limit 50
Request({"type": "http", "query_string": b"fiscal_year_gte=2020&document_type=report&is_latest=true&limit=50"})
```

---

## chunk_metadata

```python
# by parent document
Request({"type": "http", "query_string": b"document_id=12345678-1234-5678-1234-567812345678"})

# chunks mentioning EPA or NOAA
Request({"type": "http", "query_string": b"entities_contains_any=epa,noaa"})

# chunks mentioning BOTH EPA and NOAA
Request({"type": "http", "query_string": b"entities_contains_all=epa,noaa"})

# chunks NOT mentioning these
Request({"type": "http", "query_string": b"entities_contains_none=draft,archived"})

# chunks with no entities extracted
Request({"type": "http", "query_string": b"entities_is_empty=true"})

# chunks by key phrase
Request({"type": "http", "query_string": b"key_phrases_contains_any=climate,policy"})

# chunks from latest reports only
Request({"type": "http", "query_string": b"parent_document_type=report&is_latest=true"})

# ILIKE over content summary
Request({"type": "http", "query_string": b"content_summary_ilike=%25greenhouse%25"})

# full-text search over chunks
Request({"type": "http", "query_string": b"search_matches=emissions+reduction"})

# combined with return_cols and limit
Request({"type": "http", "query_string": b"entities_contains_any=epa&return_cols=chunk_id,document_id,content_summary&limit=25"})
```

---

## fact_table

```python
# by topic type
Request({"type": "http", "query_string": b"topic_type=policy"})

# recent topics
Request({"type": "http", "query_string": b"topic_fiscal_year_gte=2022"})

# high-confidence topics (>= 80)
Request({"type": "http", "query_string": b"topic_confidence_gte=80"})

# multiple topic types
Request({"type": "http", "query_string": b"topic_type_in=policy,regulation,guideline"})

# exclude drafts
Request({"type": "http", "query_string": b"authority_level_neq=draft"})

# date range on start/end
Request({"type": "http", "query_string": b"start_date_gte=2023-01-01&end_date_lt=2024-01-01"})

# topics referencing specific years
Request({"type": "http", "query_string": b"topic_dates_referenced_contains_any=2023,2024"})

# environmental category, latest only
Request({"type": "http", "query_string": b"category=environmental&is_latest=true"})

# big combined
Request({"type": "http", "query_string": b"topic_fiscal_year_gte=2022&topic_type_in=policy,regulation&is_latest=true&return_cols=topic_id,topic,topic_type&limit=50"})
```

---

## Error cases (should raise HTTPException)

Wrap these in try/except to see the error detail without crashing the script:

```python
from fastapi import HTTPException

try:
    run_search_get("doc_metadata", Request({
        "type": "http",
        "query_string": b"ghost_field=x",
    }), db)
except HTTPException as e:
    print(f"{e.status_code}: {e.detail}")
```

| Query string | Error |
|---|---|
| `b"ghost_field=x"` | 400: unknown field or op: 'ghost_field' |
| `b"fiscal_year_like=20%25"` | 400: op 'like' not allowed on int field 'fiscal_year' |
| `b"fiscal_year_gte=abc"` | 400: cannot coerce 'fiscal_year' to int: ... |
| `b"document_id=not-a-uuid"` | 400: cannot coerce 'document_id' to uuid: ... |
| `b"return_cols=search"` | 400: cannot return tsvector field: 'search' |
| `b"limit=notanumber"` | 400: limit must be an integer, got 'notanumber' |

---

## Full runner template

Drop this at the bottom of any script to probe quickly:

```python
import sys
sys.path.insert(0, '/path/to/search_api')
from starlette.requests import Request
from fastapi import HTTPException
from search_api import run_search_get

class FakeDB:
    def execute(self, sql, params):
        print("SQL:   ", sql)
        print("PARAMS:", params)
        class R:
            def fetchall(s): return []
            def scalar(s): return 0
        return R()

def probe(table, query_string):
    try:
        r = Request({"type": "http", "query_string": query_string})
        run_search_get(table, r, FakeDB())
    except HTTPException as e:
        print(f"ERR {e.status_code}: {e.detail}")
    print()

probe("doc_metadata", b"fiscal_year_gte=2020&document_type=report")
probe("chunk_metadata", b"entities_contains_any=epa,noaa")
probe("fact_table", b"topic_type_in=policy,regulation&is_latest=true")
```
