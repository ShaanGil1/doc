-- 10_load_seed_data.sql
\copy tag_qa_candidates(candidate_id,tag_name,category,llm_confidence,llm_justification,llm_definition,chunk_summary,chunk_text,document_title,doc_summary,document_ref,evidence_snippets,candidate_sources,notes_for_reviewer) FROM '/docker-entrypoint-initdb.d/tag_qa.csv' WITH (FORMAT csv, HEADER true);
\copy alias_qa_pairs(pair_id,word_one,word_two,category,embedding_similarity,string_similarity,llm_justification,definition_1,context_1,definition_2,context_2,notes_for_reviewer) FROM '/docker-entrypoint-initdb.d/alias_qa.csv' WITH (FORMAT csv, HEADER true);
