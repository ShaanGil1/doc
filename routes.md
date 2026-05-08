if column_type == "tsvector":
tsvector_col = schema["tsvector_col"]
if not tsvector_col:
    raise HTTPException(400, f"table has no tsvector column for {condition.column!r}")
placeholder = bind(condition.value)
fragments.append(f'"{tsvector_col}" @@ websearch_to_tsquery(\'english\', {placeholder})')
# NEW: capture the rank expression, reusing the same bound param
rank_exprs.append(
    f'ts_rank_cd("{tsvector_col}", websearch_to_tsquery(\'english\', {placeholder}), 32)'
)

return fragments, params, rank_exprs



def build_sql(schema: dict, query: SearchQuery) -> tuple[str, dict, str, dict]:
    fragments, where_params, rank_exprs = build_where(schema, query.conditions)
    
    # ... existing select cols logic ...
    select_cols = [...]  # whatever you already build

    # NEW: add score column if any tsvector matches present
    if rank_exprs:
        # If multiple matches, sum the ranks
        score_expr = " + ".join(rank_exprs) if len(rank_exprs) > 1 else rank_exprs[0]
        select_clause = f"SELECT {', '.join(select_cols)}, {score_expr} AS _score"
        order_clause = "ORDER BY _score DESC"
    else:
        select_clause = f"SELECT {', '.join(select_cols)}"
        order_clause = ""  # or your existing default ordering

    where_clause = f"WHERE {' AND '.join(fragments)}" if fragments else ""
    
    data_sql = f"{select_clause} FROM {schema['table']} {where_clause} {order_clause} LIMIT %(limit)s OFFSET %(offset)s"
    # count_sql stays the same, no rank/order needed for counting
