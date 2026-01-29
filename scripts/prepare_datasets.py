"""Convert the provided mock CSVs into Doccano-friendly JSONL files.

Usage:
  python scripts/prepare_datasets.py

Outputs:
  data/tag_qa.jsonl
  data/alias_qa.jsonl
"""

import json
import re
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
TAG_CSV = DATA / "mock_doccano_tag_qa.csv"
ALIAS_CSV = DATA / "mock_doccano_alias_qa_v2.csv"

def truncate(s: str, n: int = 450) -> str:
    s = "" if pd.isna(s) else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + "…") if len(s) > n else s

def main():
    tag_df = pd.read_csv(TAG_CSV)
    alias_df = pd.read_csv(ALIAS_CSV)

    # Tag QA (Text Classification)
    tag_out = DATA / "tag_qa.jsonl"
    with tag_out.open("w", encoding="utf-8") as f:
        for _, r in tag_df.iterrows():
            text = "\n".join([
                "[TAG CANDIDATE QA]",
                f"Candidate ID: {r.get('candidate_id','')}",
                f"Proposed tag: {r.get('tag_name','')}",
                f"Proposed category: {r.get('category','')}",
                f"LLM confidence: {r.get('llm_confidence','')}",
                f"Sources: {r.get('candidate_sources','')}",
                "",
                f"Document: {r.get('document_title','')}",
                f"Document ref: {r.get('document_ref','')}",
                "",
                "Chunk summary:",
                f"  {truncate(r.get('chunk_summary',''), 260)}",
                "",
                "Chunk text:",
                f"  {truncate(r.get('chunk_text',''), 420)}",
                "",
                "Evidence snippets:",
                f"  {truncate(r.get('evidence_snippets',''), 300)}",
                "",
                "Notes for reviewer:",
                f"  {truncate(r.get('notes_for_reviewer',''), 260)}",
                "",
                "Decision: choose one label -> YES / NO / UNSURE",
            ])
            rec = {"text": text, "meta": {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Alias QA (Sequence-to-Sequence)
    alias_out = DATA / "alias_qa.jsonl"
    with alias_out.open("w", encoding="utf-8") as f:
        for _, r in alias_df.iterrows():
            term_a = str(r.get("word_one",""))
            term_b = str(r.get("word_two",""))
            text = "\n".join([
                "[ALIAS / CANONICALIZATION QA]",
                f"Pair ID: {r.get('pair_id','')}",
                f"Category: {r.get('category','')}",
                f"Term A: {term_a}",
                f"Term B: {term_b}",
                f"Embedding similarity: {r.get('embedding_similarity','')}",
                f"String similarity: {r.get('string_similarity','')}",
                "",
                "Context 1:",
                f"  {truncate(r.get('context_1',''), 380)}",
                "",
                "Context 2:",
                f"  {truncate(r.get('context_2',''), 380)}",
                "",
                "Notes for reviewer:",
                f"  {truncate(r.get('notes_for_reviewer',''), 260)}",
                "",
                "What to type in the OUTPUT box:",
                "  - If NOT aliases: type exactly  NO_ALIAS",
                f"  - If aliases + prefer Term A as canonical: type exactly  {term_a}",
                f"  - If aliases + prefer Term B as canonical: type exactly  {term_b}",
                "  - If aliases + want a unified canonical (new): type your canonical string (e.g., 'Department of Defense (DoD)')",
            ])
            rec = {"text": text, "meta": {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("Wrote:")
    print(f"  {tag_out}")
    print(f"  {alias_out}")

if __name__ == "__main__":
    main()
