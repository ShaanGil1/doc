import os
import io
import re
import time
import json
import gzip
import zipfile
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from doccano_client import DoccanoClient

DOCCANO_BASE_URL = os.getenv("DOCCANO_BASE_URL", "http://doccano:8000")
DOCCANO_USERNAME = os.getenv("DOCCANO_USERNAME", "admin")
DOCCANO_PASSWORD = os.getenv("DOCCANO_PASSWORD", "password")

PGHOST = os.getenv("PGHOST", "postgres")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "tagdemo")
PGUSER = os.getenv("PGUSER", "taguser")
PGPASSWORD = os.getenv("PGPASSWORD", "tagpass")

TAG_PROJECT_NAME = os.getenv("TAG_PROJECT_NAME", "Tag QA (Demo)")
ALIAS_PROJECT_NAME = os.getenv("ALIAS_PROJECT_NAME", "Alias QA (Demo)")

CLEAR_ON_BOOTSTRAP = os.getenv("CLEAR_ON_BOOTSTRAP", "1") == "1"

TAG_LABELS = ["TAG_GOOD", "TAG_BAD", "TAG_UNSURE"]
ALIAS_LABELS = [
    "ALIAS_YES__PREF_A",
    "ALIAS_YES__PREF_B",
    "ALIAS_YES__PREF_UNIFIED",
    "ALIAS_NO__PREF_A",
    "ALIAS_NO__PREF_B",
    "ALIAS_NO__PREF_UNIFIED",
    "UNSURE",
]

# Legacy fallback (shouldn't be needed now that we keep IDs in meta)
RE_ID = re.compile(r"ID:\s*([^\n\r]+)")

def pg_conn():
    return psycopg2.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE, user=PGUSER, password=PGPASSWORD
    )

def wait_for_postgres(timeout_s=120):
    start = time.time()
    while True:
        try:
            with pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            return
        except Exception as e:
            if time.time() - start > timeout_s:
                raise RuntimeError(f"Postgres not ready after {timeout_s}s: {e}")
            time.sleep(2)

def wait_for_doccano(client: DoccanoClient, timeout_s=180):
    start = time.time()
    while True:
        try:
            client.login(DOCCANO_USERNAME, DOCCANO_PASSWORD)
            return
        except Exception as e:
            if time.time() - start > timeout_s:
                raise RuntimeError(f"Doccano not ready after {timeout_s}s: {e}")
            time.sleep(2)

def get_or_create_project(client: DoccanoClient, name: str):
    for p in client.list_projects():
        if getattr(p, "name", None) == name:
            return p
    return client.create_project(
        name=name,
        project_type="DocumentClassification",
        description="Auto-bootstrapped demo project",
        guideline=(
            "Select the best label.\n"
            "- Tag QA: TAG_GOOD / TAG_BAD / TAG_UNSURE\n"
            "- Alias QA: ALIAS_* labels; if *_PREF_UNIFIED then add preferred canonical in COMMENT.\n"
        ),
        random_order=False,
        collaborative_annotation=False,
        single_class_classification=True,
    )

def ensure_labels(client: DoccanoClient, project_id: int, label_texts):
    try:
        label_types = client.list_label_types(project_id, type="category")
    except TypeError:
        label_types = client.list_label_types(project_id)
    existing = {getattr(lt, "text", None) for lt in label_types}
    for t in label_texts:
        if t not in existing:
            try:
                client.create_label_type(project_id, type="category", text=t)
            except TypeError:
                client.create_label_type(project_id, text=t)

def delete_all_examples(client: DoccanoClient, project_id: int):
    if hasattr(client, "delete_all_examples"):
        client.delete_all_examples(project_id)
        return
    if not hasattr(client, "list_examples") or not hasattr(client, "delete_example"):
        return
    page = 1
    while True:
        examples = client.list_examples(project_id=project_id, page=page)
        if not examples:
            break
        for ex in examples:
            ex_id = getattr(ex, "id", None)
            if ex_id is not None:
                client.delete_example(project_id=project_id, example_id=ex_id)
        page += 1

def create_example(client: DoccanoClient, project_id: int, text: str, meta: dict):
    try:
        client.create_example(project_id=project_id, text=text, meta=meta, score=100.0)
    except TypeError:
        client.create_example(project_id=project_id, text=text, meta=meta)

def load_view_into_project(client: DoccanoClient, project_id: int, view_name: str):
    with pg_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {view_name} ORDER BY 1;")
        rows = cur.fetchall()
    for r in rows:
        txt = r["text"]
        meta = {k: v for k, v in r.items() if k not in ("text", "label")}
        create_example(client, project_id, txt, meta)

