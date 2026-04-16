"""
Search API over doc_metadata, chunk_metadata, and fact_table.

GET (recommended):
    /documents/search?fiscal_year_gte=2020&document_type=report&limit=20

POST (escape hatch for queries that don't fit in a URL):
    {
        "conditions": [
            {"column": "fiscal_year", "operator": "gte", "value": 2020},
            {"column": "document_type", "operator": "eq", "value": "report"}
        ],
        "return_cols": ["document_id", "document_name"],
        "limit": 20,
        "offset": 0
    }

Filter syntax (GET):
    ?document_type=report              eq is the default
    ?fiscal_year_gte=2020              operator via _suffix
    ?document_type_in=report,brief     comma-separated list
    ?entities_contains_any=epa,noaa    array operator
    ?search_matches=climate+policy     full-text search

Reserved query params: limit, offset, return_cols

Backend: SQLAlchemy Connection (pg8000 or psycopg2 dialect).
`db` arguments are SQLAlchemy Connection objects from engine.connect().
"""

from typing import Annotated, Any, Literal
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text


# ---- operators ------------------------------------------------------------

OperatorLiteral = Literal[
    "eq", "neq", "lt", "lte", "gt", "gte",
    "like", "ilike",
    "in", "not_in",
    "matches",
    "contains_any", "contains_all", "contains_none", "is_empty", "not_empty",
]

SCALAR_OPERATORS = {
    "eq": "=", "neq": "!=",
    "lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
    "like": "LIKE", "ilike": "ILIKE",
}

ARRAY_OPERATORS = {"eq", "contains_any", "contains_all", "contains_none", "is_empty", "not_empty"}

LIST_VALUE_OPERATORS = {"in", "not_in", "contains_any", "contains_all", "contains_none"}
NO_VALUE_OPERATORS = {"is_empty", "not_empty"}

# Longest first so "entities_contains_any" parses as column=entities, operator=contains_any
# and not column=entities_contains, operator=any.
KNOWN_OPERATORS = sorted(
    set(SCALAR_OPERATORS) | {"in", "not_in", "matches"} | ARRAY_OPERATORS,
    key=len, reverse=True,
)


# ---- column types ---------------------------------------------------------
#
# Scalars: "uuid", "text", "int", "numeric", "date", "bool", "tsvector"
# Arrays:  "array[<scalar>]", e.g. "array[text]", "array[int]", "array[date]"

SCALAR_TYPES = {"uuid", "text", "int", "numeric", "date", "bool", "tsvector"}


def is_array(column_type: str) -> bool:
    return column_type.startswith("array[") and column_type.endswith("]")


def array_inner(column_type: str) -> str:
    return column_type[len("array["):-1]


