# ADR-001: Modular Monolith Architecture with PostgreSQL Row-Level Security (RLS) and Provider-Neutral RAG

- **Status**: Accepted
- **Date**: 2026-10-29
- **Context**: Akademia AI requires institutional-grade multi-tenant isolation, deterministic competency tracking, and course-grounded Generative AI across two independently deployable repositories (`akademia-ai-backend` and `akademia-ai-frontend`).

## Decisions

1. **Independent Frontend & Backend Repositories (`akademia-ai-backend` / `akademia-ai-frontend`)**:
   - The backend exposes a versioned `/api/v1` REST API and exports its OpenAPI 3.1 contract (`openapi.json`), which is synchronized with `akademia-ai-frontend/src/api/generated/schema.ts`.
2. **Modular Monolith Backend**:
   - Domain modules (`identity`, `tenants`, `memberships`, `courses`, `enrollments`, `assessments`, `content`, `ai_tutor`, `learning_intelligence`, `subscriptions`, `audit`) are cleanly separated inside `app/modules/` and share a single ACID PostgreSQL transaction boundary per request.
3. **Shared PostgreSQL Schema with Mandatory Row-Level Security (`ENABLE` + `FORCE ROW LEVEL SECURITY`)**:
   - All 52 tenant-owned tables carry a non-nullable `tenant_id` column, composite tenant-aware foreign keys (`UNIQUE (tenant_id, id)`), and fail-closed RLS policies gated on `NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
   - Runtime database roles (`akademia_app`, `akademia_worker`) are provisioned with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
4. **Provider-Neutral AI Subsystem (`app/ai/contracts.py`)**:
   - Domain services depend only on `LanguageModel`, `EmbeddingModel`, `CourseRetriever`, `ContentExtractor`, and `AIUsageRecorder` protocols.
   - Pre-retrieval tenant/course filtering and post-generation citation verification guarantee zero cross-tenant or ungrounded halluncinated citations.
