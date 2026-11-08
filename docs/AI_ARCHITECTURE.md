# Akademia AI — Generative AI & RAG Architecture (`AI_ARCHITECTURE.md`)

## 1. Provider-Neutral AI Subsystem

All domain modules interact exclusively with the provider-neutral protocols in `app/ai/contracts.py` and the factory registry in `app/ai/registry.py`. Domain services never import provider-specific SDKs.

### Core Contracts (`app/ai/contracts.py`)
1. `LanguageModel`:
   - `generate_tutor_response(...) -> StructuredTutorResponse`
   - `generate_practice_questions(...) -> list[GeneratedPracticeQuestionSchema]`
2. `EmbeddingModel`:
   - `embed_texts(texts: list[str]) -> list[list[float]]`
   - `embed_query(text: str) -> list[float]`
3. `CourseRetriever`:
   - `retrieve(...) -> list[RetrievedPassage]`
4. `ContentExtractor`:
   - `extract_chunks(...) -> list[ExtractedChunk]`
5. `AIUsageRecorder`:
   - `record_usage(...) -> None`

---

## 2. Pre-Retrieval Tenant & Course Authorization (`app/ai/retrieval/service.py`)

Akademia AI enforces **Pre-Retrieval Authorization** before any vector or lexical search executes:
1. `PgVectorCourseRetriever.retrieve_authorized_passages()` requires an explicit `tenant_id` and `course_id`.
2. The SQL query against `document_chunks` joined with `documents` and `chunk_embeddings` filters explicitly on:
   - `document_chunks.tenant_id = :tenant_id`
   - `document_chunks.course_id = :course_id`
   - `documents.status = 'ready'` and `chunk_embeddings.indexing_status = 'indexed'`
   - `chunk_embeddings.embedding_model_id` matching the active embedding model
3. Additionally, PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`) is active on `documents`, `document_chunks`, and `chunk_embeddings`.
4. Retrieved chunks are scored with a hybrid of `pgvector` cosine similarity (weight `0.55`) and lexical keyword overlap (weight `0.45`), and sanitized via `sanitize_passage_text()` to neutralize indirect prompt-injection payloads embedded in uploaded documents.

---

## 3. Verifiable Citations & Academic Integrity Guardrails (`app/ai/safety/guardrails.py`)

- **Strict Citation Verification**: Every citation returned by `LanguageModel.generate_grounded_tutor_response()` is validated by `verify_and_filter_citations()` against the exact set of authorized `RetrievedPassage` chunk IDs retrieved for that turn. Any hallucinated or unauthorized `chunk_id` is stripped before persistence or response serialization.
- **Insufficient Context Honesty**: A retrieved passage counts as supporting evidence only if it covers at least **25% of the question's content terms** or has a hybrid relevance score of at least **`0.35`**. A single incidental shared word (e.g. "policy") is not treated as grounding. When no passage qualifies, the AI Tutor returns `grounding_status = "insufficient_course_material"` with no citations and explicitly declines to speculate outside approved course materials.
- **Academic Integrity Guardrail during Active Assessments**: In `AITutorService.send_message()` (`app/modules/ai_tutor/service.py`), when the course's `academic_integrity_policy` is `strict_during_assessment` and the learner has an `in_progress` assessment attempt in that course, the tutor does not retrieve or answer and returns `grounding_status = "integrity_restricted"`.