def operators_for_type(column_type: str) -> set[str]:
    if is_array(column_type):
        return ARRAY_OPERATORS
    return {
        "uuid":     {"eq", "neq", "in", "not_in"},
        "text":     {"eq", "neq", "in", "not_in", "like", "ilike"},
        "int":      {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
        "numeric":  {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
        "date":     {"eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in"},
        "bool":     {"eq"},
        "tsvector": {"matches"},
    }[column_type]


# ---- table registry -------------------------------------------------------

TABLES = {
    "doc_metadata": {
        "table": "doc_metadata",
        "fields": {
            "document_id":       "uuid",
            "document_name":     "text",
            "document_number":   "numeric",
            "document_type":     "text",
            "fiscal_year":       "int",
            "file_name":         "text",
            "document_summary":  "text",
            "document_created":  "date",
            "dates_referenced":  "array[date]",
            "document_synonyms": "array[text]",
            "version":           "text",
            "is_latest":         "bool",
            "enabled":           "bool",
            "search":            "tsvector",
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
            "entities":             "array[text]",
            "key_phrases":          "array[text]",
            "pages":                "array[int]",
            "tables":               "array[text]",
            "images":               "array[text]",
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
            "topic_dates_referenced": "array[date]",
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


# ---- pydantic models ------------------------------------------------------

class SearchCondition(BaseModel):
    """A single filter predicate applied to one column."""
    column: str = Field(
        description="The column name to filter on (e.g. 'fiscal_year', 'document_type')."
    )
    operator: OperatorLiteral = Field(
        default="eq",
        description=(
            "Comparison operator. Defaults to 'eq'. "
            "Use 'in'/'not_in' for list membership, "
            "'contains_any'/'contains_all'/'contains_none' for array columns, "
            "'matches' for full-text search columns, "
            "'is_empty'/'not_empty' for array emptiness checks."
        ),
    )
    value: Any = Field(
        default=None,
        description=(
            "The value to compare against. "
            "Pass a list for 'in', 'not_in', and array containment operators. "
            "Omit entirely for 'is_empty' / 'not_empty'."
        ),
    )

    @model_validator(mode="after")
    def check_operator_value_shape(self):
        """Shape check only. Type/schema validation happens in the pipeline."""
        if self.operator in NO_VALUE_OPERATORS:
            if self.value is not None:
                raise ValueError(f"operator {self.operator!r} must not have a value")
        elif self.operator in LIST_VALUE_OPERATORS:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"operator {self.operator!r} requires a non-empty list value")
        else:
            if self.value is None:
                raise ValueError(f"operator {self.operator!r} requires a value")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"column": "fiscal_year", "operator": "gte", "value": 2020},
                {"column": "document_type", "operator": "eq", "value": "report"},
                {"column": "entities", "operator": "contains_any", "value": ["epa", "noaa"]},
            ]
        }
    }


