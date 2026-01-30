-- 00_create_tables.sql
DROP TABLE IF EXISTS tag_qa_candidates;
DROP TABLE IF EXISTS alias_qa_pairs;

CREATE TABLE tag_qa_candidates (
  candidate_id           TEXT PRIMARY KEY,
  tag_name               TEXT,
  category               TEXT,
  llm_confidence         DOUBLE PRECISION,
  llm_justification      TEXT,
  llm_definition         TEXT,
  chunk_summary          TEXT,
  chunk_text             TEXT,
  document_title         TEXT,
  doc_summary            TEXT,
  document_ref           TEXT,
  evidence_snippets      TEXT,
  candidate_sources      TEXT,
  notes_for_reviewer     TEXT,
  reviewer_label         TEXT,
  reviewer_comment       TEXT,
  reviewed_at            TIMESTAMPTZ
);

CREATE TABLE alias_qa_pairs (
  pair_id                TEXT PRIMARY KEY,
  word_one               TEXT,
  word_two               TEXT,
  category               TEXT,
  embedding_similarity   DOUBLE PRECISION,
  string_similarity      DOUBLE PRECISION,
  llm_justification      TEXT,
  definition_1           TEXT,
  context_1              TEXT,
  definition_2           TEXT,
  context_2              TEXT,
  notes_for_reviewer     TEXT,
  reviewer_label         TEXT,
  reviewer_comment       TEXT,
  reviewed_at            TIMESTAMPTZ
);
