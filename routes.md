async def search_documents(...):
    '''
    Search document metadata.

    Filterable columns:

    | Column | Type | Supported Operators |
    | --- | --- | --- |
    | document_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_name | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_number | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_type | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | fiscal_year | int | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | dates_referenced | array[date] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | file_name | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_synonyms | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | document_summary | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_created | date | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | version | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_description | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | policies | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | is_latest | bool | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | enabled | bool | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | entities | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | topics | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    '''
    
async def search_chunks(...):
    '''
    Search chunk metadata.

    Filterable columns:

    | Column | Type | Supported Operators |
    | --- | --- | --- |
    | chunk_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | chunk_file | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | file_name | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | pages | array[int] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | document_name | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | chunking_strategy | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | chunk_text_markdown | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | entities | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | key_phrases | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | bounding_box | array[float] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | content_summary | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | version | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | is_latest | bool | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | enabled | bool | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | parent_document_type | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | tables | array[text] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | images | array[float] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | chunk_text_search_tsvector | tsvector | matches |
    '''

async def search_facts(...):
    '''
    Search the fact table (document-level topics and date ranges).

    Filterable columns:

    | Column | Type | Supported Operators |
    | --- | --- | --- |
    | topic_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | chunk_id | uuid | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic_type | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | key_information | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic_fiscal_year | int | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic_confidence | int | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic_dates_referenced | array[date] | eq, contains_any, contains_all, contains_none, is_empty, not_empty |
    | authority_level | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | document_version | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | is_latest | bool | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | start_date | date | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | end_date | date | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | category | text | eq, neq, lt, lte, gt, gte, in, not_in, like, ilike |
    | topic_keyword_search_tsvector | tsvector | matches |
    '''