def bootstrap():
    wait_for_postgres()
    client = DoccanoClient(DOCCANO_BASE_URL, verify=False)
    wait_for_doccano(client)

    tag_proj = get_or_create_project(client, TAG_PROJECT_NAME)
    alias_proj = get_or_create_project(client, ALIAS_PROJECT_NAME)

    ensure_labels(client, tag_proj.id, TAG_LABELS)
    ensure_labels(client, alias_proj.id, ALIAS_LABELS)

    if CLEAR_ON_BOOTSTRAP:
        delete_all_examples(client, tag_proj.id)
        delete_all_examples(client, alias_proj.id)

    load_view_into_project(client, tag_proj.id, "tag_qa_doccano_view")
    load_view_into_project(client, alias_proj.id, "alias_qa_doccano_view")

    print("Bootstrap complete.")
    print(f" - {TAG_PROJECT_NAME} (id={tag_proj.id})")
    print(f" - {ALIAS_PROJECT_NAME} (id={alias_proj.id})")

def download_jsonl(client: DoccanoClient, project_id: int) -> str:
    try:
        return client.download(project_id=project_id, format="JSONL", only_approved=False, dir_name="/tmp")
    except TypeError:
        return client.download(project_id=project_id, format="JSONL", dir_name="/tmp")

def iter_jsonl_lines(path: str):
    with open(path, "rb") as fb:
        head = fb.read(4)

    if head[:2] == b"\x1f\x8b":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line
        return

    if head == b"PK\x03\x04":
        with zipfile.ZipFile(path) as z:
            members = [n for n in z.namelist() if not n.endswith("/")]
            if not members:
                return
            with z.open(members[0]) as bf:
                wrapper = io.TextIOWrapper(bf, encoding="utf-8", errors="replace")
                for line in wrapper:
                    yield line
        return

    with open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line

def export_project_labels_to_pg(client: DoccanoClient, project_id: int, target_table: str, id_column: str):
    out_path = download_jsonl(client, project_id)

    updates = []
    for line in iter_jsonl_lines(out_path):
        if not line.strip():
            continue

        obj = json.loads(line)
        meta = obj.get("meta") or {}
        row_id = meta.get(id_column)

        if not row_id:
            text = obj.get("text", "")
            m = RE_ID.search(text)
            row_id = m.group(1).strip() if m else None

        if not row_id:
            continue

        label_val = obj.get("label")
        if isinstance(label_val, list):
            label_val = label_val[0] if label_val else None
        if not label_val:
            continue

        comment_val = (
            obj.get("comment")
            or obj.get("comments")
            or meta.get("comment")
            or meta.get("reviewer_comment")
        )
        if isinstance(comment_val, list):
            comment_val = " | ".join(str(x) for x in comment_val)

        updates.append((row_id, label_val, comment_val))

    now = datetime.now(timezone.utc)
    with pg_conn() as conn, conn.cursor() as cur:
        for row_id, label_val, comment_val in updates:
            cur.execute(
                f"""
                UPDATE {target_table}
                SET reviewer_label = %s,
                    reviewer_comment = COALESCE(%s, reviewer_comment),
                    reviewed_at = %s
                WHERE {id_column} = %s;
                """,
                (label_val, comment_val, now, row_id),
            )
        conn.commit()

    print(f"Wrote {len(updates)} rows back to {target_table}.")

def export_all():
    wait_for_postgres()
    client = DoccanoClient(DOCCANO_BASE_URL, verify=False)
    wait_for_doccano(client)

    tag_id = None
    alias_id = None
    for p in client.list_projects():
        if getattr(p, "name", None) == TAG_PROJECT_NAME:
            tag_id = p.id
        if getattr(p, "name", None) == ALIAS_PROJECT_NAME:
            alias_id = p.id

    if tag_id is None or alias_id is None:
        raise RuntimeError("Projects not found. Run bootstrap first.")

    export_project_labels_to_pg(client, tag_id, "tag_qa_candidates", "candidate_id")
    export_project_labels_to_pg(client, alias_id, "alias_qa_pairs", "pair_id")

def main():
    import sys
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "bootstrap"
    if cmd == "bootstrap":
        bootstrap()
    elif cmd == "export":
        export_all()
    else:
        raise SystemExit("Usage: python bridge.py [bootstrap|export]")

if __name__ == "__main__":
    main()
