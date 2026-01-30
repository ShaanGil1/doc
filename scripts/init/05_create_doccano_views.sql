-- 05_create_doccano_views.sql
-- IDs are included ONLY in meta columns (candidate_id / pair_id), not inside the visible text.
CREATE OR REPLACE VIEW tag_qa_doccano_view AS
SELECT
  (
    'Tag: ' || COALESCE(tag_name, '') || E'\n' ||
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' || E'\n' ||
    'Tag Category: ' || COALESCE(category, '') || E'\n' ||
    'LLM Score: ' || COALESCE(llm_confidence::text, '') || E'\n' ||
    'LLM Justification: ' || COALESCE(llm_justification, '') || E'\n' ||
    'LLM Definition: ' || COALESCE(llm_definition, '') || E'\n' ||
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' || E'\n' ||
    'Chunk Summary:' || E'\n' ||
    COALESCE(chunk_summary, '') || E'\n\n' ||
    'Chunk Text:' || E'\n' ||
    COALESCE(chunk_text, '') || E'\n' ||
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' || E'\n' ||
    'Document Title: ' || COALESCE(document_title, '') || E'\n' ||
    'Doc Summary: ' || COALESCE(doc_summary, '') || E'\n' ||
    'Doc Ref: ' || COALESCE(document_ref, '') || E'\n'
  ) AS text,
  ''::text AS label,
  candidate_id,
  tag_name,
  category,
  llm_confidence,
  document_ref
FROM tag_qa_candidates;

CREATE OR REPLACE VIEW alias_qa_doccano_view AS
SELECT
  (
    'WORD 1: ' || COALESCE(word_one, '') || E'\n' ||
    'WORD 2: ' || COALESCE(word_two, '') || E'\n' ||
    E'\n' ||
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' || E'\n' ||
    'Similarity Score: ' || COALESCE(embedding_similarity::text,'') || E'\n' ||
    'String Similarity: ' || COALESCE(string_similarity::text,'') || E'\n' ||
    'LLM Justification: ' || COALESCE(llm_justification,'') || E'\n' ||
    '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' || E'\n' ||
    E'\n' ||
    'Definition 1:' || E'\n' ||
    COALESCE(definition_1,'') || E'\n' ||
    'Context 1:' || E'\n' ||
    COALESCE(context_1,'') || E'\n' ||
    E'\n' ||
    'Definition 2:' || E'\n' ||
    COALESCE(definition_2,'') || E'\n' ||
    'Context 2:' || E'\n' ||
    COALESCE(context_2,'') || E'\n'
  ) AS text,
  ''::text AS label,
  pair_id,
  word_one,
  word_two,
  category,
  embedding_similarity,
  string_similarity
FROM alias_qa_pairs;
