"""
Search API over doc_metadata, chunk_metadata, and fact_table.

GET (recommended):
    /documents/search?fiscal_year_gte=2020&document_type=report&limit=20

POST (escape hatch for queries that don't fit in a URL):
    {
        "conditions": [
            {"field": "fiscal_year", "op": "gte", "value": 2020},
            {"field": "document_type", "op": "eq", "value": "report"}
        ],
        "return_cols": ["document_id", "document_name"],
        "limit": 20,
        "offset": 0
    }

Filter syntax (GET):
    ?document_type=report              eq is the default
    ?fiscal_year_gte=2020              op via _suffix
    ?document_type_in=report,brief     comma-separated list
    ?entities_contains_any=epa,noaa    array op
    ?search_matches=climate+policy     full-text search

Reserved query params: limit, offset, return_cols
"""

from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request


# ---- operators ------------------------------------------------------------

SCALAR_OPS = {
    "eq": "=", "neq": "!=",
    "lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
    "like": "LIKE", "ilike": "ILIKE",
}

ARRAY_OPS = {"eq", "contains_any", "contains_all", "contains_none", "is_empty", "not_empty"}

ALLOWED_OPS = {
    "uuid":     {"eq", "neq", "in", "not_in"},
    "text":     {"eq", "neq", "in", "not_in", "like", "ilike"},
    "int":      {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
    "numeric":  {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
    "date":     {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
    "bool":     {"eq"},
    "tsvector": {"matches"},
    "array":    ARRAY_OPS,
}

LIST_OPS = {"in", "not_in", "contains_any", "contains_all", "contains_none"}
NO_VALUE_OPS = {"is_empty", "not_empty"}

# Longest first so "entities_contains_any" parses as field=entities, op=contains_any
# and not field=entities_contains, op=any.
KNOWN_OPS = sorted(
    SCALAR_OPS.keys() | {"in", "not_in", "matches"} | ARRAY_OPS,
    key=len, reverse=True,
)


# ---- table registry -------------------------------------------------------

TABLES = {
    "doc_metadata": {
        "table": "doc_metadata",
        "fields": {
            "document_id":      "uuid",
            "document_name":    "text",
            "document_number":  "numeric",
            "document_type":    "text",
            "fiscal_year":      "int",
            "file_name":        "text",
            "document_summary": "text",
            "document_created": "date",
            "dates_referenced": "array",
            "document_synonyms":"array",
            "version":          "text",
            "is_latest":        "bool",
            "enabled":          "bool",
            "search":           "tsvector",
        },
        "default_cols": ["document_id", "document_name", "document_type", "fiscal_year"],
        "tsvector_col": "search_tsv",
    },
    "chunk_metadata": {
        "table": "chunk_metadata",
        "fields": {
            "chunk_id":             "uuid",
            "document_id":          "uuid",
            "file_name":            "text",
            "document_name":        "text",
            "content_summary":      "text",
            "version":              "text",
            "is_latest":            "bool",
            "enabled":              "bool",
            "parent_document_type": "text",
            "entities":             "array",
            "key_phrases":          "array",
            "pages":                "array",
            "tables":               "array",
            "images":               "array",
            "search":               "tsvector",
        },
        "default_cols": ["chunk_id", "document_id", "document_name", "content_summary"],
        "tsvector_col": "search_tsv",
    },
    "fact_table": {
        "table": "fact_table",
        "fields": {
            "topic_id":               "uuid",
            "document_id":            "uuid",
            "chunk_id":               "uuid",
            "topic":                  "text",
            "topic_type":             "text",
            "key_information":        "text",
            "topic_fiscal_year":      "int",
            "topic_confidence":       "int",
            "topic_dates_referenced": "array",
            "authority_level":        "text",
            "document_version":       "text",
            "is_latest":              "bool",
            "start_date":             "date",
            "end_date":               "date",
            "category":               "text",
        },
        "default_cols": ["topic_id", "document_id", "topic", "topic_type", "topic_fiscal_year"],
        "tsvector_col": None,
    },
}


# ---- parse ----------------------------------------------------------------

def split_key(key, schema):
    """Turn a query-param key into (field, op). Default op is eq."""
    if key in schema["fields"]:
        return key, "eq"
    for op in KNOWN_OPS:
        suffix = "_" + op
        if key.endswith(suffix):
            field = key[: -len(suffix)]
            if field in schema["fields"]:
                return field, op
    raise HTTPException(400, f"unknown field or op: {key!r}")


def parse_query_params(schema, params):
    """params is an iterable of (key, value) string pairs, reserved names already stripped."""
    conditions = []
    for key, raw in params:
        field, op = split_key(key, schema)
        ftype = schema["fields"][field]

        if op in NO_VALUE_OPS:
            value = None
        elif op in LIST_OPS or (op == "eq" and ftype == "array"):
            value = [v for v in raw.split(",") if v]
        else:
            value = raw

        conditions.append({"field": field, "op": op, "value": value})
    return conditions


def parse_json_body(body):
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")

    raw = body.get("conditions", [])
    if not isinstance(raw, list):
        raise HTTPException(400, "conditions must be a list")

    conditions = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not {"field", "op"} <= item.keys():
            raise HTTPException(400, f"conditions[{i}] needs at least 'field' and 'op'")
        conditions.append({
            "field": item["field"],
            "op": item["op"],
            "value": item.get("value"),
        })

    return_cols = body.get("return_cols")
    if return_cols is not None and not (
        isinstance(return_cols, list) and all(isinstance(c, str) for c in return_cols)
    ):
        raise HTTPException(400, "return_cols must be a list of strings")

    limit = body.get("limit", 20)
    offset = body.get("offset", 0)
    if not (isinstance(limit, int) and isinstance(offset, int)):
        raise HTTPException(400, "limit and offset must be integers")

    return conditions, return_cols, limit, offset


# ---- validate + coerce ----------------------------------------------------

def coerce_scalar(value, ftype, field):
    try:
        if ftype == "uuid":
            return str(UUID(str(value)))
        if ftype == "int":
            return int(value)
        if ftype == "numeric":
            return float(value)
        if ftype == "date":
            return datetime.fromisoformat(str(value)).date()
        if ftype == "bool":
            if isinstance(value, bool):
                return value
            v = str(value).lower()
            if v == "true":
                return True
            if v == "false":
                return False
            raise ValueError("expected 'true' or 'false'")
        return str(value)  # text, tsvector
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"cannot coerce {field!r} to {ftype}: {e}")


def validate_and_coerce(schema, conditions):
    """One pass: check field+op, then cast the value to the right Python type."""
    for c in conditions:
        field, op, val = c["field"], c["op"], c["value"]

        if field not in schema["fields"]:
            raise HTTPException(400, f"unknown field: {field!r}")
        ftype = schema["fields"][field]
        if op not in ALLOWED_OPS[ftype]:
            raise HTTPException(400, f"op {op!r} not allowed on {ftype} field {field!r}")

        if op in NO_VALUE_OPS:
            c["value"] = None
        elif op in LIST_OPS:
            if not isinstance(val, list) or not val:
                raise HTTPException(400, f"op {op!r} on {field!r} needs a non-empty list")
            # in/not_in target scalar fields and need per-element coercion;
            # array contains_* take the list as-is.
            if op in ("in", "not_in"):
                c["value"] = [coerce_scalar(v, ftype, field) for v in val]
            else:
                c["value"] = val
        elif ftype == "array" and op == "eq":
            if not isinstance(val, list):
                raise HTTPException(400, f"eq on array {field!r} needs a list value")
            c["value"] = val
        else:
            c["value"] = coerce_scalar(val, ftype, field)

    return conditions


def resolve_return_cols(schema, cols):
    if cols is None:
        return list(schema["default_cols"])
    for col in cols:
        if col not in schema["fields"]:
            raise HTTPException(400, f"unknown return col: {col!r}")
        if schema["fields"][col] == "tsvector":
            raise HTTPException(400, f"cannot return tsvector field: {col!r}")
    return cols


# ---- build SQL ------------------------------------------------------------

def build_where(schema, conditions):
    fragments, params = [], []

    for c in conditions:
        field, op, val = c["field"], c["op"], c["value"]
        ftype = schema["fields"][field]
        col = f'"{field}"'

        if ftype == "tsvector":
            fragments.append(f'"{schema["tsvector_col"]}" @@ plainto_tsquery(%s)')
            params.append(val)

        elif ftype == "array":
            if op == "is_empty":
                fragments.append(f"(cardinality({col}) = 0 OR {col} IS NULL)")
            elif op == "not_empty":
                fragments.append(f"cardinality({col}) > 0")
            elif op == "contains_all":
                fragments.append(f"{col} @> %s")
                params.append(val)
            elif op == "contains_any":
                fragments.append(f"{col} && %s")
                params.append(val)
            elif op == "contains_none":
                fragments.append(f"NOT ({col} && %s)")
                params.append(val)
            elif op == "eq":
                fragments.append(f"{col} = %s")
                params.append(val)

        elif op in ("in", "not_in"):
            placeholders = ", ".join(["%s"] * len(val))
            keyword = "IN" if op == "in" else "NOT IN"
            fragments.append(f"{col} {keyword} ({placeholders})")
            params.extend(val)

        else:
            fragments.append(f"{col} {SCALAR_OPS[op]} %s")
            params.append(val)

    return fragments, params


def build_sql(schema, conditions, cols, limit, offset):
    fragments, where_params = build_where(schema, conditions)
    where_sql = f"WHERE {' AND '.join(fragments)}" if fragments else ""
    select_sql = ", ".join(f'"{c}"' for c in cols)
    table = f'"{schema["table"]}"'

    data_sql = f"SELECT {select_sql} FROM {table} {where_sql} LIMIT %s OFFSET %s".strip()
    count_sql = f"SELECT COUNT(*) FROM {table} {where_sql}".strip()
    return data_sql, [*where_params, limit, offset], count_sql, where_params


# ---- pipeline -------------------------------------------------------------

def run_pipeline(table_name, conditions, return_cols, limit, offset, db):
    schema = TABLES.get(table_name)
    if not schema:
        raise HTTPException(404, f"unknown table {table_name!r}")

    conditions = validate_and_coerce(schema, conditions)
    cols = resolve_return_cols(schema, return_cols)
    data_sql, data_params, count_sql, count_params = build_sql(
        schema, conditions, cols, limit, offset
    )

    try:
        rows = db.execute(data_sql, data_params).fetchall()
        total = db.execute(count_sql, count_params).scalar() or 0
    except Exception as e:
        raise HTTPException(500, f"db error: {type(e).__name__}: {e}")

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None,
    }


def run_search_get(table_name, request, db):
    schema = TABLES.get(table_name)
    if not schema:
        raise HTTPException(404, f"unknown table {table_name!r}")

    filter_params = []
    limit, offset, return_cols = 20, 0, None

    for key, val in request.query_params.multi_items():
        if key == "limit":
            try:
                limit = int(val)
            except ValueError:
                raise HTTPException(400, f"limit must be an integer, got {val!r}")
        elif key == "offset":
            try:
                offset = int(val)
            except ValueError:
                raise HTTPException(400, f"offset must be an integer, got {val!r}")
        elif key == "return_cols":
            return_cols = [c.strip() for c in val.split(",") if c.strip()]
        else:
            filter_params.append((key, val))

    conditions = parse_query_params(schema, filter_params)
    return run_pipeline(table_name, conditions, return_cols, limit, offset, db)


def run_search_post(table_name, body, db):
    conditions, return_cols, limit, offset = parse_json_body(body)
    return run_pipeline(table_name, conditions, return_cols, limit, offset, db)


# ---- routes ---------------------------------------------------------------

def get_db():
    raise NotImplementedError("wire this up to your db session")

def get_current_user():
    raise NotImplementedError("wire this up to your auth")


router = APIRouter()


@router.get("/documents/search")
def documents_get(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_get("doc_metadata", request, db)

@router.post("/documents/search")
async def documents_post(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_post("doc_metadata", await request.json(), db)


@router.get("/chunks/search")
def chunks_get(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_get("chunk_metadata", request, db)

@router.post("/chunks/search")
async def chunks_post(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_post("chunk_metadata", await request.json(), db)


@router.get("/factable/search")
def factable_get(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_get("fact_table", request, db)

@router.post("/factable/search")
async def factable_post(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    return run_search_post("fact_table", await request.json(), db)


app = FastAPI(title="Search API")
app.include_router(router)
