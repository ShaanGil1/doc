# Search API: GET + POST with Shared Pydantic Models

Notes on building a search endpoint that accepts both GET and POST, backed by the same pydantic models and pipeline.

## The core idea

POST is easy: the body is JSON, FastAPI parses it straight into a pydantic model.

GET is annoying: there's no body, so everything lives in the URL as flat key/value strings. You can't naturally express nested structures like `conditions: [{field, op, value}, ...]` as query params, so you need a translator that converts query params into the same pydantic model POST produces.

Once both verbs end up with the same `SearchQuery` object, the downstream pipeline doesn't know or care which was used.

## Pydantic models

```python
from typing import Any, Literal
from pydantic import BaseModel, Field

OpLiteral = Literal[
    # scalar comparisons
    "eq", "neq", "lt", "lte", "gt", "gte",
    # text
    "like", "ilike",
    # list membership
    "in", "not_in",
    # full-text search (tsvector fields only)
    "matches",
    # array field ops
    "contains_any", "contains_all", "contains_none", "is_empty", "not_empty",
]


class SearchCondition(BaseModel):
    """A single filter predicate applied to one field."""
    field: str = Field(
        description="The field name to filter on (e.g. 'fiscal_year', 'document_type')."
    )
    op: OpLiteral = Field(
        default="eq",
        description=(
            "The comparison operator. Defaults to 'eq'. "
            "Use 'in'/'not_in' for list membership, "
            "'contains_any'/'contains_all'/'contains_none' for array fields, "
            "'matches' for full-text search fields."
        ),
    )
    value: Any = Field(
        default=None,
        description=(
            "The value to compare against. "
            "Pass a list for 'in', 'not_in', and array ops. "
            "Omit entirely for 'is_empty' / 'not_empty'."
        ),
    )
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "fiscal_year", "op": "gte", "value": 2020},
                {"field": "document_type", "op": "eq", "value": "report"},
                {"field": "entities", "op": "contains_any", "value": ["epa", "noaa"]},
            ]
        }
    }


class SearchQuery(BaseModel):
    """
    Request body for all POST /search endpoints.

    Pass `conditions` to filter rows, `return_cols` to select which columns
    come back, and `limit`/`offset` to paginate.
    """
    conditions: list[SearchCondition] = Field(
        default_factory=list,
        description="List of filter conditions -- all are ANDed together. Pass an empty list to return everything.",
    )
    return_cols: list[str] | None = Field(
        default=None,
        description="Columns to include in each result row. Defaults to the table's default column set if omitted.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="Max rows to return. Defaults to 20, max 1000.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of rows to skip for pagination.",
    )
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conditions": [
                        {"field": "fiscal_year", "op": "gte", "value": 2020},
                        {"field": "document_type", "op": "eq", "value": "report"},
                    ],
                    "return_cols": ["document_id", "document_name", "fiscal_year"],
                    "limit": 20,
                    "offset": 0,
                }
            ]
        }
    }


class SearchResponse(BaseModel):
    """Standard response envelope returned by all /search endpoints."""
    results: list[dict] = Field(description="The matched rows.")
    total: int = Field(description="Total number of rows matching the query (ignores limit/offset).")
    limit: int = Field(description="The limit that was applied.")
    offset: int = Field(description="The offset that was applied.")
    next_offset: int | None = Field(
        description="Pass this as `offset` in your next request to get the next page. None if you're on the last page."
    )
```

## The routes

```python
@router.get("/documents/search", response_model=SearchResponse)
def documents_get(
    query: Annotated[SearchQuery, Depends(search_query_from_get("doc_metadata"))],
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("doc_metadata", query, db)


@router.post("/documents/search", response_model=SearchResponse)
def documents_post(
    query: SearchQuery,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("doc_metadata", query, db)
```

Adding `response_model=SearchResponse` to the decorator does two things. FastAPI validates whatever `run_pipeline` returns against that schema before sending it, so if the shape is wrong you find out immediately instead of the client getting garbage. And Swagger shows the exact response structure with the field descriptions, instead of just "returns something."

## The GET parser

```python
from fastapi import Request, Depends


def search_query_from_get(table_name: str):
    """Returns a Depends-able function that parses GET query params into a SearchQuery."""
    def _parse(request: Request) -> SearchQuery:
        schema = TABLES.get(table_name)
        filter_params = []
        limit, offset, return_cols = 20, 0, None

        for key, val in request.query_params.multi_items():
            if key == "limit":
                limit = int(val)
            elif key == "offset":
                offset = int(val)
            elif key == "return_cols":
                return_cols = [c.strip() for c in val.split(",") if c.strip()]
            else:
                filter_params.append((key, val))

        raw_conditions = parse_query_params(schema, filter_params)
        return SearchQuery(
            conditions=[SearchCondition(**c) for c in raw_conditions],
            return_cols=return_cols,
            limit=limit,
            offset=offset,
        )
    return _parse
```