class SearchQuery(BaseModel):
    """Request body for all POST /search endpoints."""
    conditions: list[SearchCondition] = Field(
        default_factory=list,
        description="List of filter conditions, all ANDed together. Empty list returns everything.",
    )
    return_cols: list[str] | None = Field(
        default=None,
        description="Columns to include in each result row. Defaults to the table's default column set.",
    )
    limit: int = Field(default=20, ge=1, le=1000, description="Max rows to return.")
    offset: int = Field(default=0, ge=0, description="Rows to skip for pagination.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conditions": [
                        {"column": "fiscal_year", "operator": "gte", "value": 2020},
                        {"column": "document_type", "operator": "eq", "value": "report"},
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
    results: list[dict]
    total: int
    limit: int
    offset: int
    next_offset: int | None


# ---- GET parser -----------------------------------------------------------

def split_key(key: str, schema: dict) -> tuple[str, str]:
    """Turn a query-param key into (column, operator). Default operator is eq."""
    if key in schema["fields"]:
        return key, "eq"
    for operator in KNOWN_OPERATORS:
        suffix = "_" + operator
        if key.endswith(suffix):
            column = key[: -len(suffix)]
            if column in schema["fields"]:
                return column, operator
    raise HTTPException(400, f"unknown column or operator: {key!r}")


RESERVED_PARAMS = {"limit", "offset", "return_cols"}


def parse_int_param(name: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(400, f"{name} must be an integer, got {raw!r}")


def parse_value_from_string(raw: str, operator: str, column_type: str) -> Any:
    """Turn a raw query-string value into the right shape (list or scalar or None)."""
    if operator in NO_VALUE_OPERATORS:
        return None
    if operator in LIST_VALUE_OPERATORS or (operator == "eq" and is_array(column_type)):
        return [v for v in raw.split(",") if v]
    return raw


def build_condition_from_param(key: str, raw: str, schema: dict) -> SearchCondition:
    column, operator = split_key(key, schema)
    column_type = schema["fields"][column]
    value = parse_value_from_string(raw, operator, column_type)
    return SearchCondition(column=column, operator=operator, value=value)


def search_query_from_get(table_name: str):
    """Returns a Depends-able function that parses GET query params into a SearchQuery."""
    def parse(request: Request) -> SearchQuery:
        schema = TABLES.get(table_name)
        if not schema:
            raise HTTPException(404, f"unknown table {table_name!r}")

        params = {"limit": 20, "offset": 0, "return_cols": None}
        conditions: list[SearchCondition] = []

        for key, raw in request.query_params.multi_items():
            if key in ("limit", "offset"):
                params[key] = parse_int_param(key, raw)
            elif key == "return_cols":
                params["return_cols"] = [c.strip() for c in raw.split(",") if c.strip()]
            else:
                conditions.append(build_condition_from_param(key, raw, schema))

        try:
            return SearchQuery(conditions=conditions, **params)
        except ValueError as e:
            raise HTTPException(422, str(e))

    return parse


# ---- validate + convert ---------------------------------------------------

def convert_scalar(value: Any, column_type: str, column: str) -> Any:
    try:
        if column_type == "uuid":
            return str(UUID(str(value)))
        if column_type == "int":
            return int(value)
        if column_type == "numeric":
            return float(value)
        if column_type == "date":
            return datetime.fromisoformat(str(value)).date()
        if column_type == "bool":
            if isinstance(value, bool):
                return value
            v = str(value).lower()
            if v == "true":
                return True
            if v == "false":
                return False
            raise ValueError("expected 'true' or 'false'")
        # text, tsvector
        return str(value)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"cannot convert {column!r} to {column_type}: {e}")


def convert_value(value: Any, operator: str, column_type: str, column: str) -> Any:
    """Convert a condition's value based on its operator and the column type."""
    if operator in NO_VALUE_OPERATORS:
        return None

    if is_array(column_type):
        inner = array_inner(column_type)
        if operator == "eq" and not isinstance(value, list):
            raise HTTPException(400, f"eq on array column {column!r} needs a list value")
        return [convert_scalar(v, inner, column) for v in value]

    if operator in ("in", "not_in"):
        return [convert_scalar(v, column_type, column) for v in value]

    return convert_scalar(value, column_type, column)


def validate_condition(condition: SearchCondition, schema: dict) -> None:
    """Check the column exists and the operator is valid, then convert the value in place."""
    if condition.column not in schema["fields"]:
        raise HTTPException(400, f"unknown column: {condition.column!r}")

    column_type = schema["fields"][condition.column]
    if condition.operator not in operators_for_type(column_type):
        raise HTTPException(
            400,
            f"operator {condition.operator!r} not allowed on {column_type} column {condition.column!r}",
        )

    condition.value = convert_value(condition.value, condition.operator, column_type, condition.column)


def resolve_return_cols(return_cols: list[str] | None, schema: dict) -> list[str]:
    """Fill in defaults or validate the user's requested columns."""
    if return_cols is None:
        return list(schema["default_cols"])

    for col in return_cols:
        if col not in schema["fields"]:
            raise HTTPException(400, f"unknown return col: {col!r}")
        if schema["fields"][col] == "tsvector":
            raise HTTPException(400, f"cannot return tsvector column: {col!r}")
    return return_cols


def validate_and_convert(schema: dict, query: SearchQuery) -> SearchQuery:
    """Schema-aware validation. Checks columns, operators, and converts values."""
    for condition in query.conditions:
        validate_condition(condition, schema)
    query.return_cols = resolve_return_cols(query.return_cols, schema)
    return query


# ---- build SQL ------------------------------------------------------------

def build_where(schema: dict, conditions: list[SearchCondition]) -> tuple[list[str], dict]:
    """
    Returns (fragments, params) where:
      fragments: list of SQL snippets using :p0, :p1, ... named placeholders
      params:    dict mapping those placeholder names to values
    """
    fragments: list[str] = []
    params: dict[str, Any] = {}

    def bind(value: Any) -> str:
        key = f"p{len(params)}"
        params[key] = value
        return f":{key}"

    for condition in conditions:
        column_type = schema["fields"][condition.column]
        col = f'"{condition.column}"'

        if column_type == "tsvector":
            tsvector_col = schema["tsvector_col"]
            if not tsvector_col:
                raise HTTPException(400, f"table has no tsvector column for {condition.column!r}")
            fragments.append(f'"{tsvector_col}" @@ plainto_tsquery({bind(condition.value)})')

        elif is_array(column_type):
            if condition.operator == "is_empty":
                fragments.append(f"(cardinality({col}) = 0 OR {col} IS NULL)")
            elif condition.operator == "not_empty":
                fragments.append(f"cardinality({col}) > 0")
            elif condition.operator == "contains_all":
                placeholders = ", ".join(bind(v) for v in condition.value)
                fragments.append(f"{col} @> ARRAY[{placeholders}]")
            elif condition.operator == "contains_any":
                placeholders = ", ".join(bind(v) for v in condition.value)
                fragments.append(f"{col} && ARRAY[{placeholders}]")
            elif condition.operator == "contains_none":
                placeholders = ", ".join(bind(v) for v in condition.value)
                fragments.append(f"NOT ({col} && ARRAY[{placeholders}])")
            elif condition.operator == "eq":
                placeholders = ", ".join(bind(v) for v in condition.value)
                fragments.append(f"{col} = ARRAY[{placeholders}]")

        elif condition.operator in ("in", "not_in"):
            placeholders = ", ".join(bind(v) for v in condition.value)
            keyword = "IN" if condition.operator == "in" else "NOT IN"
            fragments.append(f"{col} {keyword} ({placeholders})")

        else:
            fragments.append(f"{col} {SCALAR_OPERATORS[condition.operator]} {bind(condition.value)}")

    return fragments, params


def build_sql(schema: dict, query: SearchQuery) -> tuple[str, dict, str, dict]:
    """Returns (data_sql, data_params, count_sql, count_params)."""
    fragments, where_params = build_where(schema, query.conditions)
    where_sql = f"WHERE {' AND '.join(fragments)}" if fragments else ""
    select_sql = ", ".join(f'"{c}"' for c in query.return_cols)
    table = f'"{schema["table"]}"'

    data_sql = f"SELECT {select_sql} FROM {table} {where_sql} LIMIT :_limit OFFSET :_offset".strip()
    data_params = {**where_params, "_limit": query.limit, "_offset": query.offset}
    count_sql = f"SELECT COUNT(*) FROM {table} {where_sql}".strip()
    count_params = dict(where_params)
    return data_sql, data_params, count_sql, count_params


# ---- pipeline -------------------------------------------------------------

def run_pipeline(table_name: str, query: SearchQuery, db) -> dict:
    """`db` is a SQLAlchemy Connection (from engine.connect())."""
    schema = TABLES.get(table_name)
    if not schema:
        raise HTTPException(404, f"unknown table {table_name!r}")

    query = validate_and_convert(schema, query)
    data_sql, data_params, count_sql, count_params = build_sql(schema, query)

    try:
        data_result = db.execute(text(data_sql), data_params)
        rows = [dict(m) for m in data_result.mappings()]
        total = db.execute(text(count_sql), count_params).scalar() or 0
    except Exception as e:
        raise HTTPException(500, f"db error: {type(e).__name__}: {e}")

    return {
        "results": rows,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
        "next_offset": query.offset + query.limit if query.offset + query.limit < total else None,
    }


# ---- routes ---------------------------------------------------------------

def get_db():
    """Wire this up to your SQLAlchemy engine."""
    raise NotImplementedError("wire this up to your SQLAlchemy engine")


def get_current_user():
    raise NotImplementedError("wire this up to your auth")


router = APIRouter()


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


@router.get("/chunks/search", response_model=SearchResponse)
def chunks_get(
    query: Annotated[SearchQuery, Depends(search_query_from_get("chunk_metadata"))],
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("chunk_metadata", query, db)


@router.post("/chunks/search", response_model=SearchResponse)
def chunks_post(
    query: SearchQuery,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("chunk_metadata", query, db)


@router.get("/factable/search", response_model=SearchResponse)
def factable_get(
    query: Annotated[SearchQuery, Depends(search_query_from_get("fact_table"))],
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("fact_table", query, db)


@router.post("/factable/search", response_model=SearchResponse)
def factable_post(
    query: SearchQuery,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    return run_pipeline("fact_table", query, db)


app = FastAPI(title="Search API")
app.include_router(router)