### Why it's a factory (function that returns a function)

`search_query_from_get("doc_metadata")` is called once at import time when the route is defined. It bakes the table name into a closure and hands back `_parse`, which is the actual dependency FastAPI runs on every request.

You need the factory pattern because `Depends(...)` wants a callable, and that callable only gets `Request` injected, it doesn't get your table name. So you close over the table name ahead of time.

If you had a second route like `/reports/search`, you'd write `Depends(search_query_from_get("reports"))` and get a separate parser with that table baked in.

### What the parser does

It pulls every query param off the URL, peels off the three meta ones (`limit`, `offset`, `return_cols`), and dumps the rest into `filter_params` as raw `(key, value)` tuples. Then `parse_query_params(schema, filter_params)` translates something like `?fiscal_year_gte=2020&document_type=report` into dicts matching `SearchCondition`. Then it builds the `SearchQuery`.

From the route's perspective, both GET and POST end up with the same `SearchQuery` object, and `run_pipeline` doesn't know or care which verb was used.

## Calling the GET

Exact syntax depends on how `parse_query_params` is implemented. Two common patterns:

Pattern A, operator baked into the key:
```
/documents/search?fiscal_year_gte=2020&document_type=report&limit=20
```

Pattern B, operator as a prefix on the value:
```
/documents/search?fiscal_year=gte:2020&document_type=report&limit=20
```

Pattern A reads nicer. Pattern B handles weird values better (what if the value itself contains an underscore).

`return_cols` is comma separated in a single param, which matches `val.split(",")`:
```
&return_cols=document_id,document_name,fiscal_year
```

For list-value ops like `in` or `contains_any`, either repeat the key (`?entities=epa&entities=noaa`, which is why `multi_items()` is used) or comma separate (`?entities=epa,noaa`).

## Things to double check

**`Annotated` import.** `Annotated[SearchQuery, Depends(...)]` is correct FastAPI syntax, just make sure `from typing import Annotated` is there.

**`multi_items()` vs `items()`.** `multi_items()` preserves duplicate keys (so `?tag=a&tag=b` gives both), `items()` would collapse them. Right choice if `parse_query_params` handles repeated keys.

**Type coercion.** GET params always come in as strings, `"2020"` not `2020`. `SearchCondition.value` is typed `Any` so pydantic won't complain, but downstream code needs to coerce types based on the schema, otherwise `fiscal_year >= "2020"` might behave oddly depending on the DB driver. Presumably `parse_query_params` handles that, worth confirming.

**Redundant unpacking.** `SearchQuery(conditions=[SearchCondition(**c) for c in raw_conditions], ...)` works, though if `raw_conditions` is already a list of dicts you could pass them directly and let pydantic construct the nested models. Same result.

## Swagger docs, the honest answer

**POST will look great.** Swagger introspects `SearchQuery`, shows every field with descriptions, renders the example from `json_schema_extra`, and gives you a "Try it out" button with prefilled JSON. Really nice.

**GET will look worse.** Because it uses `Depends` with a `Request` object inside, FastAPI can't see what query params you actually accept. It just knows there's a dependency. So in Swagger the GET shows up with no documented params, no example, nothing useful. Still works if you type the URL manually, but discoverability is bad.

Options to improve it:

1. **Quick fix:** add a docstring to the route explaining the query param format. Ugly but works.

2. **Better fix:** declare the common params explicitly as function args so Swagger sees them:

```python
def documents_get(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    return_cols: str | None = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    query = search_query_from_get("doc_metadata")(request)
    return run_pipeline("doc_metadata", query, db)
```

Now `limit`, `offset`, `return_cols` show up in Swagger properly, and filter params are still free form through the request object. You lose the clean `Depends` pattern but gain real docs.

3. **Fanciest fix:** generate a custom OpenAPI schema for the endpoint. Overkill unless this is a widely consumed API.

For an internal tool, probably fine to live with uglier GET docs and tell people "POST is the documented path, GET exists for convenience and bookmarks." The whole point of supporting both is that humans hitting the API casually use GET, and anything programmatic uses POST where the docs are good.
